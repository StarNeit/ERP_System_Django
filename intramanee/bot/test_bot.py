from unittest import TestCase
from bson import ObjectId
from datetime import datetime, timedelta, time
from time import sleep
from dateutil.relativedelta import relativedelta

from intramanee.common.codes import CustomerCode
from intramanee.production import documents as prod_doc
from intramanee.stock import documents as stock_doc
from intramanee.sales import documents as sales_doc
from intramanee.bot.documents import MRPSession

from intramanee.stock.test_utils import Step, StepComponent
from intramanee.production.test_utils import ProductionFixture


class BotFixture(ProductionFixture):

    def __init__(self, verbose=False):
        super(BotFixture, self).__init__()
        # Raw Materials
        self.raw_mat_1 = self.ensure_material_exists("011SILVACTIVX", 'g',
                                                     lot_size=stock_doc.MaterialMaster.LZ_WEEKLY,
                                                     scrap_percentage=0.05)
        self.raw_mat_2 = self.ensure_material_exists("011SILV660LVL", 'g',
                                                     gr_processing_time=0,
                                                     lot_size=stock_doc.MaterialMaster.LZ_DAILY,
                                                     lot_size_min=50,
                                                     lot_size_max=100)
        self.raw_mat_3 = self.ensure_material_exists("011G999660LVL", 'g',
                                                     gr_processing_time=1440,
                                                     lot_size=stock_doc.MaterialMaster.LZ_LOT_FOR_LOT,
                                                     lot_size_min=100,
                                                     lot_size_max=400)
        self.raw_mat_4 = self.ensure_material_exists("011SILV660BRI", 'g',
                                                     mrp_type=stock_doc.MaterialMaster.NO_MRP)

        # Mold #1
        mold_step_1 = Step(5291, [0.1], [5])
        mold_step_2 = Step(5331, [1440], [5]) << [
            StepComponent(self.raw_mat_1.code, [5], 'g', 100),
        ]
        mold_step_3 = Step(5462, [10], [3])

        mold_step_1.then(mold_step_2)
        mold_step_2.then(mold_step_3)

        self.mold_1 = self.ensure_mold_exists("021G999M00002",
                                              Step.build_schematic_dict(mold_step_1),
                                              scrap_percentage=0.05)

        # Finish Good #1
        fg1_step_1 = Step(5291, [0.1], [5]) << [
            StepComponent(self.mold_1.code, [1], 'pc', 100)
        ]
        fg1_step_2 = Step(5331, [1440], [5]) << [
            StepComponent(self.raw_mat_1.code, [5], 'g', 300),
            StepComponent(self.raw_mat_4.code, [3], 'g', 300)
        ]
        fg1_step_3 = Step(5391, [5], [5]) << [
            StepComponent(self.raw_mat_1.code, [1], 'g', 300),
            StepComponent(self.raw_mat_2.code, [3], 'g', 300)
        ]
        fg1_step_4 = Step(5462, [5], [5])

        fg1_step_1.then(fg1_step_2, fg1_step_3)
        fg1_step_2.then(fg1_step_4)
        fg1_step_3.then(fg1_step_4)

        # Finish Good #2
        fg2_step_1 = Step(5291, [0.1], [5])
        fg2_step_2 = Step(5331, [1440], [5]) << [
            StepComponent(self.raw_mat_2.code, [5], 'g', 300),
        ]
        fg2_step_3 = Step(5391, [10], [5]) << [
            StepComponent(self.raw_mat_3.code, [5], 'g', 300),
        ]
        fg2_step_4 = Step(5462, [12], [5])

        fg2_step_1.then(fg2_step_2, fg2_step_3)
        fg2_step_2.then(fg2_step_4)
        fg2_step_3.then(fg2_step_4)

        # Create finished material exists.
        self.finished_material = self.ensure_180_exists("180G999BL29999HPBE", Step.build_schematic_dict(fg1_step_1), 20, verbose)
        self.finished_material2 = self.ensure_180_exists("180G999BL19999HPBE", Step.build_schematic_dict(fg2_step_1), 20, verbose)

        # Ensure inventory content
        self.ensure_inventory_content_quantity(self.raw_mat_1, 300)
        self.ensure_inventory_content_quantity(self.raw_mat_2, 400)
        self.ensure_inventory_content_quantity(self.raw_mat_3, 500)

        # Grant sales_order write access to tester
        self.ensure_tester_permission('sales_order+write')

    def teardown(self):
        super(BotFixture, self).teardown()
        prod_doc.ProductionOrder.manager.delete(cond={
            'material': {'$regex': '^stock-%s' % self.COMP_CODE}
        }, verbose=True)
        prod_doc.ProductionGroupedOperation.manager.delete(cond={
            'created_by': ObjectId(self.tester.id)
        }, verbose=True)
        sales_doc.SalesOrder.manager.delete(cond={
            'created_by': ObjectId(self.tester.id)
        })
        stock_doc.InventoryContent.manager.delete(cond={
            'batch': {'$regex': '^TESTMV'}
        })

    def create_sales_orders(self, material, revision, quantity, deliver_in, verbose=True):
        if not isinstance(deliver_in, timedelta):
            raise ValueError('deliver_in must be instance of timedelta')

        # prepare items
        o = sales_doc.SalesOrder()
        o.customer = CustomerCode(self.COMP_CODE)
        midnight = datetime.combine(datetime.today().date(), time(0, 0, 0, 0))
        o.delivery_date = midnight + deliver_in
        o.status = sales_doc.SalesOrder.STATUS_OPEN
        o.add_entry(
            material=material.code,
            revision=revision,
            size=None,
            quantity=quantity,
            uom='pc',
            net_price=40000
        )
        o.touched(self.tester)

    def create_production_orders(self, material, revision, quantity, start_in, verbose=False):
        if not isinstance(start_in, timedelta):
            raise ValueError('deliver_in must be instance of timedelta')

        # Create existing production orders.
        start = datetime.today() - relativedelta(months=3)
        end = datetime.today() + relativedelta(months=6)
        scheduler = prod_doc.Scheduler(start, end)

        midnight = datetime.combine(datetime.today().date(), time(0, 0, 0, 0))

        order = prod_doc.ProductionOrder()
        order.material = material.code
        order.quantity = quantity
        order.uom = 'pc'
        order.revision = revision
        order.planned_start = midnight + start_in

        # enclose
        order.read_bom()
        order.schedule_order(True, scheduler)
        self.assign_all(order, self.tester, self.tester)
        order.release(self.tester)


