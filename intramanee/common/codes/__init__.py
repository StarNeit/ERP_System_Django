# coding=utf-8
__author__ = 'peat'
import re
import models
from intramanee.common.models import Company
from intramanee.common.task import Task
from django.db.models import Q, Max
from intramanee.common import utils
from django.utils.translation import ugettext as _
from intramanee.common.errors import ValidationError, BadParameterError


class CodeComponent:

    def __init__(self, name_, length_):
        self.name = name_
        self.length = length_


class KV(object):

    def __init__(self, code_, label_=None, children_=[], **kwargs):
        self.code = str(code_)
        self.label = label_ or str(code_)
        self.children = children_
        self.info = kwargs.pop('info', None)

    def has_child(self):
        return len(self.children) > 0

    def __str__(self):
        return ('%s: %s' % (self.code, self.label)).encode('utf-8')

    def __repr__(self):
        return str(self)


class Component(object):
    allowed_wildcard = True
    context = None

    def values(self):
        raise NotImplementedError('Required implementation')

    def suggest(self, typed, limit=-1):
        raise NotImplementedError('Required implementation')

    def can_append(self):
        raise NotImplementedError('Required implementation')

    def has(self, value):
        return self.get(value) is not None

    def get(self, code):
        """

        :param code:
        :return: matched KV, and None if not found.
        """
        for kv in self.values():
            if kv.code == code:
                return kv
        return None

    def is_optional(self):
        """
        Main Usage: Annotate system that this component is not required.

        If this component is missing from the ``Code`` system will and such component is last_component.
        System will return True

        :return:
        """
        return False


class UnconstraintedComponent(CodeComponent, Component):

    def __init__(self, length, pad_character="0"):
        self.pad_character = pad_character
        super(UnconstraintedComponent, self).__init__("unconstrainted", length)

    def values(self):
        possible_values = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        return map(self.get, possible_values)

    def suggest(self, typed, limit=10):
        return []

    def can_append(self):
        return False

    def has(self, value):
        return True

    def get(self, code):
        return KV(code.rjust(self.length, self.pad_character)[:self.length], str(code))


class CompanyComponent(Component):

    def __init__(self, **kwargs):
        super(CompanyComponent, self).__init__(**kwargs)
        self.length = 3

    def values(self):
        possible_values = Company.objects.all().order_by('code')
        return map(lambda x: KV(x.code, x.title), possible_values)

    def suggest(self, typed, limit=-1):
        qu = Company.objects.filter(Q(code__istartswith=typed) | Q(title__istartswith=typed))
        return map(lambda x: KV(x.code, x.title), qu.order_by('code'))

    def has(self, code):
        return self.get(code) is not None

    def get(self, code):
        l = utils.get_or_none(Company, code=code)
        if l:
            return KV(l.code, l.title)
        else:
            return None

    def can_append(self):
        return True

    def append(self, code_, title_, **kwargs):
        if not len(code_) == self.length:
            raise ValidationError('Supplied code "%s" must have size of %d' % (code_, self.length))

        # check if code_ already exists
        queried = Company.objects.filter(code=code_)
        if queried.count() > 0:
            raise ValidationError('Code "%s" already exists.' % code_)

        comp = Company(code=code_, title=title_)
        if 'author' in kwargs:
            comp.author = kwargs['author']
        comp.save()

        return True

    def __repr__(self):
        return unicode('Company')


class TaskComponent(Component):

    def __init__(self, length_):
        self.length = length_

    def values(self):
        possible_values = [v for k, v in Task.tasks.iteritems()]
        output = []
        for l in possible_values:
            output.append(KV(l.code, l.label))
        return output

    def suggest(self, typed, limit=-1):
        output = []
        queried = Task.filter(typed)
        output.extend(KV(l.code, l.label) for l in queried)
        return output

    def has(self, code):
        return self.get(code) is not None

    def get(self, code):
        if code.isdigit():
            l = Task.factory(code)
            if l:
                return KV(l.code, l.label, [])
        return None

    def can_append(self):
        return False


