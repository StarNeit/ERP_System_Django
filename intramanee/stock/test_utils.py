from django.db.models import ObjectDoesNotExist
from intramanee.common.models import IntraUser
from intramanee.common import codes
from intramanee.common.codes.models import LOV
from intramanee.common.uoms import UOM
from intramanee.common.location import Location
from intramanee.common.documents import RunningNumberCenter, DailyRunningNumberPolicy
from intramanee.common.utils import LOG
from intramanee.stock.documents import MaterialMaster, Schematic, SchematicEntry, InventoryContent
import re

TEST_MOVEMENT_NUMBER_KEY = 'test_movement_auto_number'
RunningNumberCenter.register_policy(TEST_MOVEMENT_NUMBER_KEY, DailyRunningNumberPolicy('TESTMV'))


class StepComponent(object):

    def __init__(self, str_material_code, int_quantities, str_uom, cost=100):
        """

        :param basestring|codes.StockCode str_material_code:
        :param [int] int_quantities:
        :param basestring str_uom:
        :param int cost:
        """
        assert isinstance(str_material_code, (codes.StockCode, basestring))
        assert isinstance(int_quantities, list)
        assert isinstance(str_uom, basestring)
        assert isinstance(cost, int)
        self.material_code = str_material_code if isinstance(str_material_code, basestring) else str(str_material_code)
        self.quantities = int_quantities
        self.uom = str_uom
        self.cost = cost
        self.is_configurable = len(int_quantities) > 1

    def serialized(self):
        return {
            'code': self.material_code,
            'quantity': self.quantities,
            'is_configurable': self.is_configurable,
            'counter': self.uom,
            'cost': self.cost
        }


class Step(object):

    def __init__(self, int_task_code, int_durations, int_staging_durations, **kwargs):
        """

        :param int int_task_code:
        :param [int] int_durations:
        :param [int] int_staging_durations:
        :param kwargs:
        """
        assert isinstance(int_task_code, int)
        assert isinstance(int_durations, list)
        assert isinstance(int_staging_durations, list)
        self.task_code = int_task_code
        self.durations = int_durations
        self.staging_durations = int_staging_durations
        self.is_configurable = len(int_durations) > 1
        self.labor_cost = kwargs.pop('labor_cost', 11)
        self.markup = kwargs.pop('markup', 20)
        # Will be generated on build_schematic_dict()
        self.id = None          # empty Id
        # update via << operator
        self.materials = []
        # update via then()
        self.destinations = []
        self.source = []

    def then(self, *destinations):
        for dest in destinations:
            assert isinstance(dest, Step)
            dest.source.append(self)
            self.destinations.append(dest)
        return self

    @classmethod
    def simple(cls, int_task_code, int_duration, int_staging_duration=5):
        return cls(int_task_code, [int_duration], [int_staging_duration])

    @classmethod
    def configurable(cls, int_task_code, int_durations, int_staging_durations):
        return cls(int_task_code, int_durations, int_staging_durations)

    def __lshift__(self, other):
        if isinstance(other, StepComponent):
            assert len(other.quantities) == len(self.durations), "Incompatible component, incorrect configurable sizes"
            self.materials.append(other)
            return self
        elif isinstance(other, (list, tuple)):
            for o in other:
                assert len(o.quantities) == len(
                    self.durations), "Incompatible component, incorrect configurable sizes"
                self.materials.append(o)
            return self
        else:
            raise ValueError("Unable to append component of type %s" % type(other))

    @staticmethod
    def build_schematic_dict(first_step):
        tmp = list()

        work_list = [first_step]
        for a in work_list:
            if a not in tmp:
                a.id = len(tmp) + 1
                tmp.append(a)
                work_list.extend(a.destinations)

        return map(lambda x: {
            'id': x.id,                  # Calculate this
            'process': x.task_code,
            'labor_cost': x.labor_cost,
            'markup': x.markup,
            'is_configurable': x.is_configurable,
            'source': list(str(s.id) for s in x.source),   # Calculate this
            'duration': x.durations,
            'staging_duration': x.staging_durations,
            'materials': list(m.serialized() for m in x.materials)
        }, sorted(tmp, lambda a, b: a.id < b.id))

    def __eq__(self, other):
        return self.id == other.id


