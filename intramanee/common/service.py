__author__ = 'peat'

from codes import *
from errors import BadParameterError, ProhibitedError
from task import TaskGroup
from location import Location
from intramanee.randd import documents as design_docs
from intramanee.stock import documents as stock_docs
from intramanee.sales import documents as sales_docs
from intramanee.production import documents as production_docs
from intramanee.purchasing import documents as purchasing_docs
from intramanee.models import IntraUser
from intramanee.common.codes import models
from intramanee.common.uoms import UOM
from intramanee.common.models import UserFile
from intramanee.common.documents import Revisioned, Event, Validatable, Authored, Docs
from intramanee.stock.documents import MaterialMaster
from json import JSONDecoder, JSONEncoder
from bson import ObjectId
from datetime import datetime
import re


class TypedCodeAvoidEncoder(JSONEncoder):

    def default(self, o):
        if isinstance(o, TypedCode):
            return str(o)
        return o.__dict__


def choices(requested_types):

    def key_value_pair(tup):
        return {'value': tup[0], 'label': tup[1]}

    def values_for_type(type):
        if type == 'uom':
            output = JSONDecoder().decode(TypedCodeAvoidEncoder().encode(UOM.uoms))
        elif type == 'grouped_uom':
            output = UOM.grouped_uoms
        elif type == 'mrp_type':
            output = map(key_value_pair, stock_docs.MaterialMaster.MRP_TYPES)
        elif type == 'lot_size':
            output = map(key_value_pair, stock_docs.MaterialMaster.LOT_SIZES)
        elif type == 'procurement_type':
            output = map(key_value_pair, stock_docs.MaterialMaster.PROCUREMENT_TYPES)
        elif type == 'abc_indicator':
            output = map(key_value_pair, stock_docs.MaterialMaster.AI_INDICATORS)
        elif type == 'plant_status':
            output = map(key_value_pair, stock_docs.MaterialMaster.PLANT_STATUSES)
        elif type == 'inv-movement_type':
            output = map(key_value_pair, stock_docs.InventoryMovement.TYPES)
        elif type == 'location':
            output = map(lambda (k, l): {'value': l.code, 'label': l.label}, Location.locations.iteritems())
        elif type == 'sales_order_status':
            output = map(key_value_pair, sales_docs.SalesOrder.SALES_ORDER_STATUSES)
        elif type == 'currency':
            output = map(key_value_pair, sales_docs.SalesOrder.CURRENCY)
        elif type == 'production_order_status':
            output = map(key_value_pair, production_docs.ProductionOrder.PRODUCTION_ORDER_STATUSES)
        elif type == 'production_order_type':
            output = map(key_value_pair, production_docs.ProductionOrder.PRODUCTION_ORDER_TYPES)
        elif type == 'pr_status':
            output = map(key_value_pair, purchasing_docs.PurchaseRequisition.DOC_STATUSES)
        elif type == 'pr_type':
            output = map(key_value_pair, purchasing_docs.PurchaseRequisition.PR_TYPES)
        elif type == 'pr_currency':
            output = map(key_value_pair, purchasing_docs.PurchaseRequisition.CURRENCY)
        elif type == 'task-group':
            output = TaskGroup.groups
        else:
            raise BadParameterError('Unknown choice type=%s' % type)
        return type, output

    return dict(values_for_type(t) for t in requested_types)


class IdLookupSource(object):
    type = "N/A"

    '''
    :return dictionary for possible values (key-value pair)
    '''
    def lookup(self, query, **kwargs):
        raise NotImplementedError('Required implementation')

    def fullCode(self, lookedup):
        return lookedup


class MaterialLookupSource(IdLookupSource):

    def __init__(self):
        self.type = "material_master"
        super(MaterialLookupSource, self).__init__()

    def lookup(self, query, **kwargs):
        q = re.compile(query, re.IGNORECASE)
        return map(lambda r: KV(r.object_id, str(r.code), info={'uom': r.uom}),
                   stock_docs.MaterialMaster.manager.find(pagesize=10, page=0, cond={
                       "$or": [
                            {
                                "code": {'$regex': q},
                            },
                            {
                                "_id": {'$regex': q},
                            }
                        ]
                   }))

    def fullCode(self, lookedup):
        return str(lookedup.code)