class LovComponent(Component):

    def __init__(self, group_, length_):
        self.group = group_
        self.length = length_

    def values(self):
        possible_values = models.LOV.objects.filter(self._get_filter()).order_by('code')
        output = []
        for l in possible_values:
            output.append(KV(l.code, l.label))
        return output

    def suggest(self, typed, limit=-1):
        output = []
        queried = models.LOV.objects.filter(self._get_filter(), (Q(code__istartswith=typed) | Q(label__istartswith=typed)))
        for l in queried.order_by('code'):
            output.append(KV(l.code, l.label))
        return output

    def has(self, code):
        return self.get(code) is not None

    def get(self, code):
        l = utils.get_or_none(models.LOV, group=self.groupValue(), code=code)
        if l:
            return KV(l.code, l.label, [])
        else:
            return None

    def append(self, code_, label_, **kwargs):
        if not len(code_) == self.length:
            raise ValidationError('Supplied code "%s" must have size of %d' % (code_, self.length))
        # check if code_ already exists
        queried = models.LOV.objects.filter(self._get_filter() & Q(code=code_))
        if queried.count() > 0:
            raise ValidationError('Code "%s" already exists.' % code_)

        models.LOV(group=self.groupValue(), code=code_, label=label_).save()
        return True

    def max(self):
        cursor = models.LOV.objects.filter(self._get_filter())
        if cursor.count() == 0:
            return 0
        else:
            r = cursor.aggregate(Max('code'))
            return r['code__max']

    def _get_filter(self):
        return Q(group=self.groupValue())

    def can_append(self):
        return True

    def __repr__(self):
        return unicode(self.groupValue())

    def groupValue(self):
        if hasattr(self.group, '__call__'):
            return self.group()
        return self.group


class HierarchyLovComponent(LovComponent):

    def __init__(self, group_, length_, parent_=None):
        super(HierarchyLovComponent, self).__init__(group_, length_)
        if parent_ is not None and not isinstance(parent_, models.LOV):
            raise ValidationError('Parent provided must be models.LOV class, received %s instead' % type(parent_))
        self.parent = parent_

    def get(self, code):
        """
        get code and children
        :param code:
        :return: KV of code, label and if it contains children, children will be nested and return inside the same KV
        """
        if self.parent:
            l = utils.get_or_none(models.LOV, group=self.groupValue(), code=code, parent=self.parent)
        else:
            l = utils.get_or_none(models.LOV, group=self.groupValue(), code=code)
        if l:
            child = l.children.filter()
            if child:
                return KV(l.code, l.label, [HierarchyLovComponent(child[0].group, len(child[0].code), l)])
            else:
                return KV(l.code, l.label, [])
        else:
            return None

    def _get_filter(self):
        """
        Get filter
        :return: filter for LOV
        """
        if self.parent:
            return (Q(group=self.groupValue()) & Q(parent=self.parent))
        else:
            return Q(group=self.groupValue())


class StaticComponent(CodeComponent, Component):

    def __init__(self, name_, length_, values_):
        super(StaticComponent, self).__init__(name_, length_)
        self.vals = values_

    def values(self):
        return self.vals

    def suggest(self, typed, limit=-1):
        filtered = []
        match = typed.lower()
        for v in self.vals:
            if v.code.lower().startswith(match) or v.label.lower().startswith(match):
                filtered.append(v)
        return filtered

    def get(self, code):
        for v in self.vals:
            if v.code == code:
                return v
            if v.code == ('*' * self.length):
                return v
        return None

    def can_append(self):
        return False

    def __repr__(self):
        return unicode(self.name)


class GenericColorKV(KV):

    def __init__(self, code, shade):
        super(GenericColorKV, self).__init__(code, shade, [
            LovComponent('Color-%s' % shade, 2)
        ])


class GemColorComponent(LovComponent):

    def __init__(self):
        super(GemColorComponent, self).__init__('Shade', 1)


class DiamondColorComponent(LovComponent):

    def __init__(self):
        super(DiamondColorComponent, self).__init__('Diamond-Color', 4)


class DiamondShineComponent(LovComponent):

    def __init__(self):
        super(DiamondShineComponent, self).__init__('Diamond-Shine', 4)


class GemShapeComponent(LovComponent):

    def __init__(self):
        super(GemShapeComponent, self).__init__('Shape', 4)


class GemTextureComponent(LovComponent):

    def __init__(self):
        super(GemTextureComponent, self).__init__('Texture', 2)


class StyleComponent(LovComponent):

    def __init__(self):
        super(StyleComponent, self).__init__('Style', 2)


class TaskCodeConfigComponent(TaskComponent):

    def __init__(self):
            super(TaskCodeConfigComponent, self).__init__(4)


class SkinTypeComponent(LovComponent):

    def __init__(self):
        super(SkinTypeComponent, self).__init__('Skin', 2)


class OfficeSupplyTypeLov(LovComponent):

    def __init__(self):
        super(OfficeSupplyTypeLov, self).__init__('Office Supply Type', 1)


class DipTypeComponent(LovComponent):

    def __init__(self):
        super(DipTypeComponent, self).__init__('Dip', 2)


