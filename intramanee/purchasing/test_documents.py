__author__ = 'wasansae-ngow'

from unittest import TestCase
from intramanee.purchasing import documents as pur
from intramanee.purchasing.test_utils import PurchasingFixture
from intramanee.production import documents as prod
from intramanee.task import documents as tasks
from intramanee.stock import documents as stock
from intramanee.common.task import Task
from datetime import datetime


class PurchasingTest(TestCase):

    utils = PurchasingFixture()

    def __init__(self, _method_name='test_create_purchase_requisition'):
        super(PurchasingTest, self).__init__(_method_name)
        self.tester = self.utils.tester

    @classmethod
    def setUpClass(cls):
        super(PurchasingTest, cls).setUpClass()
        cls.grant_full_access(cls.utils.tester)
        cls.utils.tester.save()

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
        grant_access(user, pur.PurchaseRequisition.Meta.collection_name, base_actions)
        grant_access(user, pur.PurchaseOrder.Meta.collection_name, base_actions)

    @classmethod
    def create_material_movement(cls, movement_type, items, ref_doc=None):
        mv = stock.InventoryMovement()
        mv.type = movement_type
        mv.ref_doc = ref_doc
        mv.touched(cls.utils.tester)

        return mv

    @classmethod
    def tearDownClass(cls):
        super(PurchasingTest, cls).tearDownClass()
        cls.utils.teardown()

    def test_create_purchase_requisition(self, **kwargs):
        testing = kwargs.pop("testing", True)

        req_date = datetime.today().replace(hour=13, minute=0, second=0, microsecond=0) if testing else datetime(2016, 1, 10, 8)

        req = self.utils.create_purchase_requisition(self.utils.raw_mat_1.code,     # Material
                                                     10,                            # Quantity
                                                     'pc',                          # UOM
                                                     20,                            # Revision
                                                     None,                          # Size
                                                     1200,
                                                     req_date,                      # Delivery date
                                                     10,                          # Open quantity
                                                     1                              # PR type
                                                     )

        req = self.utils.create_purchase_requisition(self.utils.raw_mat_1.code,     # Material
                                                     10,                            # Quantity
                                                     'pc',                          # UOM
                                                     20,                            # Revision
                                                     None,                          # Size
                                                     350.5,
                                                     req_date,                      # Delivery date
                                                     10,                          # Open quantity
                                                     1                              # PR type
                                                     )