class ProductionOrderLookupSource(IdLookupSource):

    def __init__(self, and_cond=None):
        self.type = 'production_order'
        self.and_cond = and_cond
        super(ProductionOrderLookupSource, self).__init__()

    def lookup(self, query, **kwargs):
        def output(o):
            info = {
                "status": o.status,
            }
            return KV(o.object_id, str(o.doc_no), info=info)
        q = re.compile(query, re.IGNORECASE)
        cond = {
           "$or": [
               {
                   "_id": {'$regex': q}
               },
               {
                   "doc_no": {'$regex': q}
               }
           ]
        }
        if self.and_cond is not None:
            cond = {
                "$and": [
                    self.and_cond,
                    cond
                ]
            }
        return map(output, production_docs.ProductionOrder.manager.find(pagesize=10, page=0, cond=cond))

    def fullCode(self, lookedup):
        return str(lookedup.code)


class SalesOrderLookupSource(IdLookupSource):

    def __init__(self, and_cond=None):
        self.type = 'sales_order'
        self.and_cond = and_cond
        super(SalesOrderLookupSource, self).__init__()

    def lookup(self, query, **kwargs):
        def output(o):
            o.populate('sales_rep')
            info = {
                "customer": str(o.customer),
                "status": o.status,
                "sales_rep": o.sales_rep,
                "customer_currency": o.customer_currency,
                "delivery_date": o.delivery_date,
                "remark": o.remark
            }
            return KV(o.object_id, str(o.doc_no), info=info)
        q = re.compile(query, re.IGNORECASE)
        cond = {
           "$or": [
               {
                   "customer": {'$regex': q}
               },
               {
                   "_id": {'$regex': q}
               },
               {
                   "doc_no": {'$regex': q}
               }
           ]
        }
        if self.and_cond is not None:
            cond = {
                "$and": [
                    self.and_cond,
                    cond
                ]
            }
        return map(output, sales_docs.SalesOrder.manager.find(pagesize=10, page=0, cond=cond))

    def fullCode(self, lookedup):
        return str(lookedup.code)


class PurchaseRequisitionLookupSource(IdLookupSource):

    def __init__(self, and_cond=None):
        self.type = 'purchase_requisition'
        self.and_cond = and_cond
        super(PurchaseRequisitionLookupSource, self).__init__()

    def lookup(self, query, **kwargs):
        def output(o):
            info = {
                "vendor": str(o.vendor),
                "status": o.status,
                "currency": o.currency
            }
            return KV(o.object_id, str(o.doc_no), info=info)
        q = re.compile(query, re.IGNORECASE)
        cond = {
           "$or": [
               {
                   "vendor": {'$regex': q}
               },
               {
                   "_id": {'$regex': q}
               },
               {
                   "doc_no": {'$regex': q}
               }
           ]
        }
        if self.and_cond is not None:
            cond = {
                "$and": [
                    self.and_cond,
                    cond
                ]
            }
        return map(output, purchasing_docs.PurchaseRequisition.manager.find(pagesize=10, page=0, cond=cond))

    def fullCode(self, lookedup):
        return str(lookedup.code)


class IntramaneeCodeLookupSource(IdLookupSource):
    baseCode = None

    def __init__(self, type_, intramaneeCode_):
        super(IntramaneeCodeLookupSource, self).__init__()
        self.baseCode = intramaneeCode_
        self.type = type_

    def lookup(self, typed, **kwargs):
        return self.baseCode.suggest(typed, kwargs.get('limit', -1))

    def fullCode(self, lookedup):
        return "%s%s" % (str(self.baseCode), lookedup.code)


class IntramaneeCodeDeepLookupSource(IntramaneeCodeLookupSource):

    def __init__(self, type_, intramaneeCode_):
        super(IntramaneeCodeDeepLookupSource, self).__init__(type_, intramaneeCode_)


class IntramaneeCodeEnumLookupSource(IdLookupSource):
    enum = None
    type = None

    def __init__(self, type_, enum_):
        super(IntramaneeCodeEnumLookupSource, self).__init__()
        self.enum = enum_
        self.type = type_

    def lookup(self, typed, **kwargs):
        r = []
        for k, v in enumerate(self.enum.__dict__):
            o = self.enum.__dict__[v]
            if isinstance(o, IntramaneeCode):
                kv = o.tail()
                if kv and (kv.label.lower().startswith(typed) or kv.code.lower().startswith(typed)):
                    r.append(KV(o.code, kv.label, info=o))
        return r

    def fullCode(self, lookedup):
        return str(lookedup.info)