class BotTest(TestCase):

    fixture = BotFixture()

    @classmethod
    def setUpClass(cls):
        super(BotTest, cls).setUpClass()
        cls.tester = cls.fixture.tester

    @classmethod
    def tearDownClass(cls):
        cls.fixture.teardown()

    def test_materials_without_product_orders(self):

        def execute(materials):
            MRPSession.kickoff(self.tester, materials)
            sleep(0.5)
            self.assertIsNotNone(MRPSession.running_session())
            MRPSession.wait()
            self.assertIsNone(MRPSession.running_session())

        # Create Sales Orders
        self.fixture.create_sales_orders(self.fixture.finished_material, revision=20, quantity=200, deliver_in=timedelta(days=5))
        self.fixture.create_sales_orders(self.fixture.finished_material, revision=20, quantity=150, deliver_in=timedelta(days=12))

        execute([
            [self.fixture.finished_material.code, 20, None],
        ])

        # With SalesOrder + ProductionOrder
        self.fixture.create_sales_orders(self.fixture.finished_material2, revision=20, quantity=100, deliver_in=timedelta(days=12))
        self.fixture.create_sales_orders(self.fixture.finished_material2, revision=20, quantity=200, deliver_in=timedelta(days=19))
        self.fixture.create_production_orders(self.fixture.finished_material2, revision=20, quantity=100, start_in=timedelta(days=1))

        execute([
            (self.fixture.finished_material2.code, 20, None)
        ])

