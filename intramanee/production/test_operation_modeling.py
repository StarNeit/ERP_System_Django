from unittest import TestCase
from test_utils import ProductionFixture
from intramanee.stock.documents import MaterialMaster, Schematic
from intramanee.stock.test_utils import Step, StepComponent
from intramanee.common.models import IntraUser


class ProductionOrderOperationModelingTest(TestCase):

    utils = ProductionFixture()

    @classmethod
    def setUpClass(cls):
        super(ProductionOrderOperationModelingTest, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        super(ProductionOrderOperationModelingTest, cls).tearDownClass()

        cls.utils.teardown()

    def testSetupMaterials(self):
        step_1 = Step.simple(5291, 0.1)
        step_2 = Step.simple(5331, 1440) << [
            StepComponent('TST011SILVACTIVX', [5], 'g', 100),
            StepComponent('TST011SILV660LVL', [3], 'g', 300)
        ]
        step_3 = Step.simple(5462, 10) << [
            StepComponent('TST011SILVACTIVX', [1], 'g', 250),
            StepComponent('TST011SILV660LVL', [30], 'g', 250)
        ]
        step_4 = Step.simple(5391, 12, 10)

        # Link
        step_1.then(step_2, step_3)
        step_2.then(step_4)
        step_3.then(step_4)

        # Validate linkages
        assert step_1.source == []
        assert step_2.source == [step_1]
        assert step_3.source == [step_1]
        assert step_4.source == [step_2, step_3]

        schematic = Step.build_schematic_dict(step_1)

        assert step_1.destinations == [step_2, step_3]
        assert step_2.destinations == [step_4]
        assert step_3.destinations == [step_4]
        assert step_4.destinations == []

        compare = [
            {
                'id': 1,
                'process': 5291,
                'labor_cost': 11,
                'markup': 20,
                'is_configurable': False,
                'source': [],
                'materials': [],
                'duration': [0.1],
                'staging_duration': [5]
            },
            {
                'id': 2,
                'process': 5331,
                'labor_cost': 11,
                'markup': 20,
                'is_configurable': False,
                'source': ['1'],
                'materials': [
                    {
                        'code': 'TST011SILVACTIVX',
                        'quantity': [5],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 100
                    },
                    {
                        'code': 'TST011SILV660LVL',
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
                'labor_cost': 11,
                'markup': 20,
                'is_configurable': False,
                'source': ['1'],
                'materials': [
                    {
                        'code': 'TST011SILVACTIVX',
                        'quantity': [1],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 250
                    },
                    {
                        'code': 'TST011SILV660LVL',
                        'quantity': [30],
                        'is_configurable': False,
                        'counter': 'g',
                        'cost': 250
                    },
                ],
                'duration': [10],
                'staging_duration': [5]
            },
            {
                'id': 4,
                'process': 5391,
                'labor_cost': 11,
                'markup': 20,
                'is_configurable': False,
                'source': ['2', '3'],
                'materials': [],
                'duration': [12],
                'staging_duration': [10]
            }
        ]

        assert len(compare) == len(schematic), "Built schematic should be equal in size"

        def verbose(message, mode=False):
            if mode:
                print message

        for index, correct in enumerate(compare):
            challenge = schematic[index]
            verbose("Check schematic index %s" % index)
            for field in ['process', 'id', 'source', 'duration', 'staging_duration', 'is_configurable', 'markup', 'labor_cost', 'materials']:
                verbose("\tCheck field: %s" % field)
                if field in ['materials']:
                    for material_idx, correct_mat in enumerate(correct['materials']):
                        for material_field in correct_mat:
                            verbose("\t\tIndex: %s [%s] %s => %s" % (material_idx, material_field, correct_mat[material_field], challenge['materials'][material_idx][material_field]))
                            assert correct_mat[material_field] == challenge['materials'][material_idx][material_field], "Build schematic should have equal material description failed at"
                else:
                    assert correct[field] == challenge[field], "Built schematic should be equal at index=%s field=%s\n%s => %s" % (index, field, correct[field], challenge[field])

    def testOperationModelNavigation(self):
        # Test next_op(), prev_op() methods
        step_1 = Step.simple(5291, 0.1)
        step_2 = Step.simple(5331, 1440) << [
            StepComponent('TST011SILVACTIVX', [5], 'g', 100),
            StepComponent('TST011SILV660LVL', [3], 'g', 300)
        ]
        step_3 = Step.simple(5462, 10) << [
            StepComponent('TST011SILVACTIVX', [1], 'g', 250),
            StepComponent('TST011SILV660LVL', [30], 'g', 250)
        ]
        step_4 = Step.simple(5391, 12, 10)

        # Link
        step_1.then(step_2, step_3)
        step_2.then(step_4)
        step_3.then(step_4)

        # Schematic that should be
        sch = Step.build_schematic_dict(step_1)

        # Create the MaterialMaster
        mm_fp = self.utils.ensure_180_exists('180GR09RI60003CA14', sch, 1)

        # Create Production Order per Material Master

    def testCheckGroupableValidation(self):
        # Test is_groupable_with() method
        pass
