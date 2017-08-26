__author__ = 'wasansae-ngow'

from documents import SalesOrder, SalesOrderEntry
from intramanee.production.test_utils import ProductionFixture
from intramanee.common import codes
from bson import ObjectId


class SalesFixture(ProductionFixture):

    customer = None

    def __init__(self):
        super(SalesFixture, self).__init__()
        self.customer = codes.CustomerCode(self.COMP_CODE)

    def teardown(self):
        SalesOrder.manager.delete(cond={
            'created_by': ObjectId(self.tester.id)
        })

    def create_sales_order(self, material, quantity, delivery_date, uom, revision, **kwargs):
        author = kwargs.pop('author', self.tester)
        so = SalesOrder()
        so.customer = self.customer
        so.sales_rep = self.tester
        so.delivery_date = delivery_date
        item = SalesOrderEntry()
        item.material = material
        item.quantity = quantity
        item.uom = uom
        item.revision = revision
        so.items = [item]
        so.touched(author)
        return so
