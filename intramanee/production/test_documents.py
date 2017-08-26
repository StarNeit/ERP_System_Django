__author__ = 'wasansae-ngow'

from unittest import TestCase
from intramanee.production import documents as prod
from intramanee.production.test_utils import ProductionFixture
from intramanee.randd import documents as randd
from intramanee.task import documents as tasks
from intramanee.stock import documents as stock
from intramanee.sales import documents as sales
from intramanee.common.task import Task
from intramanee.common.models import IntraUser
from intramanee.common.location import Location
from intramanee.common.calendar import documents as cal
from intramanee.common.utils import NOW, print_verbose
from bson import ObjectId
import datetime


class ProductionTest(TestCase):

    utils = ProductionFixture()

    def __init__(self, _method_name='testCreateProductionOrder'):
        super(ProductionTest, self).__init__(_method_name)
        self.tester = self.utils.tester

    @classmethod
    def setUpClass(cls):
        super(ProductionTest, cls).setUpClass()
        cls.utils.grant_full_access(cls.utils.tester)
        cls.utils.tester.save()
        cls.utils.prepare_raw_mat_stock(cls.utils.tester)

    @classmethod
    def create_material_movement(cls, movement_type, items, ref_doc=None):
        mv = stock.InventoryMovement()
        mv.type = movement_type
        mv.ref_doc = ref_doc
        mv.touched(cls.utils.tester)

        return mv

    @classmethod
    def tearDownClass(cls):
        super(ProductionTest, cls).tearDownClass()
        cls.utils.teardown()

    def testCreateProductionOrder(self, **kwargs):
        return self.utils.create_production_orders(**kwargs)
        # FIXME: Asserts

    def test_group_operation(self, **kwargs):
        orders = self.testCreateProductionOrder(**kwargs)
        operations = [op for order in orders for op in order.operation]
        op_list = [op.object_id for op in operations if op.task.code == 5291]

        group = prod.ProductionGroupedOperation()
        group.invoke_set_operation(self.tester, op_list)
        group.invoke_set_type(self.tester, prod.ProductionGroupedOperation.TYPE_PLAN)
        print("group object id %s created" % group.object_id)

        op_list = [op.object_id for op in operations if op.task.code == 5331][1:]

        group = prod.ProductionGroupedOperation()
        group.invoke_set_operation(self.tester, op_list)
        group.invoke_set_type(self.tester, prod.ProductionGroupedOperation.TYPE_PLAN)
        print("group object id %s created" % group.object_id)

        op_list = [op.object_id for op in operations if op.task.code == 5391][4:]

        group = prod.ProductionGroupedOperation()
        group.invoke_set_operation(self.tester, op_list)
        group.invoke_set_type(self.tester, prod.ProductionGroupedOperation.TYPE_PLAN)
        print("group object id %s created" % group.object_id)

    def test_automate_group(self, **kwargs):
        orders = self.testCreateProductionOrder(testing=False, **kwargs)
        operations = [op.object_id for order in orders for op in order.operation]
        prod.ProductionGroupedOperation.automate_group(self.tester, True, testing={'created_by': ObjectId(self.tester.id),
                                                                                   '_id': {'$in': operations}})

    def test_clear_all(self):
        self.test_group_operation()
        prod.ProductionGroupedOperation.clear_all(self.tester, True, testing={'created_by': ObjectId(self.tester.id)})

    def test_confirm_prod(self):
        orders = self.testCreateProductionOrder()
        order = orders[0]
        order.populate('operation')

        def assign(o):
            o.assignee = self.tester
            o.touched(self.tester)

        map(assign, order.operation)

        order.release(self.tester)

        for o in order.operation:
            conf = prod.ProductionConfirmation.create(o.get_confirmable_quantity(), 0, [], None,
                                                      actual_start=NOW(),
                                                      actual_duration=5,
                                                      actual_end=NOW(),
                                                      assignee=self.tester)
            o.confirm(self.tester, conf)
            self.assertEqual(o.status, prod.ProductionOrderOperation.STATUS_CONFIRMED)

        self.assertEqual(order.status, prod.ProductionOrder.STATUS_CONFIRMED)

    def test_scheduler(self):
        start_period = datetime.datetime(2015, 1, 1)

        # offhour from 1/10 18:00 to 2/10 8:00
        off = cal.OffHoursRange()
        off.start = datetime.datetime(2015, 10, 1, 18)
        off.end = datetime.datetime(2015, 10, 2, 8)

        # offhour from 2/10 18:00 to 5/10 8:00
        off1 = cal.OffHoursRange()
        off1.start = datetime.datetime(2015, 10, 2, 18)
        off1.end = datetime.datetime(2015, 10, 5, 8)

        # offhour from 5/10 18:00 to 6/10 8:00
        off2 = cal.OffHoursRange()
        off2.start = datetime.datetime(2015, 10, 5, 18)
        off2.end = datetime.datetime(2015, 10, 6, 8)

        # offhour from 6/10 18:00 to 7/10 8:00
        off3 = cal.OffHoursRange()
        off3.start = datetime.datetime(2015, 10, 6, 18)
        off3.end = datetime.datetime(2015, 10, 7, 8)

        # 13 hours starting from 6:00 Friday 2nd Oct to 19:00 Friday 2nd Oct
        # Working time is 8:00 to 18:00 on weekday - 10 hours
        # Saturday 3rd Oct and Sunday 4th Oct are weekend
        d1 = datetime.datetime(2015, 10, 2, 6)
        d2 = datetime.datetime(2015, 10, 2, 19)

        expected_forward_start = datetime.datetime(2015, 10, 2, 8)
        expected_forward_end = datetime.datetime(2015, 10, 5, 11)

        expected_backward_start = datetime.datetime(2015, 10, 1, 15)
        expected_backward_end = datetime.datetime(2015, 10, 2, 18)

        sc = prod.Scheduler(start_period, start_period)
        sc.off_hours = [
            off,
            off1,
            off2,
            off3
        ]

        result1 = sc.get_start_end_forward(d1, d2, False)
        # Get new end will move start time to working time
        self.assertEqual(result1.start, expected_forward_start, "Forward: New start time should be 8:00 on 2/10/2015")
        self.assertEqual(result1.end, expected_forward_end, "Forward: New end time should be 11:00 on 5/10/2015")

        result2 = sc.get_start_end_backward(d1, d2, False)
        self.assertEqual(result2.start, expected_backward_start, "Forward: New start time should be 15:00 on 1/10/2015")
        self.assertEqual(result2.end, expected_backward_end, "Forward: New end time should be 18:00 on 2/10/2015")