class WipTypeComponent(LovComponent):

    def __init__(self):
        super(WipTypeComponent, self).__init__('WipType', 2)


class MaracasiteGradeComponent(LovComponent):

    def __init__(self):
        super(MaracasiteGradeComponent, self).__init__('Marcasite-Grade', 1)


class GemGradeComponent(LovComponent):

    def __init__(self):
        super(GemGradeComponent, self).__init__('Grade', 2)


class GemCutComponent(LovComponent):

    def __init__(self):
        super(GemCutComponent, self).__init__('Gem-Cut', 2)


class DrillTypeComponent(LovComponent):

    def __init__(self):
        super(DrillTypeComponent, self).__init__('Drill-Type', 1)


class CrystalGradeLov(LovComponent):

    def __init__(self):
        super(CrystalGradeLov, self).__init__('Crystal Grade', 1)


class SwarovskiLov(HierarchyLovComponent):

    def __init__(self):
        super(SwarovskiLov, self).__init__('SwarovskiCut', 6)


class MetalTypeLov(LovComponent):

    def __init__(self):
        super(MetalTypeLov, self).__init__('Metal Type', 1)


class MetalComponentTypeLov(LovComponent):

    def __init__(self):
        super(MetalComponentTypeLov, self).__init__('MetalComponent Type', 1)


class MetalBodyLov(LovComponent):

    def __init__(self):
        super(MetalBodyLov, self).__init__('MetalBody', 4)


class GemSizeLov(LovComponent):

    def __init__(self):
        super(GemSizeLov, self).__init__('GemSize', 6)


class MoldTypeLov(LovComponent):

    def __init__(self):
        super(MoldTypeLov, self).__init__('MoldType', 1)


class SkinBodyLov(LovComponent):

    def __init__(self):
        super(SkinBodyLov, self).__init__('SkinBody', 4)


class OtherComponentTypeLov(LovComponent):

    def __init__(self):
        super(OtherComponentTypeLov, self).__init__('OtherComponent Type', 1)


class SparePartLov(LovComponent):

    def __init__(self):
        super(SparePartLov, self).__init__('SparePart', 1)


class ScrapLov(LovComponent):

    def __init__(self):
        super(ScrapLov, self).__init__('Scrap', 1)


class MetalBody2Lov(LovComponent):

    def __init__(self):
        super(MetalBody2Lov, self).__init__('MetalBody2', 6)


class MGStaticLov(StaticComponent):

    def __init__(self):
        super(MGStaticLov, self).__init__("M/G", 1, [
            KV("M", _("MOLD_CLASS_MA")),
            KV("G", _("MOLD_CLASS_GRAND_MA"))
        ])


class ContextBasedRunningNumberLov(LovComponent):
    """
    Context will be automatically injected to the Component
    via IntramaneeCode object.
    """

    def __init__(self, prefix, length, trimmed_code=None):
        """

        :param basestring prefix:
        :param int length:
        :param int trimmed_code:
        """
        super(ContextBasedRunningNumberLov, self).__init__(self.calculate_group, length)
        self.prefix = prefix
        self.trimmed_code = trimmed_code

    def calculate_group(self):
        """
        Lazy group calculator
        :return:
        """
        return "%s%s" % (self.prefix, self.context[0] if self.trimmed_code is None else self.context[0][-self.trimmed_code:])

    def new_code(self):
        """
        Created a new code then commit the code to the system right away.

        :return: newly created code.
        """
        output = str(int(self.max()) + 1).zfill(self.length)
        self.append(output, 'WIP_' + output)
        return output

    def __str__(self):
        return str(_("CODE_COMPONENT_RUNNING_NUMBER"))

    def __repr__(self):
        return unicode(self.__str__())


class MoldSizeNameLov(LovComponent):

    def __init__(self):
        # Using same name as common/service.py@LovLookupSource
        super(MoldSizeNameLov, self).__init__(models.LOV.RANDD_SIZE, models.LOV.RANDD_SIZE_DIGIT_COUNT)


class OptionalMoldSizeNameLov(MoldSizeNameLov):

    def is_optional(self):
        return True


class StoneLov(LovComponent):

    def __init__(self):
        super(StoneLov, self).__init__('Stone', 1)


