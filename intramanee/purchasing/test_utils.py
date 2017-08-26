from dateutil.relativedelta import relativedelta
from datetime import datetime
import time
from intramanee.production import documents as prod
from intramanee.purchasing import documents as pur
from intramanee.stock.test_utils import StockFixture
from bson import ObjectId


class PurchasingFixture(StockFixture):

    def __init__(self):
        super(PurchasingFixture, self).__init__()
        self.raw_mat_1 = self.ensure_material_exists("011SILVACTIVX", 'g')
        self.raw_mat_2 = self.ensure_material_exists("011SILV660LVL", 'g')

    def teardown(self):
        super(PurchasingFixture, self).teardown()
        pur.PurchaseOrder.manager.delete(cond={
            'created_by': ObjectId(self.tester.id)
        }, verbose=True)
        pur.PurchaseRequisition.manager.delete(cond={
            'created_by': ObjectId(self.tester.id)
        }, verbose=True)

    def create_purchase_requisition(self, material, quantity, uom, revision, size, net_price, delivery_date, open_quantity, verbose=True):
        req = pur.PurchaseRequisition()
        req.vendor = 'Batman'

        req_it = pur.PurchaseRequisitionItem()
        req_it.material = material
        req_it.quantity = quantity
        req_it.net_price = net_price
        req_it.uom = uom
        req_it.revision = revision
        req_it.size = size
        req_it.delivery_date = delivery_date
        req_it.open_quantity = open_quantity

        req.items = [req_it]
        req.touched(self.tester)
        if verbose:
            print('Purchase Requisition %s created' % req.doc_no)

        return req
