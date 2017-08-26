__author__ = 'wasansae-ngow'

import ConfigParser
from django.utils.translation import ugettext as _
from intramanee.settings import CONF_ROOT


class UOM(object):

    uoms = {}
    grouped_uoms = {}

    def __init__(self, uom_code, uom_label, uom_group, uom_rate):
        self.code = uom_code
        self.label = uom_label
        self.group = uom_group
        self.rate = uom_rate

    def __unicode__(self):
        return self.code

    def __str__(self):
        return unicode(self)

    def convert(self, target_uom, quantity):
        """
        Convert quantity to target UOM

        :param target_uom:
        :param quantity:
        :return:
        """

        if not isinstance(target_uom, (UOM, basestring)):
            raise Exception('Expect input UOM as UOM class object or string')

        if target_uom is self:
            return quantity

        if isinstance(target_uom, basestring) and target_uom not in UOM.uoms:
            raise KeyError('Input UOM "' + target_uom + '" is not maintained in UOM file')

        if isinstance(target_uom, basestring):
            target_uom = UOM.uoms[target_uom]

        if not self.convertible(target_uom):
            raise ValueError(_("ERR_CANNOT_CONVERT_UOM: %(from)s to %(to)s:") % {
                'from': self.code,
                'to': target_uom
            })

        if target_uom.rate == 0:
            raise Exception('target_uom (%s) rate is 0' % str(target_uom))

        return quantity * self.rate / target_uom.rate

    # Check if target UOM is convertible
    def convertible(self, target_uom):
        return self.group == target_uom.group

    @staticmethod
    def has(uom_code):
        return (uom_code if isinstance(uom_code, basestring) else uom_code.code) in UOM.uoms

    @staticmethod
    def factory(uom_code):
        """
        Build and return requested UOM object

        :param uom_code:
        :return: requested UOM Object
        :raise: KeyError if uom_name is not found, Exception if
        """
        if not UOM.has(uom_code):
            raise KeyError('Input UOM "' + uom_code + '" is not defined')

        return UOM.uoms[uom_code]

# Read UOM from config file
conf = ConfigParser.ConfigParser()
conf.read('%s/uom.ini' % CONF_ROOT)

for code in conf.sections():
    item_list = conf.items(code)
    d = dict(item_list)

    u = UOM(d['code'], d['label'], d['group'], float(d['rate']))
    UOM.uoms[d['code']] = u
    if d['group'] not in UOM.grouped_uoms:
        UOM.grouped_uoms[d['group']] = []
    UOM.grouped_uoms[d['group']].append({'code': d['code'], 'label': d['label']})