RULES = [
        CompanyComponent(),
        StaticComponent('Category', 1, [
            KV(0, 'Raw Material', [
                StaticComponent('Raw Material Type', 1, [
                    KV(0, 'Gem Stone', [
                        StaticComponent('Gem Stone Type', 1, [
                            KV(1, 'Crystal',[
                                CrystalGradeLov(),
                                SwarovskiLov(),
                            ]),
                            KV(2, 'CZ', [
                                GemColorComponent(),
                                GemShapeComponent(),
                                GemCutComponent(),
                                GemSizeLov()
                            ]),
                            KV(3, 'Marcasite', [
                                MaracasiteGradeComponent(),
                                SwarovskiLov(),
                            ]),
                            KV(4, 'Synthesized', [
                                GemTextureComponent(),
                                GemColorComponent(),
                                GemShapeComponent(),
                                GemCutComponent(),
                                DrillTypeComponent(),
                                GemSizeLov()
                            ]),
                            KV(5, 'Authentic', [
                                GemColorComponent(),
                                GemTextureComponent(),
                                GemGradeComponent(),
                                GemShapeComponent(),
                                GemCutComponent(),
                                DrillTypeComponent(),
                                GemSizeLov()
                            ]),
                            KV(6, 'Diamond', [
                                DiamondColorComponent(),
                                DiamondShineComponent(),
                                GemShapeComponent(),
                                GemCutComponent(),
                                GemSizeLov()
                            ])
                        ])
                    ]),
                    KV(1, 'Metal', [
                        MetalTypeLov(),
                        MetalBodyLov(),
                        MetalBody2Lov(),
                    ]),
                    KV(2, 'Mold', [
                        MoldTypeLov(),   # <---------------------+
                        MetalBodyLov(),  # <---------------------|---+
                        MGStaticLov(),   # <---------------------|---|---+
                        ContextBasedRunningNumberLov('mold-', 5, 1 + 4 + 1),
                        OptionalMoldSizeNameLov()
                    ]),
                    KV(4, 'MetalComponent', [
                        MetalComponentTypeLov(),
                        MetalBodyLov(),
                        # TODO: Running Number
                    ]),
                    KV(5, 'OtherComponent', [
                        OtherComponentTypeLov(),
                        SkinBodyLov(),
                        # TODO : Running Number
                    ])
                ])
            ]),
            KV(1, 'สินค้า', [
                StaticComponent('WipType', 2, [
                    KV(80, 'สินค้าสำเร็จรูป', [
                        MetalBodyLov(),
                        StyleComponent(),
                        StoneLov(),
                        UnconstraintedComponent(4, '0'),
                        SkinTypeComponent(),
                        DipTypeComponent()
                    ]),
                    KV('**', 'สินค้ากึ่งสำเร็จรูป', [
                        MetalBodyLov(),
                        StyleComponent(),
                        StoneLov(),
                        UnconstraintedComponent(4, '0'),
                        SkinTypeComponent(),
                        DipTypeComponent(),
                        ContextBasedRunningNumberLov('wip-', 2)
                    ])
                ])
            ]),
            KV(2, 'แบบกึ่งสำเร็จรูป', [
                StaticComponent('WipMoldType', 2, [
                    KV('**', 'ประเภทแบบกึ่งสำเร็จรูป', [
                        MoldTypeLov(),   # <---------------------+
                        MetalBodyLov(),  # <---------------------|---+
                        MGStaticLov(),   # <---------------------|---|---+
                        ContextBasedRunningNumberLov('mold-', 5, 1 + 4 + 1),
                        MoldSizeNameLov(),  # No longer optional :)
                        ContextBasedRunningNumberLov('wip-', 2)
                    ])
                ])
            ]),
            KV(3, 'เศษวัสดุจากกระบวนการผลิต', [
                ScrapLov(),
                MetalBodyLov(),
            ]),
            KV(4, 'อุปกรณ์ (เพื่อการซ่อมแซมและบำรุงรักษา)', [
                OfficeSupplyTypeLov(),
            ]),
            KV(5, 'Equipment', []),
            KV(7, 'อะไหล่', [
                SparePartLov(),
            ]),
        ])
    ]