class StockFixture(object):
    COMP_CODE = 'TST'
    tester = None       # type: IntraUser

    def __init__(self):
        try:
            self.tester = IntraUser.objects.get(code='testman')
        except ObjectDoesNotExist:
            self.tester = IntraUser.objects.create_user('testman', 'kittiphat', 'nope')

        company_comp = codes.CompanyComponent()
        if not company_comp.has(self.COMP_CODE):
            company_comp.append(self.COMP_CODE, 'Test Customer', author=self.tester)

    def teardown(self):
        LOG.info("REMOVING ALL TST DATA")
        InventoryContent.manager.delete(cond={
            'code': {'$regex': '^stock-%s' % self.COMP_CODE}
        }, verbose=True)
        MaterialMaster.manager.delete(cond={
            'code': {'$regex': '^stock-%s' % self.COMP_CODE}
        }, verbose=True)

    @classmethod
    def ensure_inventory_content_quantity(cls, material, quantity):
        """

        :param MaterialMaster|StockCode material:
        :param quantity:
        """
        content = InventoryContent.factory(material if isinstance(material, codes.StockCode) else material.code,
                                           Location.factory('STORE').code,
                                           RunningNumberCenter.new_number(TEST_MOVEMENT_NUMBER_KEY),
                                           None)
        content.quantity = quantity
        content.save()

    def ensure_tester_permission(self, permission_string):
        if not self.tester.can(permission_string):
            self.tester.permissions.append(permission_string)
            self.tester.save()

    def ensure_material_exists(self, stock_code_without_owner, uom_code, **kwargs):
        """
        Make sure given stock code with prefix of self.COMP_CODE exists

        :param basestring stock_code_without_owner:
        :param basestring|UOM uom_code:
        :param kwargs:
        :return MaterialMaster:
        """
        author = kwargs.pop('author', self.tester)
        plan = kwargs.pop('schematic', None)
        default_procurement_type = MaterialMaster.EXTERNAL if plan is None else MaterialMaster.INTERNAL
        procurement_type = kwargs.pop('procurement_type', default_procurement_type)
        scrap_percentage = kwargs.pop('scrap_percentage', 0)
        m = MaterialMaster.factory(codes.StockCode("%s%s" % (self.COMP_CODE, stock_code_without_owner)),
                                   uom_code,
                                   procurement_type=kwargs.pop('procurement_type', procurement_type),
                                   author=author,
                                   scrap_percentage=scrap_percentage)

        # Additional fields
        changed = False
        for field in ['mrp_type', 'gr_processing_time', 'lot_size', 'lot_size_arg', 'lot_size_min', 'lot_size_max']:
            val = kwargs.pop(field, None)
            if val is not None:
                setattr(m, field, val)
                changed = True

        if changed:
            m.save()

        # Attach schematic
        if plan is not None:
            sch = Schematic.factory(m.object_id, kwargs.pop('revision', 20), author,
                                    conf_size=kwargs.pop('conf_size', []),
                                    verbose=True)
            sch.schematic = plan
            sch.touched(self.tester)
            if kwargs.get('verbose', False):
                print sch
            m.update_schematic(author, sch)
        return m

    def ensure_mold_exists(self, code_no_company_no_size, schematic_listed_dict=None, revision=20, **kwargs):
        m = re.compile('([0-9A-Z]{8})(\d{5})').match(code_no_company_no_size)
        assert m is not None
        prefix, num = m.groups()
        size_code = LOV.ensure_exist(LOV.RANDD_SIZE, 'TEST_SIZE')
        c = codes.StockCode("%s%s%s" % (self.COMP_CODE, prefix, size_code))
        # if not c.lastComp.has(num):
        #     c.lastComp.append(num, '$test_item_delete_me')
        plan = None
        if schematic_listed_dict is not None:
            plan = self.create_plan(schematic_listed_dict)
        r = self.ensure_material_exists("%s%s" % (code_no_company_no_size, size_code),
                                        schematic=plan,
                                        revision=revision,
                                        uom_code=kwargs.pop('uom_code', 'pc'),
                                        **kwargs)

        # assert re.compile('[0-9A-Z]{11}\d{10}').match(r.code), "invalid mold code %s" % r.code
        return r

    def ensure_180_exists(self, code, schematic_listed_dict, revision, verbose=False, **kwargs):
        # 180G999RI11234HP14
        m = re.compile(r'180([0-9A-Z]{4})([A-Z]{2})(\d)(\d{4})([0-9A-Z]{2})([0-9A-Z]{2})').match(code)
        assert m is not None
        items = m.groups()
        # Validate 180 Codes
        c = codes.StockCode("%s180%s" % (self.COMP_CODE, "".join(items)))
        c.validate()
        return self.ensure_material_exists(code,
                                           'pc',
                                           schematic=self.create_plan(schematic_listed_dict),
                                           revision=revision,
                                           verbose=verbose)

    @classmethod
    def create_plan(cls, schematic_listed_dict):
        assert isinstance(schematic_listed_dict, list)

        def convert(d):
            r = SchematicEntry()
            r.deserialized(d)
            return r
        return map(convert, schematic_listed_dict)

