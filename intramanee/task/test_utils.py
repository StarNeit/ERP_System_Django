author = 'bank'
from intramanee.production.test_utils import ProductionFixture
from documents import ClerkAuxTask, StoreAuxTask
from intramanee.common import utils as u


class TaskFixture(ProductionFixture):

    def create_aux_task(self, verbose=True, **kwargs):
        order = self.create_production_orders(**kwargs)[0]
        order.populate('operation')

        def assign(o):
            o.assignee = self.tester
            o.touched(self.tester)

        map(assign, order.operation)
        order.release(self.tester)
        u.print_verbose(verbose, "order is released successfully")
        oid = [o.object_id for o in order.operation]

        clerks = ClerkAuxTask.manager.find(0, 0, {'parent_task': {'$in': oid}})
        stores = StoreAuxTask.manager.find(0, 0, {'parent_task': {'$in': oid}})

        return {'order': order, 'clerks': clerks, 'stores': stores}