class LovLookupSource(IdLookupSource):

    def __init__(self, type_, group_):
        self.type = type_
        self.group = group_

    def lookup(self, typed, **kwargs):
        queried = models.LOV.objects.filter(Q(group=self.group) & (Q(code__istartswith=typed) | Q(label__istartswith=typed)))
        return map(lambda lov: KV(lov.code, lov.label), queried)

    def fullCode(self, lookedup):
        return str(lookedup.code)


class UserFileLookupSource(IdLookupSource):

    def __init__(self, type_, domain_, sub_domain_):
        self.type = type_
        self.domain = domain_
        self.sub_domain = sub_domain_

    def lookup(self, typed, **kwargs):
        queried = UserFile.objects.filter(Q(domain=self.domain, sub_domain=self.sub_domain, file__icontains=typed))
        return map(lambda f: KV("\$f%s" % unicode(f.file), "\$f%s" % unicode(f.file)), queried)

    def fullCode(self, lookedup):
        return unicode(lookedup.code)


class DesignStampingLookupSource(IdLookupSource):

    def __init__(self, type_):
        self.type = type_

    def lookup(self, query, **kwargs):
        pagesize = kwargs.get('limit', 20)
        queried = design_docs.Design.manager.find(pagesize, 0, {}, customer=kwargs.get('customer', None))
        return reduce(lambda a, b: a + b, map(lambda design: design.stamping, queried), [])

    def fullCode(self, lookedup):
        return str(lookedup.code)


class UomLookupSource(IdLookupSource):

    def __init__(self):
        self.type = 'UOM'
        super(UomLookupSource, self).__init__()

    def lookup(self, typed, **kwargs):
        pattern = '(' + typed + '|.*' + typed + '$)'
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
        result = [KV(val.code, val.label) for key, val in UOM.uoms.items() if re.match(compiled_pattern, val.code) or
                  re.match(compiled_pattern, val.label)]

        return result

    def fullCode(self, lookedup):
        return str(lookedup.code)


class IntraUserLookupSource(IdLookupSource):

    def __init__(self):
        self.type = 'USER'

    def lookup(self, typed, **kwargs):
        print("Searching user based on %s" % typed)
        queried = IntraUser.objects.filter(Q(code__icontains=typed) | Q(first_name__icontains=typed) | Q(last_name__icontains=typed))
        return map(lambda f: KV(f.code, ("%s %s" % (f.first_name if f.first_name else '', f.last_name if f.last_name else '')).strip(), info=f.id), queried)

    def fullCode(self, lookedup):
        return str(lookedup.info)


