__author__ = 'peat'
import documents as d
from mock_template import DesignMockTemplate as mock
from unittest import TestCase
from bson import ObjectId
from intramanee.common import codes, task
from intramanee.common.models import IntraUser, UserFile
from intramanee.common.utils import get_or_none
from intramanee.stock import documents as stock_doc, test_documents as test_doc
from intramanee.common.documents import ApprovableDoc
from intramanee.production.test_documents import ProductionTest
from django.utils.translation import ugettext as _
import re
import random
import time


class TestDesign(TestCase):

    tester = get_or_none(IntraUser, code='testman')
    existing_material = None

    def __init__(self, _method_name='test_mock_design'):
        super(TestDesign, self).__init__(_method_name)

    @classmethod
    def setUpClass(cls):
        """
        For every test methods
        :return:
        """
        if cls.tester is None:
            cls.tester = IntraUser.objects.create_user('testman', 'kittiphat', 'nope')

        ProductionTest.utils.grant_full_access(cls.tester)

        # Create Customer Test Code
        company_comp = codes.CompanyComponent()
        if not company_comp.has('TST'):
            company_comp.append('TST', 'Test Customer', author=cls.tester)

        if cls.existing_material is None:
            cls.existing_material = stock_doc.MaterialMaster.factory(codes.StockCode("TST011SILVACTIVX"), 'g', author=cls.tester)

    def test_design_uid_validation(self):
        """
        Validate the UID pair
        :return:
        """
        exist_design_code = "TST180G999RI0000108TE"        # TEST ID

        self.exist_design_uid = ObjectId()
        d.DesignUID.commit(self.exist_design_uid, exist_design_code, self.tester)

        self.assertTrue(d.DesignUID.validate_pair(self.exist_design_uid, exist_design_code))

        d.DesignUID.manager.delete({
            'code': exist_design_code
        })

    def test_design_object_validation(self):
        o = d.Design()
        o.attachments = []
        o.process = d.DesignProcess()
        o.process.material_master = []
        o.process.sample_creation = []

        # Simple TestCase - empty data complaining
        errors = o.validate_for_errors()       # errors tuple
        self.assertTrue(_("ERROR_REQUIRE_ATTACHMENT") in errors[0])
        self.assertTrue(_("ERROR_REQUIRE_THREE_PROCESSES") in errors[1])
        self.assertTrue(_("ERROR_REQUIRE_THREE_PROCESSES") in errors[2])
        self.assertTrue(_("ERROR_REQUIRE_COST") in errors[3])
        self.assertTrue(_("ERROR_REQUIRE_COMPLETE_PRODUCT_CODE") in errors[4])

        # Add attachment
        o.attachments.append(UserFile.objects.all()[0])
        errors = o.validate_for_errors()
        self.assertTrue(len(errors[0]) == 0)

        # Add master modeling process
        # ID, Task, Materials, Source, Configurable, Duration, LaborCost, MarkUp, target
        o.process.new_process("1", task.Task.factory('5291'), [], [], False, [20], 30, 30, target="master_modeling")
        o.process.new_process("2", task.Task.factory('5331'), [], ["1"], False, [20], 30, 30, target="master_modeling")
        o.process.new_process("3", task.Task.factory('4143'), [], ["2"], False, [20], 30, 30, target="master_modeling")

        errors = o.validate_for_errors()
        self.assertTrue(_("ERROR_UNABLE_TO_IDENTIFY_MASTER_MODEL") in errors[1])  # 4143 required 021 to be completed

        # Code, Quantities, isConfigurable, counter, cost
        o.process.master_modeling[2].add_material(self.ensure_mold_exists("TST021BNZYM66666"), [-1], False, "g", 10)
        errors = o.validate_for_errors()

        self.assertTrue(len(errors[1]) == 0)        # Everything should be correct at this point.

        # Test orphan operations
        o.process.new_process("4", task.Task.factory('5291'), [], [], False, [20], 30, 30, target="master_modeling")
        errors = o.validate_for_errors()
        self.assertTrue(_("ERROR_TASK_STOPPER_MUST_BE_LAST_PROCESS") in errors[1])  # 5291 is not task_stopper

        o.process.new_process("5", task.Task.factory('5331'), [], ["4"], False, [20], 30, 30, target="master_modeling")
        proc = o.process.new_process("6", task.Task.factory('4143'), [], ["5"], False, [20], 30, 30, target="master_modeling")
        proc.add_material(self.ensure_mold_exists("TST023BNZYM66667"), [-1], False, "pc", 10)
        errors = o.validate_for_errors()
        self.assertTrue(_("ERROR_UNABLE_TO_IDENTIFY_MASTER_MODEL") in errors[1])  # 4143 required 021 to be completed

        proc.process = task.Task.factory('4161')
        errors = o.validate_for_errors()
        self.assertTrue(len(errors[1]) == 0)

        # Check counter unit of measure
        proc = o.process.new_process("10", task.Task.factory('5291'), [], [], False, [20], 30, 30, target="sample_creation")
        # Check against newly create item with different counter group
        mat = proc.add_material(self.ensure_mold_exists("TST023BNZYM66667"), [1], False, "g", 20)
        o.process.new_process("11", task.Task.factory('5331'), [], ["10"], False, [20], 30, 30, target="sample_creation")
        o.process.new_process("12", task.Task.factory('4143'), [], ["11"], False, [20], 30, 30, target="sample_creation")

        errors = o.validate_for_errors()
        self.assertTrue(len(errors[2]) == 1)
        self.assertTrue(_("ERROR_BAD_UOM %(material)s") % {'material': str(mat.code)} in errors[2])

        mat.counter = "pc"
        errors = o.validate_for_errors()
        self.assertTrue(len(errors[2]) == 0)

        # Check against existing material
        mat = proc.add_material(self.existing_material.code, [1], False, "cm", 50)
        errors = o.validate_for_errors()
        self.assertTrue(len(errors[2]) == 1)
        self.assertTrue(_("ERROR_BAD_UOM %(material)s") % {'material': str(mat.code)} in errors[2])

    def ensure_mold_exists(self, code):
        m = re.compile('([0-9A-Z]{11})(\d{5})').match(code)
        self.assertIsNotNone(m, "given code must match pattern")
        prefix, num = m.groups()
        c = codes.StockCode(prefix)
        if not c.lastComp.has(num):
            c.lastComp.append(num, '$test_item_delete_me')
        return codes.StockCode(code)

    @classmethod
    def tearDownClass(cls):
        if cls.existing_material:
            stock_doc.MaterialMaster.manager.delete({
                '_id': cls.existing_material.object_id
            })

        stock_doc.MaterialMaster.manager.delete({
            'created_by': ObjectId(cls.tester.id)
        })

        d.Design.manager.delete({
            'created_by': ObjectId(cls.tester.id)
        })
        d.DesignUID.manager.delete({
            'commit_by': ObjectId(cls.tester.id)
        })

    def test_mock_design(self, verbose=True, **kwargs):

        def message(v, m):
            if v:
                print m

        number = kwargs.pop('number', 10)
        finished_codes = mock.get_finished_code(number)
        message(verbose, "Done: getting finished codes")
        master_models = mock.get_master_model(number)
        message(verbose, "Done: getting master model codes")

        def ensure(mm):
            self.ensure_mold_exists(mm[0])
            message(verbose, "Done: ensuring mold %s exists" % str(mm))

        map(ensure, master_models)

        numbers = mock.get_numbers()

        index = 0
        used_master_models = []

        for c in finished_codes:
            start = time.time()
            uid = ObjectId()
            d.DesignUID.commit(uid, c, self.tester)

            o = d.Design()
            args = {
                # 'template_no': mock.get_randomized_template(),
                'template_no': random.randint(0, numbers['template_no']-1),
                # 'raw_index': mock.get_randomized_index(),
                'index': index,
                'design_number': c[13:17],
                'code': c,
                'rev_unique_id': uid,
            }

            # randomized_master_model = random.randint(0, len(master_models)-1)
            randomized_master_model = index
            args.update({'master_model': master_models[randomized_master_model]})
            args.update({'include_master': True})
            # if randomized_master_model not in used_master_models:
            #     used_master_models.append(randomized_master_model)
            #     args.update({'include_master': True})

            o.deserialized(mock.get_template(**args))
            o.attachments = []
            o.attachments.append(UserFile.objects.all()[0])

            o.invoke_set_status(self.tester, ApprovableDoc.APPROVED, verbose=True)
            o.touched(self.tester)
            end = time.time()
            message(verbose, "Done: Design for %s is saved with unique number %s within %s" % (c, c[13:17], end - start))
            index += 1