class IntramaneeCode(object):
    allowed_wildcard = True

    def __init__(self, code_, rules_):
        self.rules = rules_
        self.code = code_
        (self.length, self.parsed, self.leftover, self.trail, self.lastComp) = self.parse()

    def suggest(self, typed, limit=-1):
        if not self.validate():
            utils.LOG.error('Calling suggestion on invalid Intramanee code %s' % str(self))
        if not self.lastComp:
            return []
        return self.lastComp.suggest(typed, limit)

    def tail(self):
        (comp, code, label) = self.trail[-1:][0]
        kv = comp.get(code)
        return kv

    def validate(self):
        return len(self.leftover) == 0

    def is_completed(self):
        """

        :return: - True if lastComp is not None or lastComp is optional.
        """
        return self.lastComp is None or self.lastComp.is_optional()

    def use_wildcard(self):
        return "#" in self.code

    def parse(self, i=0, rules=None):
        """
        Parse
        :return - parsed index, parsed string, unable to parse string, component trail, nextComp
        """
        if rules is None:
            rules = self.rules
        trail = []
        lastComp = None
        for ix, component in enumerate(rules):
            length = component.length
            compare = self.code[i:i+length]
            component.context = (self.code[:i], compare)

            # nothing to compare
            if len(compare) == 0:
                if lastComp is None:
                    lastComp = component

            if lastComp is not None:
                break

            # is wildcard ?
            wildcard = (compare == ''.rjust(length, '#'))
            if component.allowed_wildcard and self.allowed_wildcard and wildcard:
                i += length
                trail.append([component, compare, compare])
                continue

            # check compare against
            kv = component.get(compare)
            if kv is not None:
                i += length
                trail.append([component, compare, kv.label])
                if kv.has_child():
                    (i, x, y, tail, lastComp) = self.parse(i, kv.children)
                    trail.extend(tail)
            else:
                lastComp = component
                break
        return i, self.code[:i], self.code[i:], trail, lastComp

    def __len__(self):
        return len(self.code)

    def __str__(self):
        return self.code


def register_typed_code(type, clz):
    TYPED_CODES[type] = clz


def typed_code_factory(type, code):
    if type in TYPED_CODES:
        return TYPED_CODES[type](code)
    raise ValidationError('Unknown type_code type: "%s"' % type)


class TypedCode(IntramaneeCode):

    def __init__(self, type_, code_, rules):
        super(TypedCode, self).__init__(code_, rules)
        self.type = type_

    def __str__(self):
        return '%s-%s' % (self.type, self.code)

    @staticmethod
    def check(code_):
        if '-' not in code_:
            raise ValidationError('%s is invalid' % code_)

    @staticmethod
    def translate(input, output='label', allow_incomplete=False):

        if output not in ['label', 'object', 'extract']:
            raise BadParameterError("output format '%s' is invalid" % output)

        # assume default type = 'stock'
        (type, code) = input.split('-', 1) if '-' in input else ('stock', input)

        c = typed_code_factory(type, code)

        if c is None:
            raise ValidationError("Unable to parse '%s'" % code)

        if not allow_incomplete and output not in ['extract'] and len(c.leftover) > 0:
            raise ValidationError("Unable to parse partial of code near '%s' of %s" % (c.leftover, str(c)))

        if 'label' == output:
            return c.tail().label

        if 'extract' == output:
            return c.trail

        return c

    @staticmethod
    def compare(pattern_, code_):
        if isinstance(pattern_, TypedCode):
            pattern_ = str(pattern_)
        elif isinstance(pattern_, basestring):
            pattern_ = pattern_
        else:
            raise ValidationError('Unable to handle %s' % type(pattern_))

        p = re.compile('^'+re.sub(r'#+', lambda x: ('[#0-9a-z]{'+str(len(x.group(0)))+'}'), pattern_), re.IGNORECASE)
        return p.match(str(code_.code) if isinstance(code_, TypedCode) else code_) is not None

    def matched(self, pattern_):
        return TypedCode.compare(pattern_, self)

    def __eq__(self, other):
        return str(self) == str(other)

    def __repr__(self):
        return str(self)


class StockCode(TypedCode):

    def __init__(self, code_):
        super(StockCode, self).__init__('stock', code_, RULES)

    def create_wip(self, next_operation_code):
        """
        Create WIP Code from self, given that current StockCode is 180

        :raises ValueError if code is not completed.
        :raises ValueError if given code is not 180.
        :raises ValueError if next_operation_code is too short.
        :raises ValueError if generated code is not completed.
        :return:
        """
        if not self.is_completed():
            raise ValueError(_("ERR_CANNOT_CREATE_WIP_CODE_FROM_UNCOMPLETED_CODE"))

        next_operation_code = str(next_operation_code)
        if next_operation_code is None or len(next_operation_code) < 4:
            raise ValueError(_("ERR_CANNOT_CREATE_WIP_CODE_BAD_NEXT_OPERATION_CODE"))

        # Case IMC180
        if self.matched('###180'):
            # Extract next operation
            code_str = "IMC1" + next_operation_code[1:3] + self.code[6:]
            code = StockCode(code_str)
        # Case MOLD IMC02[123]
        elif self.matched('###021') or self.matched('###022') or self.matched('###023'):
            code_str = "IMC2" + next_operation_code[1:3] + self.code[5:]
            code = StockCode(code_str)
        else:
            raise ValueError(_("ERR_CANNOT_CREATE_WIP_CODE_FROM_NON_180_STOCK_CODE"))

        # inject running number
        if not isinstance(code.lastComp, ContextBasedRunningNumberLov):
            raise ValueError(_("ERR_FAILED_TO_CREATE_PROPER_CODE: %(reason)s") % {
                'reason': "invalid last component %s" % str(code.lastComp)
            })
        new_comp = code.lastComp.new_code()
        code_str += new_comp
        code = StockCode(code_str)
        if not code.is_completed():
            raise ValueError(_("ERR_FAILED_TO_CREATE_COMPLETED_WIP_CODE: %(generated_code)s") % {
                'generated_code': code_str
            })
        return code


