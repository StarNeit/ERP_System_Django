from intramanee.bot import documents as doc
from intramanee.stock import documents as stock_doc
from intramanee.common import errors as err
import time


class Robot(object):

    def __init__(self):
        pass

    @classmethod
    def list_stock_requirement(cls, material_object_id, revision, size):
        # Validate if combination exists
        try:
            material_master = stock_doc.MaterialMaster(material_object_id)
            material_master.validate_pair(revision, size)
        except ValueError:
            raise err.BadParameterError('Unknown Material object_id=%s' % material_object_id)

        rec = doc.MRPSessionExecutionRecord()
        rec.material = material_master.code
        rec.revision = revision
        rec.size = size

        rec.populate('material_master')
        rec.gather()

        def convert(o):
            return {
                'marker': time.mktime(o.marker.timetuple()),
                'quantity': o.quantity,
            }
        return list(map(convert, rec.entries))

    @classmethod
    def run_mrp(cls, user, material_spec, wait=False):
        # Check permission
        user.can('mrp-session+write', None, True)
        if material_spec is None:
            # FIXME: query all TST material
            material_spec = stock_doc.MaterialMaster.manager.find(cond={
                'code': {'$regex': r'^stock-TST180'}
            })

            # Format output - [self.utils.finished_material.code, 20, None]
            def get_material_to_run(a):
                a.populate('schematic')
                sizes = a.schematic.conf_size
                r = []
                for s in sizes if len(sizes) > 0 else [None]:
                    r.append((a.code, a.schematic.rev_id, s))
                return r

            def merge(a, b):
                a.extend(b)
                return a
            material_spec = reduce(merge, map(get_material_to_run, material_spec), [])
        doc.MRPSession.kickoff(user, material_spec)
        if wait:
            doc.MRPSession.wait()
        return True

    @classmethod
    def get_running_session(cls):
        return doc.MRPSession.running_session()