class IdLookupAPI(object):
    source = {
        'spec': [
            IntramaneeCodeLookupSource('metal', MetalCode()),
            IntramaneeCodeLookupSource('stone', StoneTypeCode()),
            IntramaneeCodeLookupSource('style', StyleCode()),
            IntramaneeCodeLookupSource('finish', FinishCode()),
            LovLookupSource('size', models.LOV.RANDD_SIZE),
            IntramaneeCodeLookupSource('plating', PlatingCode()),
        ],
        'plating': [
            IntramaneeCodeLookupSource('plating', PlatingCode()),
        ],
        'stone': [
            IntramaneeCodeLookupSource('stone', StoneTypeCode()),
        ],
        'metal': [
            IntramaneeCodeLookupSource('metal', MetalCode())
        ],
        'stock': [
            IntramaneeCodeDeepLookupSource('stock', StockCode('###'))
        ],
        'finish': [
            IntramaneeCodeLookupSource('finish', FinishCode())
        ],
        'size': [
            LovLookupSource('size', models.LOV.RANDD_SIZE)
        ],
        'stamping': [
            LovLookupSource('stamping', models.LOV.RANDD_STAMPING),
            UserFileLookupSource('stamping', 'randd', 'stamping'),
            # DesignStampingLookupSource('stamping'),
        ],
        'uom': [
            UomLookupSource()
        ],
        'material_master': [
            MaterialLookupSource()
        ],
        'sales_order': [
            SalesOrderLookupSource()
        ],
        'sales_order:open-only': [
            SalesOrderLookupSource(and_cond={
                'status': sales_docs.SalesOrder.STATUS_OPEN
            })
        ],
        'production_order': [
            ProductionOrderLookupSource()
        ],
        'production_order:active-only': [
            ProductionOrderLookupSource(and_cond={
                'status': {'$ne': production_docs.ProductionOrder.STATUS_CANCELLED}
            })
        ],
        'inv-movement-reason': [
            LovLookupSource('inv-movement-reason', 'inv-movement-reason')
        ],
        'purchase_requisition': [
            PurchaseRequisitionLookupSource(and_cond={
                'status': {'$lte': purchasing_docs.PurchaseRequisition.STATUS_PARTIAL_CONVERTED}
            })
        ],
        'user': [
            IntraUserLookupSource()
        ]
    }
    cache = {

    }
    auto_complete_source = {
        # Auto added by external parties
    }
    _instance = None

    # Singleton
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            print '\t=> initialised IdLookupAPI'
            cls._instance = super(IdLookupAPI, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def register_lookup_source(self, group, source):
        if not isinstance(source, IdLookupSource):
            raise ValueError('Unable to add non %s instance as lookup source' % type(source))
        if group not in self.source:
            self.source[group] = []
        self.source[group].append(source)

    def lookup(self, source, typed, **kwargs):
        result = []
        for src in self.source[source]:
            result += map(lambda v: {
                'code': v.code,
                'label': v.label,
                'type': src.type,
                'fullCode': src.fullCode(v),
                'info': v.info or None
            }, src.lookup(typed, **kwargs))
        return result

    def next_token(self, current, typed, limit=-1):
        TypedCode.check(current)
        code = TypedCode.translate(current, 'object')
        if code is not None:
            suggestion = []
            if len(typed) > 0 and typed[0] == '#':
                suggestion = [{'code': ''.rjust(code.length, '#'), 'label': ''.rjust(code.length, '#')}]

            suggestion.extend(map(lambda (kv): {'code': kv.code, 'label': kv.label}, code.suggest(typed, limit)))
            return {
                'suggestion': suggestion,
                'name': code.lastComp and unicode(code.lastComp) or '',
                'appendable': code.lastComp.length if code.lastComp.can_append() else 0,
                'fields': ['code', 'label']
            }
        return {}

    def add_token(self, current, content, author):
        TypedCode.check(current)
        code = TypedCode.translate(current, 'object')
        if code is None:
            raise ValidationError('current value does not match any existing code.')

        if code.lastComp is None:
            raise ValidationError('current value is already completed code.')

        if not code.lastComp.can_append:
            raise ValidationError('%s is not appendable.' % code.lastComp)

        if not {'code', 'label'} <= set(content):
            raise ValidationError('"code" and "label" are both required')

        return code.lastComp.append(content['code'], content['label'], author=author)

    def add_lov(self, group, content, author):
        # Validate required fields
        if not {'code', 'label'} <= set(content):
            raise BadParameterError('"code" and "label" are both required')

        r = models.LOV.create(group=group,
                              label=content['label'],
                              code=content['code'])
        return r.code

    def translate(self, target, terms):
        r = dict((t, {'invalid': True}) for t in terms)
        try:
            if "typed_codes" == target:
                r = self._trans_typecode(terms)
            elif "user_object" == target:
                users = IntraUser.objects.filter(id__in=map(ObjectId, terms))
                found = dict((str(u.id), {'invalid': False, 'code': u.code, 'first_name': u.first_name, 'last_name': u.last_name}) for u in users)
                r.update(found)
            elif "LOV:" == target[:4]:
                lov = models.LOV.objects.filter(Q(group=target[4:]) & Q(code__in=terms))
                found = dict((unicode(u.code), {'invalid': False, 'code': u.code, 'label': u.label}) for u in lov)
                r.update(found)
            elif "material_object" == target:
                pass
            else:
                pass
        except Exception as e:
            def append_error(o):
                if o.invalid:
                    o.error = str(e)
                return o
            r = map(append_error, r)
        return target, r

    def extract(self, code):
        return map(lambda (k): {'code': k[1], 'label': k[2]}, TypedCode.translate(code, 'extract'))

    def register_auto_complete_source(self, source_name, source_callable):
        if source_name in self.auto_complete_source:
            raise ValidationError('auto complete source %s already exists' % source_name)
        self.auto_complete_source[source_name] = source_callable

    def auto_complete(self, typed, source, source_parameters):
        if source not in self.auto_complete_source:
            raise ValidationError('unknown auto complete source "%s"' % typed)
        self.auto_complete_source[source].lookup(typed, source_parameters)

    def _trans_typecode(self, codes):

        def fmt(k):
            o = {}
            try:
                o['label'] = TypedCode.translate(k, 'label')
                o['invalid'] = False
            except ValidationError as e:
                o['error'] = e.message
                o['invalid'] = True

            return k, o
        return dict(map(fmt, codes))


class CRUDApi(object):

    @classmethod
    def delete(cls, user, model_name, pk):
        """

        :param user:
        :param model_name:
        :return:
        """
        clz = cls.document_model_factory(model_name)
        user.can("%s+delete" % clz.manager.collection_name, None, True)   # Validate User Permission

        return clz.manager.delete(cond={
            '_id': ObjectId(pk)
        })

    def write(self, user, model_name, contents, options):
        """
        Request a database write operation to the given model
        :param user:
        :param model_name:
        :param contents:
        :param options:
        :return:
        """
        # self.validate_permission('write', user, model_name)
        invocations = options.pop('invocations', [])

        if contents is None:
            raise ValidationError("Content is required")

        if not isinstance(invocations, list):
            raise BadParameterError("Invocations must be array")

        def perform_write(content):
            document_id = None
            if '_id' in content:
                if content['_id'] is not None:
                    document_id = ObjectId(content['_id'])
                del content['_id']

            clz = CRUDApi.document_model_factory(model_name)
            d = clz(document_id)
            d.deserialized(content)
            if len(invocations) > 0:
                list(d.invoke(user, f) for f in invocations)
            d.touched(user)
            return d

        if isinstance(contents, list):
            return map(perform_write, contents)
        return perform_write(contents)

    @classmethod
    def sync(cls, content):
        """

        :param content: array of dict {model, object_id, last_edited.object_id}
        :return: array of dict {model, object_id, content}
        """
        if content is None or not isinstance(content, list):
            raise ValidationError("Content list is required")

        _fs_holders = {}

        def get_fs_holder(model_name, id):
            if model_name not in _fs_holders:
                _fs_holders[model_name] = CRUDApi.document_model_factory(model_name)
            return _fs_holders[model_name](id)

        result = []

        for con in content:
            model = con.pop('model', None)
            if model is None:
                raise ValidationError("Model is required")

            id = con.pop('id', None)
            if id is None:
                raise ValidationError("id is required")

            last_edited = con.pop('last_edited', None)
            if last_edited is None:
                raise ValidationError("last_edited is required")

            fs_holder = get_fs_holder(model, id)
            fs = fs_holder.fieldspec('last_edited')
            doc_last_edited = fs.from_serialized(last_edited)
            if doc_last_edited != fs_holder.last_edited:
                result.append({'model': model, 'id': id, 'content': fs_holder.serialized()})

        return result

    @classmethod
    def update(cls, user, content):
        if content is None or not isinstance(content, list):
            raise ValidationError("Content list is required")

        _fs_holders = {}

        def get_fs_holder(model_name, id):
            if model_name not in _fs_holders:
                _fs_holders[model_name] = CRUDApi.document_model_factory(model_name)
            return _fs_holders[model_name](id)

        def merge_conditions(prev, con):
            model = con.pop('model', None)
            if model is None:
                raise ValidationError("Model is required")
            if model not in prev:
                prev[model] = []

            content_buffer = {
                'cond': {'_id': ObjectId(con.pop('id'))},
            }

            fs_holder = get_fs_holder(model, content_buffer['cond']['_id'])
            for k, v in con.iteritems():
                fs = fs_holder.fieldspec(k)
                if fs is None:
                    raise ValidationError('%s is not a fieldspec' % k)
                v = fs.from_serialized(v)
                con[k] = fs.to_document(v)

            content_buffer['content'] = con

            if hasattr(fs_holder.__class__, 'last_edited'):
                content_buffer.update({'event': fs_holder})
            prev[model].append(content_buffer)
            return prev

        def execute(content):
            for model_name, c in reduce(merge_conditions, content, {}).iteritems():
                yield CRUDApi.document_model_factory(model_name).manager.update(user, c)

        return list(execute(content))

    def read_one(self, user, model_name, pk, **kwargs):
        kwargs['query'] = {'_id': ObjectId(pk)}
        docs = self.read(user, model_name, 1, 0, **kwargs)
        return len(docs) > 0 and docs[0] or None

    def read(self, user, model_name, pagesize, page, **kwargs):
        """
        Request a database read operation to a given model, kwargs will supply
        additional flags that could drive what will happen to search result.

        kwargs may also convey the Query parameter.
        :param user:
        :param model_name:
        :param pagesize:
        :param page:
        :param kwargs:
        :return:
        """
        clz = self.document_model_factory(model_name)
        user.can("%s+read" % clz.manager.collection_name, None, True)   # Validate User Permission
        flags = self.validate_read_flags(clz, **kwargs)
        if flags['latest_revision_only']:
            docs = clz().list_latest_revisions(pagesize, page)
        elif flags['production_end_today']:
            docs = clz.manager.find(pagesize, page, {'status': {'$lt': 5}, '$or': [{'actual_end': {'$eq': None}}, {'$and': [{'actual_end': {'$ne': None}}, {'actual_end': {'$gt': datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)}}]}]})
        else:
            query = kwargs.get('query', {})
            print query
            docs = clz.manager.find(pagesize, page, cond=query)
        return map(flags['each_result'], docs)

    def count(self, user, model_name, **kwargs):
        clz = CRUDApi.document_model_factory(model_name)
        user.can("%s+read" % clz.manager.collection_name, None, True)   # Validate User Permission
        flags = self.validate_read_flags(clz, **kwargs)
        if flags['latest_revision_only']:
            return clz().revisions_count()
        return clz.manager.count(**kwargs)

    @staticmethod
    def validate_read_flags(klass, **kwargs):
        latest_revision_only = kwargs.pop("latest_revision_only", False)
        with_schematic = kwargs.pop("with_schematic", False)
        validate_errors = kwargs.pop("validate_errors", False)
        resolve_design_uid = kwargs.pop("resolve_design_uid", False)
        production_end_today = kwargs.pop("production_end_today", False)

        if latest_revision_only and not issubclass(klass, Revisioned):
            raise BadParameterError("model %s doesn't support latest_revision_only flag." % str(klass))

        # Customisation by flags
        pipeline = []
        if issubclass(klass, Authored):
            pipeline.append(lambda d: d.populate('last_edited.who').populate('created_by'))

        if with_schematic and issubclass(klass, MaterialMaster):
            pipeline.append(lambda d: d.populate('schematic'))

        if validate_errors and issubclass(klass, Validatable):
            pipeline.append(lambda d: d.validate_data(throw=False))

        if resolve_design_uid and issubclass(klass, design_docs.Design):
            pipeline.append(lambda d: d.populate('design_code'))

        if issubclass(klass, production_docs.ProductionOrder):
            pipeline.append(lambda d: d.populate('operation'))

        pipeline.append(lambda d: d.serialized())

        return {
            'latest_revision_only': latest_revision_only,
            'production_end_today': production_end_today,
            'each_result': lambda d: reduce(lambda o, f: f(o), pipeline, d)
        }

    @staticmethod
    def document_model_factory(model_name):
        """
        :param model_name:
        :return: appropriate class for given model_name
        """

        try:
            return Docs.factory_doc(model_name)
        except ProhibitedError:
            raise BadParameterError('Unknown model_name="%s"' % model_name)


class DocumentHelperApi(object):
    """
    Helper API for all type of documents
    """
    @staticmethod
    def next_revision(model_name, rev_unique_id):
        return DocumentHelperApi.revision_document_factory(model_name)().next_revision_id(rev_unique_id)

    @staticmethod
    def list_revision(model_name, rev_unique_id):
        return DocumentHelperApi.revision_document_factory(model_name)().list_revision_ids(rev_unique_id)

    @staticmethod
    def revision_document_factory(model_name):
        model = CRUDApi.document_model_factory(model_name)
        if not issubclass(model, Revisioned):
            raise ('Invalid model "%s" is not Revisioned' % model_name)
        return model

    @staticmethod
    def material_revisions(material_code):
        """
        Material + Schematic Helper - list material's schematic variations from material_code

        :param string material_code:
        :return dict:
        """
        mm = MaterialMaster.get(material_code)

        return map(lambda a: {
            'rev_id': a.rev_id,
            'conf_size': a.conf_size,
            'schematic_id': a.object_id,
            'default': (mm.schematic == a.object_id)
        }, mm.revisions())