class StoneTypeCode(TypedCode):

    def __init__(self, code_=''):
        super(StoneTypeCode, self).__init__('stone', code_, [
            StoneLov()
        ])


class MetalCode(TypedCode):

    def __init__(self, code_=''):
        super(MetalCode, self).__init__('metal', code_, [
            MetalBodyLov()
        ])


class StyleCode(TypedCode):

    def __init__(self, code_=''):
        super(StyleCode, self).__init__('style', code_, [
            StyleComponent()
        ])


class FinishCode(TypedCode):

    def __init__(self, code_=''):
        super(FinishCode, self).__init__('finish', code_, [
            SkinTypeComponent()
        ])


class PlatingCode(TypedCode):

    def __init__(self, code_=''):
        super(PlatingCode, self).__init__('plating', code_, [
            DipTypeComponent()
        ])


class TaskCode(TypedCode):

    def __init__(self, code_):
        super(TaskCode, self).__init__('task', code_, [
            TaskCodeConfigComponent()
        ])


class CustomerCode(TypedCode):

    def __init__(self, code_):
        super(CustomerCode, self).__init__('cust', code_, [
            CompanyComponent()
        ])

TYPED_CODES = {
    "stock": StockCode,
    "cust": CustomerCode,
    "style": StyleCode,
    "task": TaskCode,
    "metal": MetalCode,
    "plating": PlatingCode,
    "stone": StoneTypeCode,
    "finish": FinishCode,
}


Tree = utils.enum(
    SAMPLE='sampleCreation',
    MASTER='masterModeling'
)

Process = utils.enum(
    Hammer=TaskCode('4144'),
    Cast=TaskCode('5331'),
    Awt=TaskCode('5291'),
    Sprue=TaskCode('4143'),
    LaserEtch=TaskCode('4154'),
    MakeRubberMold=TaskCode('5261'),
    Solder=TaskCode('5351'),
    WaxInject=TaskCode('5271'),
    WaxSetting=TaskCode('5281'),
    HandSetting=TaskCode('5381'),
    Tumble=TaskCode('5391'),
    HighPolish=TaskCode('5401'),
    Sandblast=TaskCode('5402'),
    SatinFinish=TaskCode('5403'),
    LightlyBrush=TaskCode('5404'),
    HeavilyBrush=TaskCode('5405'),
    SemiPolish=TaskCode('5406'),
    Repolish=TaskCode('5407'),
    DiamondCut=TaskCode('5408'),
    Plate=TaskCode('5421'),
    Oxidize=TaskCode('5422'),
    Glue=TaskCode('5431'),
    DCMasterModel=TaskCode('4171'),
    QCMasterModel=TaskCode('5461'),
    QCCasting=TaskCode('5462'),
    QCForm=TaskCode('5463'),
    QCWaxSetting=TaskCode('5464'),
    QCHandSetting=TaskCode('5465'),
    QCFinishing=TaskCode('5466'),
    QCPlating=TaskCode('5467'),
    QCFinal=TaskCode('5468'),
    QCRawMaterial=TaskCode('5469'),
    FileNSand=TaskCode('5341')
)


Finishes = utils.enum(
    HighPolished=FinishCode('HP'),
    Hammered=FinishCode('HA'),
    Sandblasted=FinishCode('SB'),
    Satin=FinishCode('ST'),
    LightBrushed=FinishCode('LB'),
    HeavilyBrushed=FinishCode('HB'),
    Tumbled=FinishCode('TU'),
    Worn=FinishCode('WO'),
    DiamondCut=FinishCode('DC'),
    F2=FinishCode('F2'),
    F3=FinishCode('F3'),
    CA=FinishCode('CA'),
)


