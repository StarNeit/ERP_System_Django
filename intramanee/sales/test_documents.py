__author__ = 'wasansae-ngow'

from unittest import TestCase
from test_utils import SalesFixture
from intramanee.production.test_documents import ProductionTest
from intramanee.stock import documents as stock
import datetime
import random


class SalesTest(ProductionTest):

    utils = SalesFixture()

    def __init__(self, _method_name='test_mock_sales_order'):
        super(SalesTest, self).__init__(_method_name)
        self.tester = self.utils.tester

    @classmethod
    def setUpClass(cls):
        super(SalesTest, cls).setUpClass()
        cls.utils.grant_full_access(cls.utils.tester)
        cls.utils.tester.save()

    @classmethod
    def tearDownClass(cls):
        cls.utils.teardown()

    def test_mock_sales_order(self, verbose=True, **kwargs):
        number = kwargs.pop('number', 10)
        regex = '^stock-TST180.*'
        period_min = kwargs.pop('range', 60) * 24 * 60
        finished_materials = stock.MaterialMaster.manager.find(number, 0, {
            'code': {'$regex': regex},
        })
        found_len = len(finished_materials)
        if verbose:
            print "Materials found : %s" % found_len

        if number > found_len:
            number = found_len

        def create_order(mat):
            for i in range(0, random.randint(1, 5)):
                qty = random.randint(1, 10)
                delivery_date = datetime.datetime.today() + datetime.timedelta(minutes=random.randint(0, period_min))
                so = self.utils.create_sales_order(mat.code, qty, delivery_date, mat.uom, 1)
                if verbose:
                    print "Material: %s, Sales order created : %s" % (mat.code, so.doc_no)

        map(create_order, finished_materials[:number])