def group_operation(user=None):
    # create sample group cast
    operations = prod.ProductionOrderOperation.manager.find(0, 0, {'task': 5331})
    if not operations:
        print('No cast operation found')
        quit()

    if len(operations) < 2:
        print('Not enough cast operations to group')
        quit()

    group = prod.ProductionGroupedOperation()
    group.invoke_set_operation()


def create_test_production_order(user=None):
    # get material with procurement type 'I'
    i_material = stock.MaterialMaster.manager.find(20, 0, {'procurement_type': 'I'})
    e_material = stock.MaterialMaster.manager.find(20, 0, {'procurement_type': 'E'})

    if len(i_material) < 1:
        print('No internal produced material')
        quit()

    p = prod.ProductionOrder()
    o = prod.ProductionOrderOperation()
    o2 = prod.ProductionOrderOperation()
    c = prod.ProductionOrderComponent()
    c2 = prod.ProductionOrderComponent()

    p.material = i_material[0].code
    p.revision = i_material[0].revisions()[0].rev_id
    p.uom = i_material[0].uom
    p.quantity = 4
    p.planned_start = datetime.datetime(9999, 1, 1)

    if i_material[0].revisions()[0].conf_size:
        p.size = i_material[0].revisions()[0].conf_size[0]

    o.id = '10'
    o.task = Task.factory('4143')

    o2.id = '20'
    o2.task = Task.factory('5331')

    if len(e_material) < 1:
        print('No external produced material')
        quit()

    c.material = e_material[0].code
    c.uom = e_material[0].uom
    c.quantity = -2

    c2.material = e_material[1].code
    c2.uom = e_material[1].uom
    c2.quantity = -3

    o.materials = [c]
    o2.materials = [c2]

    o2.source = [o]

    p.operation = [o, o2]

    u = IntraUser.objects.all()[0] if user is None else user

    p.touched(u)

    return p