Styles = utils.enum(
    Ring=StyleCode('RI'),
    Earrings=StyleCode('ER'),
    Necklace=StyleCode('NL'),
    Bracelet=StyleCode('BL'),
    Bangle=StyleCode('BA'),
    GiftItem=StyleCode('GI'),
    Part=StyleCode('XX'),
    Bead=StyleCode('BD'),        # TODO: Verify code, -- need this from DOME's update file
    Cufflinks=StyleCode('CF'),   # TODO: Verify code,
    Brooch=StyleCode('BR'),      # TODO: Verify code,
    Choker=StyleCode('CH')
)


StoneTypes = utils.enum(
    Crystal=StoneTypeCode('1'),
    CZ=StoneTypeCode('2'),
    Marcasite=StoneTypeCode('3'),
    Synthetic=StoneTypeCode('4'),
    Genuine=StoneTypeCode('5'),
    Diamond=StoneTypeCode('6'),
    Various=StoneTypeCode('7')
)

PlatingTypes = utils.enum(
    FTKGold=PlatingCode('14'),
    ETKGold=PlatingCode('18'),
    TFKGold=PlatingCode('24'),
    PinkGold=PlatingCode('PG'),
    Rhodium=PlatingCode('RH'),
    BlackRuthenium=PlatingCode('BR'),
    TwoColors=PlatingCode('2T'),
    ThreeColors=PlatingCode('3T'),
    Silver=PlatingCode('SA'),
    Oxidized=PlatingCode('OX'),
    PinkGoldECoat=PlatingCode('PE'),
    SilverECoat=PlatingCode('SE'),
    YellowBronzeECoat=PlatingCode('YE'),
    BlackRutheniumECoat=PlatingCode('BE'),
    GoldECoat=PlatingCode('GE'),
    RhodiumECoat=PlatingCode('RE'),
    OxidizedECoat=PlatingCode('OE'),
)


class Spec2Process(object):
    condition = None
    actions = []

    def __init__(self, condition_, actions_=[]):
        if isinstance(condition_, list):
            self.condition = condition_
        else:
            self.condition = [condition_]
        self.actions = actions_


