from dateutil.relativedelta import relativedelta
from datetime import datetime
import time
from intramanee.production import documents as prod
from intramanee.stock.test_utils import StockFixture
from intramanee.stock import documents as stock
from intramanee.sales import documents as sales
from intramanee.randd import documents as randd
from intramanee.task import documents as tasks
from intramanee.production import documents as prod
from intramanee.common.task import Task
from bson import ObjectId


class ProductionFixture(StockFixture):

    def __init__(self):
        super(ProductionFixture, self).__init__()
        self.raw_mat = [
            self.ensure_material_exists("011SILVACTIVX", 'g'),
            self.ensure_material_exists("011SILV660LVL", 'g')
        ]

    @staticmethod
    def grant_full_access(user):
        base_actions = ['write', 'read', 'delete']

        def grant_access(u, collection, base, options=None):
            for b in base:
                perm = str(collection) + '+' + str(b)
                if options:
                    for o in options:
                        permo = perm + '@' + str(o)
                        if permo not in u.permissions:
                            u.permissions.append(permo)
                else:
                    if perm not in u.permissions:
                        u.permissions.append(perm)

        grant_access(user, prod.ProductionOrder.Meta.collection_name, base_actions)
        grant_access(user, stock.InventoryMovement.Meta.collection_name, base_actions, [k[0] for k in stock.InventoryMovement.TYPES])
        grant_access(user, tasks.TaskDoc.Meta.collection_name, base_actions, Task.get_task_list())
        grant_access(user, randd.Design.Meta.collection_name, base_actions, ["approve"])
        grant_access(user, sales.SalesOrder.Meta.collection_name, base_actions)

    def prepare_raw_mat_stock(self, user, raw_mat=None, quantity=None):
        if not raw_mat:
            raw_mat = self.raw_mat

        if not quantity:
            quantity = 100

        raw_movement = []

        def validate(m):
            if not isinstance(m, stock.MaterialMaster):
                m = stock.MaterialMaster.get(m)
            raw_movement.append({
                'material': str(m.code),
                'location': 'STORE',
                'quantity': quantity,
                'value': quantity * 100,
                'weight': quantity * 10,
            })

        map(validate, raw_mat)

        def convert_movement(m):
            r = stock.InventoryMovementEntry()
            r.deserialized(m)
            return r

        mv_items = map(convert_movement, raw_movement)

        if mv_items:
            self.create_material_movement(user, stock.InventoryMovement.GR_PR, mv_items)

    @classmethod
    def create_material_movement(cls, user, movement_type, items, ref_doc=None):
        mv = stock.InventoryMovement()
        mv.type = movement_type
        mv.ref_doc = ref_doc
        mv.items = items
        mv.touched(user)

        return mv

    @classmethod
    def assign_all(cls, order, assignee, user):
        """

        :param prod.ProductionOrder order:
        :param IntraUser assignee:
        :param IntraUser user:
        :return:
        """
        def assign(op):
            op.assignee = assignee
            op.touched(user)

        order.populate('operation')
        map(assign, order.operation)

    @classmethod
    def create_production_order(cls, material, user, revision=None, quantity=None, start=None):
        if not material:
            raise ValueError

        start = datetime.today() - relativedelta(months=3)
        end = datetime.today() + relativedelta(months=6)
        scheduler = prod.Scheduler(start, end)

        order = prod.ProductionOrder()
        order.material = material.code
        order.quantity = quantity
        order.uom = material.uom
        order.revision = revision
        order.planned_start = start if start else datetime.today()
        order.read_bom()
        order.schedule_order(True, scheduler)
        order.touched(user)
        return order

    def teardown(self):
        super(ProductionFixture, self).teardown()
        prod.ProductionOrder.manager.delete(cond={
            'material': {'$regex': '^stock-%s' % self.COMP_CODE}
        }, verbose=True)
        prod.ProductionGroupedOperation.manager.delete(cond={
            'created_by': ObjectId(self.tester.id)
        }, verbose=True)

    def create_production_orders(self, verbose=True, **kwargs):

        testing = kwargs.pop("testing", True)
        number = kwargs.pop("number", 7)

        results = []

        finished_material_schematic = [
            {
                'id': '1',
                'process': 5291,
                'labor_cost': 11,
                'markup': 20.0,
                'is_configurable': False,
                'source': [],
                'materials': [],
                'duration': [0.1],
                'staging_duration': [5]
            },
            {
                'id': 2,
                'process': 5331,
                'labor_cost': 13,
                'markup': 5.0,
                'is_configurable': False,
                'source': ['1'],
                'materials': [
                    {
                        'code': str(self.raw_mat[0].code),
                        'quantity': [5],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    },
                    {
                        'code': str(self.raw_mat[1].code),
                        'quantity': [3],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    },
                ],
                'duration': [1440],
                'staging_duration': [5]
            },
            {
                'id': 3,
                'process': 5462,
                'labor_cost': 29,
                'markup': 5.0,
                'is_configurable': False,
                'source': ['1'],
                'materials': [
                    {
                        'code': str(self.raw_mat[0].code),
                        'quantity': [5],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    },
                    {
                        'code': str(self.raw_mat[1].code),
                        'quantity': [3],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    },
                ],
                'duration': [5],
                'staging_duration': [5]
            },
            {
                'id': 4,
                'process': 5391,
                'labor_cost': 11,
                'markup': 21.0,
                'is_configurable': False,
                'source': ['2', '3'],
                'materials': [],
                'duration': [5],
                'staging_duration': [5]
            }
        ]
        finished_code = "180G999BL29999HPBE"
        revision = 20

        finished_material_schematic2 = [
            {
                'id': '1',
                'process': 5291,
                'labor_cost': 11,
                'markup': 20.0,
                'is_configurable': False,
                'source': [],
                'materials': [],
                'duration': [0.1],
                'staging_duration': [5]
            },
            {
                'id': 2,
                'process': 5331,
                'labor_cost': 13,
                'markup': 5.0,
                'is_configurable': False,
                'source': ['1'],
                'materials': [
                    {
                        'code': str(self.raw_mat[0].code),
                        'quantity': [5],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    },
                    {
                        'code': str(self.raw_mat[1].code),
                        'quantity': [3],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    },
                ],
                'duration': [1440],
                'staging_duration': [5]
            },
            {
                'id': 3,
                'process': 5462,
                'labor_cost': 29,
                'markup': 5.0,
                'is_configurable': False,
                'source': ['1'],
                'materials': [
                    {
                        'code': str(self.raw_mat[0].code),
                        'quantity': [5],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    },
                    {
                        'code': str(self.raw_mat[1].code),
                        'quantity': [3],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    },
                ],
                'duration': [10],
                'staging_duration': [5]
            },
            {
                'id': 4,
                'process': 5391,
                'labor_cost': 11,
                'markup': 21.0,
                'is_configurable': False,
                'source': ['2', '3'],
                'materials': [],
                'duration': [12],
                'staging_duration': [5]
            }
        ]
        finished_code2 = "180G999BL19999HPBE"
        revision2 = 20

        finished_material = self.ensure_180_exists(finished_code, finished_material_schematic, revision, verbose)
        finished_material2 = self.ensure_180_exists(finished_code2, finished_material_schematic2, revision2, verbose)

        start = datetime.today() - relativedelta(months=3)
        end = datetime.today() + relativedelta(months=6)
        scheduler = prod.Scheduler(start, end)

        start_time = time.time()
        order = prod.ProductionOrder()
        order.material = finished_material.code
        order.quantity = 40
        order.uom = 'pc'
        order.revision = 20
        if testing:
            order.planned_start = datetime(2016, 1, 14, 6)
        else:
            order.planned_start = datetime.today().replace(hour=6, minute=0, second=0, microsecond=0)
        order.read_bom()
        order.schedule_order(True, scheduler)
        order.touched(self.tester)
        results.append(order)
        if verbose:
            print("--- %s seconds ---" % (time.time() - start_time))
            print("order %s created with objectid: %s." % (order.doc_no, order.object_id))

        if number == 1:
            return results

        start_time = time.time()
        order = prod.ProductionOrder()
        order.material = finished_material.code
        order.quantity = 100
        order.uom = 'pc'
        order.revision = 20
        if testing:
            order.planned_start = datetime(2016, 1, 14, 10)
        else:
            order.planned_start = datetime.today().replace(hour=10, minute=0, second=0, microsecond=0)
        order.read_bom()
        order.schedule_order(True, scheduler)
        order.touched(self.tester)
        results.append(order)
        if verbose:
            print("--- %s seconds ---" % (time.time() - start_time))
            print("order %s created with objectid: %s." % (order.doc_no, order.object_id))

        if number == 2:
            return results

        start_time = time.time()
        order = prod.ProductionOrder()
        order.material = finished_material.code
        order.quantity = 100
        order.uom = 'pc'
        order.revision = 20
        if testing:
            order.planned_start = datetime(2016, 1, 14, 13)
        else:
            order.planned_start = datetime.today().replace(hour=13, minute=0, second=0, microsecond=0)
        order.read_bom()
        order.schedule_order(True, scheduler)
        order.touched(self.tester)
        results.append(order)
        if verbose:
            print("--- %s seconds ---" % (time.time() - start_time))
            print("order %s created with objectid: %s." % (order.doc_no, order.object_id))

        if number == 3:
            return results

        start_time = time.time()
        order = prod.ProductionOrder()
        order.material = finished_material2.code
        order.quantity = 80
        order.uom = 'pc'
        order.revision = 20
        if testing:
            order.planned_start = datetime(2016, 1, 14, 15)
        else:
            order.planned_start = datetime.today().replace(hour=15, minute=0, second=0, microsecond=0)
        order.read_bom()
        order.schedule_order(True, scheduler)
        order.touched(self.tester)
        results.append(order)
        if verbose:
            print("--- %s seconds ---" % (time.time() - start_time))
            print("order %s created with objectid: %s." % (order.doc_no, order.object_id))

        if number == 4:
            return results

        start_time = time.time()
        order = prod.ProductionOrder()
        order.material = finished_material2.code
        order.quantity = 70
        order.uom = 'pc'
        order.revision = 20
        if testing:
            order.planned_start = datetime(2016, 1, 14, 16)
        else:
            order.planned_start = datetime.today().replace(hour=16, minute=0, second=0, microsecond=0)
        order.read_bom()
        order.schedule_order(True, scheduler)
        order.touched(self.tester)
        results.append(order)
        if verbose:
            print("--- %s seconds ---" % (time.time() - start_time))
            print("order %s created with objectid: %s." % (order.doc_no, order.object_id))

        if number == 5:
            return results

        start_time = time.time()
        order = prod.ProductionOrder()
        order.material = finished_material2.code
        order.quantity = 60
        order.uom = 'pc'
        order.revision = 20
        if testing:
            order.planned_start = datetime(2016, 1, 14, 17)
        else:
            order.planned_start = datetime.today().replace(hour=17, minute=0, second=0, microsecond=0)
        order.read_bom()
        order.schedule_order(True, scheduler)
        order.touched(self.tester)
        results.append(order)
        if verbose:
            print("--- %s seconds ---" % (time.time() - start_time))
            print("order %s created with objectid: %s." % (order.doc_no, order.object_id))

        if number == 6:
            return results

        start_time = time.time()
        order = prod.ProductionOrder()
        order.material = finished_material2.code
        order.quantity = 60
        order.uom = 'pc'
        order.revision = 20
        if testing:
            order.planned_start = datetime(2016, 1, 14, 17)
        else:
            order.planned_start = datetime.today().replace(hour=17, minute=0, second=0, microsecond=0)
        order.read_bom()
        order.schedule_order(True, scheduler)
        order.touched(self.tester)
        results.append(order)
        if verbose:
            print("--- %s seconds ---" % (time.time() - start_time))
            print("order %s created with objectid: %s." % (order.doc_no, order.object_id))

        if number == 7:
            return results

        return results
