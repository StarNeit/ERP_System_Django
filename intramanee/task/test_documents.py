__author__ = 'bank'
from test_utils import TaskFixture
from unittest import TestCase
from intramanee.common import utils as u
from intramanee.production.documents import ProductionOrder
from intramanee.task.documents import ClerkAuxTask, StoreAuxTask


class TaskTest(TestCase):

    utils = TaskFixture()

    def __init__(self, _method_name='test_aux_task'):
        super(TaskTest, self).__init__(_method_name)
        self.tester = self.utils.tester

    @classmethod
    def setUpClass(cls):
        super(TaskTest, cls).setUpClass()
        cls.utils.grant_full_access(cls.utils.tester)
        cls.utils.tester.save()
        cls.utils.prepare_raw_mat_stock(cls.utils.tester)

    def test_aux_task(self, verbose=True, **kwargs):
        order = self.utils.create_production_orders(testing=False, number=1, **kwargs)[0]
        order.populate('operation')

        def assign(o):
            o.assignee = self.tester
            o.touched(self.tester)

        map(assign, order.operation)
        order.release(self.tester)
        self.assertEqual(order.status, ProductionOrder.STATUS_RELEASED, "Order status should be released")
        u.print_verbose(verbose, "order is released successfully")
        oid = [o.object_id for o in order.operation]

        clerks = ClerkAuxTask.manager.find(0, 0, {'parent_task': {'$in': oid}})
        self.assertTrue(len(clerks) > 0, "Clerk tasks should be created")
        stores = StoreAuxTask.manager.find(0, 0, {'parent_task': {'$in': oid}})
        self.assertTrue(len(stores) > 0, "Store tasks should be created")


