__author__ = 'peat'
from unittest import TestCase
from documents import MaterialMaster
from intramanee.common import task
from test_utils import StockFixture


class TestStock(TestCase):

    utils = StockFixture()

    @classmethod
    def setUpClass(cls):
        super(TestStock, cls).setUpClass()
        cls.raw_mat_1 = cls.utils.ensure_material_exists("011SILVACTIVX", 'g')
        cls.raw_mat_2 = cls.utils.ensure_material_exists("011SILV660LVL", 'g')

    @classmethod
    def tearDownClass(cls):
        super(TestStock, cls).tearDownClass()
        cls.utils.teardown()

    def test_revisions(self):
        mold_rev_1_schematic = [
            {
                'id': '1',
                'process': 5291,
                'labor_cost': 11,
                'markup': 20.0,
                'is_configurable': False,
                'source': [],
                'materials': [],
                'duration': [12]
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
                        'code': str(self.raw_mat_1.code),
                        'quantity': [20],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    }
                ],
                'duration': [600]
            },
            {
                'id': 3,
                'process': 4143,
                'labor_cost': 11,
                'markup': 20.0,
                'is_configurable': False,
                'source': ['2'],
                'materials': [],
                'duration': [15]
            }
        ]

        mold_1 = self.utils.ensure_mold_exists("021G999M10001", mold_rev_1_schematic, revision=19)
        self.assertEqual(mold_1.schematic.rev_id, 19)

        # Update schematic
        mold_rev_1_schematic[1]['markup'] = 20.0
        mold_1 = self.utils.ensure_mold_exists("021G999M10001", mold_rev_1_schematic, revision=20)

        self.assertEqual(mold_1.schematic.rev_id, 20)

        revs = mold_1.revisions()
        self.assertEqual(len(revs), 2)

    def test_expansion(self):
        end_product_sch = [
            {
                'id': 1,
                'process': 5281,
                'labor_cost': 11,
                'markup': 20.0,
                'is_configurable': False,
                'source': [],
                'materials': [],
                'duration': [12]
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
                        'code': str(self.raw_mat_1.code),
                        'quantity': [20],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 300
                    }
                ],
                'duration': [600]
            },
            {
                'id': 3,
                'process': 5401,
                'labor_cost': 11,
                'markup': 20.0,
                'is_configurable': False,
                'source': ['2'],
                'materials': [],
                'duration': [15]
            },
            {
                'id': 4,
                'process': 5421,
                'labor_cost': 12,
                'markup': 20,
                'is_configurable': False,
                'source': ['3'],
                'materials': [],
                'duration': [500]
            },
            {
                'id': 5,
                'process': 5422,
                'labor_cost': 12,
                'markup': 20,
                'is_configurable': False,
                'source': ['4'],
                'materials': [],
                'duration': [500]
            }
        ]
        fp = self.utils.ensure_180_exists('180G999RI11234HP14', end_product_sch, 11)

        self.assertEqual(len(fp.schematic.schematic), 5)
        self.assertEqual(str(fp.code), 'stock-TST180G999RI11234HP14')
        self.assertEqual(fp.schematic.schematic[0].process, task.Task.factory(5281))
        self.assertEqual(fp.schematic.schematic[1].process, task.Task.factory(5331))
        self.assertEqual(fp.schematic.schematic[2].process, task.Task.factory(5401))
        self.assertEqual(fp.schematic.schematic[3].process, task.Task.factory(5421))
        self.assertEqual(fp.schematic.schematic[4].process, task.Task.factory(5422))

        fp.schematic.expand(is_production=True)

        self.assertEqual(fp.schematic.schematic[0].process, task.Task.factory(5281))
        self.assertEqual(fp.schematic.schematic[1].process, task.Task.factory(5464))  # Appended
        self.assertEqual(fp.schematic.schematic[2].process, task.Task.factory(5271))  # Prepended
        self.assertEqual(fp.schematic.schematic[3].process, task.Task.factory(5291))  # Prepended
        self.assertEqual(fp.schematic.schematic[4].process, task.Task.factory(5331))
        self.assertEqual(fp.schematic.schematic[5].process, task.Task.factory(5462))  # Appended
        self.assertEqual(fp.schematic.schematic[6].process, task.Task.factory(5391))  # Appended
        self.assertEqual(fp.schematic.schematic[7].process, task.Task.factory(5401))
        self.assertEqual(fp.schematic.schematic[8].process, task.Task.factory(5466))  # Forked
        self.assertEqual(fp.schematic.schematic[9].process, task.Task.factory(5411))  # Prepended
        self.assertEqual(fp.schematic.schematic[10].process, task.Task.factory(5421))
        self.assertEqual(fp.schematic.schematic[11].process, task.Task.factory(5412))  # Appended
        self.assertEqual(fp.schematic.schematic[12].process, task.Task.factory(5422))
        self.assertEqual(fp.schematic.schematic[13].process, task.Task.factory(5467))  # Forked