SPEC2PROCESS = {
    'metal': [
        Spec2Process(MetalCode(''), [
            (Tree.SAMPLE, Process.Cast, StockCode('###01#@input')),
        ])
    ],
    'style': [
        Spec2Process(Styles.Ring, [
            (Tree.MASTER, Process.Awt, StockCode('WAX')),               # TODO: Stock Code for WAX
            (Tree.MASTER, Process.Cast, StockCode('IMC011SILV')),
            (Tree.MASTER, Process.Sprue, StockCode('Copper Wire')),     # TODO: Stock Code for Copper Wire
            (Tree.MASTER, Process.QCMasterModel),
            (Tree.MASTER, Process.DCMasterModel),
            (Tree.SAMPLE, Process.WaxInject, '@metal'),
            (Tree.SAMPLE, Process.Awt, StockCode('WAX')),               # TODO: Stock Code for WAX
            (Tree.SAMPLE, Process.Cast, '@metal'),
            (Tree.SAMPLE, Process.QCCasting),
            (Tree.SAMPLE, Process.FileNSand),
        ])
    ],
    'stone': [
        Spec2Process(StoneTypes.Crystal, [
            (Tree.SAMPLE, Process.Glue, '@input'),
            (Tree.SAMPLE, Process.QCFinal)
        ]),
        Spec2Process(StoneTypes.CZ, [
            (Tree.SAMPLE, Process.HandSetting, '@input'),
            (Tree.SAMPLE, Process.QCHandSetting)
        ]),
        Spec2Process(StoneTypes.Marcasite, [
            (Tree.SAMPLE, Process.Oxidize),
            (Tree.SAMPLE, Process.Glue, '@input'),
            (Tree.SAMPLE, Process.HighPolish),
            (Tree.SAMPLE, Process.QCFinishing)
        ]),
        Spec2Process(StoneTypes.Synthetic, [
            (Tree.SAMPLE, Process.HandSetting, '@input'),
            (Tree.SAMPLE, Process.QCHandSetting)
        ]),
        Spec2Process(StoneTypes.Genuine, [
            (Tree.SAMPLE, Process.HandSetting, '@input'),
            (Tree.SAMPLE, Process.QCHandSetting)
        ]),
        Spec2Process(StoneTypes.Diamond, [
            (Tree.SAMPLE, Process.HandSetting, '@input'),
            (Tree.SAMPLE, Process.QCHandSetting)
        ])
    ],
    'finish': [  # TODO: Define rule for F2, F3, CA
        Spec2Process(Finishes.HighPolished, [
            (Tree.SAMPLE, Process.HighPolish),
            (Tree.SAMPLE, Process.QCFinishing)
        ]),
        Spec2Process(Finishes.Hammered, [
            (Tree.MASTER, Process.Hammer),
            (Tree.SAMPLE, Process.QCFinishing)
        ]),
        Spec2Process(Finishes.Sandblasted, [
            (Tree.SAMPLE, Process.Sandblast),
            (Tree.SAMPLE, Process.QCFinishing)
        ]),
        Spec2Process(Finishes.Satin, [
            (Tree.SAMPLE, Process.SatinFinish),
            (Tree.SAMPLE, Process.QCFinishing)
        ]),
        Spec2Process(Finishes.LightBrushed, [
            (Tree.SAMPLE, Process.LightlyBrush),
            (Tree.SAMPLE, Process.QCFinishing)
        ]),
        Spec2Process(Finishes.HeavilyBrushed, [
            (Tree.SAMPLE, Process.HeavilyBrush),
            (Tree.SAMPLE, Process.QCFinishing)
        ]),
        Spec2Process(Finishes.Tumbled, [
            (Tree.SAMPLE, Process.Tumble),
            (Tree.SAMPLE, Process.QCFinishing)
        ]),
        Spec2Process(Finishes.Worn, [
            (Tree.SAMPLE, Process.SemiPolish),
            (Tree.SAMPLE, Process.Repolish),
            (Tree.SAMPLE, Process.QCFinishing)
        ]),
        Spec2Process(Finishes.DiamondCut, [
            (Tree.SAMPLE, Process.DiamondCut),
            (Tree.SAMPLE, Process.QCFinishing)
        ])
    ],
    'plating': [
        Spec2Process(PlatingTypes.Silver, [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017S999UAG621')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC019CHEMACTIVX')),
        ]),
        Spec2Process([PlatingTypes.TFKGold, {"metal": "metal-BNZY"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROB')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROC')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BAS')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660LVL')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BRI')),
        ]),
        Spec2Process([PlatingTypes.TFKGold, {"metal": "metal-SILV"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017S999UAG621')),
        ]),
        Spec2Process([PlatingTypes.TFKGold], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017PALLDEC300')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R1')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R2')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R3')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017G999LGGF24')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC019CHEMACTIVX')),
        ]),
        Spec2Process([PlatingTypes.ETKGold, {"metal": "metal-BNZY"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROB')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROC')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BAS')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660LVL')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BRI')),
        ]),
        Spec2Process([PlatingTypes.ETKGold, {"metal": "metal-SILV"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017S999UAG621')),
        ]),
        Spec2Process(PlatingTypes.ETKGold, [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017PALLDEC300')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R1')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R2')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R3')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18EPI730')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC019CHEMACTIVX')),
        ]),
        Spec2Process([PlatingTypes.FTKGold, {"metal": "metal-BNZY"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROB')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROC')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BAS')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660LVL')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BRI')),
        ]),
        Spec2Process([PlatingTypes.FTKGold, {"metal": "metal-SILV"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017S999UAG621')),
        ]),
        Spec2Process(PlatingTypes.FTKGold, [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017PALLDEC300')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R1')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R2')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R3')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY14PARDOR')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC019CHEMANTIOX')),
        ]),
        Spec2Process([PlatingTypes.PinkGold, {"metal": "metal-BNZY"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROB')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROC')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BAS')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660LVL')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BRI')),
        ]),
        Spec2Process([PlatingTypes.PinkGold, {"metal": "metal-SILV"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017S999UAG621')),
        ]),
        Spec2Process(PlatingTypes.PinkGold, [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017PALLDEC300')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GR18OMG160')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC019CHEMACTIVX')),
        ]),
        Spec2Process([PlatingTypes.BlackRuthenium, {"metal": "metal-BNZY"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROB')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROC')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BAS')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660LVL')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BRI')),
        ]),
        Spec2Process([PlatingTypes.BlackRuthenium, {"metal": "metal-SILV"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017S999UAG621')),
        ]),
        Spec2Process(PlatingTypes.BlackRuthenium, [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R1')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R2')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017GY18O180R3')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017BLRUR479R')),
        ]),
        Spec2Process([PlatingTypes.Rhodium, {"metal": "metal-BNZY"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROB')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPRCUPROC')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BAS')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660LVL')),
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017CPPR660BRI')),
        ]),
        Spec2Process([PlatingTypes.Rhodium, {"metal": "metal-SILV"}], [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017S999UAG621')),
        ]),
        Spec2Process(PlatingTypes.Rhodium, [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC017RHODIWG-C2')),
        ]),
        Spec2Process(PlatingTypes.Oxidized, [
            (Tree.SAMPLE, Process.Plate, StockCode('IMC40001')),
        ]),
    ]
}