def test_confirmation(**kwargs):

    user = kwargs.pop("user", None)
    production = kwargs.pop("prod", None)
    operation = kwargs.pop("op", None)
    qty = kwargs.pop("qty", None)
    scrap = kwargs.pop("scrap", None)

    e_material = stock.MaterialMaster.manager.find(20, 0, {'procurement_type': 'E'})

    if production:
        list_prod = prod.ProductionOrder.manager.find(100, 0, {'doc_no': production})
    else:
        list_prod = prod.ProductionOrder.manager.find(100, 0)

    if not list_prod:
        print('No production order found')
        quit()

    if operation:
        op = prod.ProductionOrderOperation(list_prod[0].operation[operation])
    else:
        op = prod.ProductionOrderOperation(list_prod[0].operation[0])

    conf = prod.ProductionConfirmation()
    conf.confirm_yield = qty if qty else 1
    conf.scrap = scrap if scrap else 0

    mv = stock.InventoryMovement()
    mvi = stock.InventoryMovementEntry()

    mv.type = 201
    mv.ref_doc = list_prod[0]
    # doc_no = doc.FieldString(none=True)     # Running Number
    # type = doc.FieldNumeric(choices=TYPES)
    # cancel = doc.FieldDoc('inv_movement', none=True, unique=True, omit_if_none=True)
    # ref_ext = doc.FieldString(none=True)
    # ref_doc = doc.FieldString(none=True)
    # posting_date = doc.FieldDateTime(none=True)
    # items = doc.FieldList(doc.FieldNested(InventoryMovementEntry))

    mvi.material = e_material[0].code
    mvi.quantity = -3
    mvi.location = Location.locations['STORE'].code

    invc = stock.InventoryContent.manager.find(1, 0, {'material': unicode(e_material[0].code), 'quantity': {'$gt': 0}})

    mvi.batch = invc[0].batch
    mvi.value = (invc[0].value / invc[0].quantity) * mvi.quantity
    mvi.weight = invc[0].weight

    mv.items = [mvi]

    # material = doc.FieldTypedCode(codes.StockCode, none=False)
    # quantity = doc.FieldNumeric(default=1, none=False)
    # batch = doc.FieldString()           # Assigned from InventoryMovementInstance
    # value = doc.FieldNumeric()
    # weight = doc.FieldNumeric()
    # location = doc.FieldString(default=Location.locations['STORE'].code, none=False)
    # ref_doc = doc.FieldString(none=True)     # For production order only
    # reason = doc.FieldString(lov=MOVEMENT_LOV_KEY, none=True)

    u = IntraUser.objects.all()[0] if user is None else user

    op.confirm_operation(u, conf, [mv])

    # def confirm_operation(self, user, confirmation, movement=None):

    # actual_start = doc.FieldDateTime(none=True)
    # actual_duration = doc.FieldNumeric(none=True)
    # actual_end = doc.FieldDateTime(none=True)
    # created_by = doc.FieldIntraUser()
    # created_on = doc.FieldDateTime()
    # cancel = doc.FieldBoolean
    # cancel_by = doc.FieldIntraUser()
    # cancel_on = doc.FieldDateTime()
    # Assignee = doc.FieldIntraUser()
