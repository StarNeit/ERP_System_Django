from intramanee.settings import CONF_ROOT
from intramanee.models import IntraUser
from intramanee.common.errors import ProhibitedError
import ConfigParser
import re
import operator


class Defect(object):

    defects = {}

    def __init__(self, _code, label):
        self.code = _code
        self.label = label

    # def __repr__(self):
    #     return unicode(self.label)

    def __eq__(self, other):
        if not isinstance(other, basestring) and not isinstance(other, Defect):
            return False

        if isinstance(other, basestring):
            return self.code == other

        return self.code == other.code

    def serialize(self):
        return {
            'code': self.code,
            'label': self.label
        }

    @classmethod
    def get_defect_list(cls):
        return [v.code for k, v in cls.defects.iteritems()]

    @staticmethod
    def has(defect_code):
        return defect_code in Defect.defects

    @staticmethod
    def filter(key):
        output = []
        sorted_defects = sorted(Defect.defects.items(), key=operator.itemgetter(0))
        for k, v in sorted_defects:
            if bool(re.match(str(key), str(k), re.IGNORECASE)):
                output.append(v)
                continue
            if bool(re.match(str(key), str(v.label), re.IGNORECASE)):
                output.append(v)
                continue

        return output

    @staticmethod
    def factory(defect_code):
        """
        Build and return requested Defect object

        :param defect_code:
        :return: requested Defect Object
        :raise: KeyError if defect_code is not found, Exception if
        """
        if not Defect.has(defect_code):
            raise KeyError('Unknown defect_code: "%s"' % defect_code)

        return Defect.defects[defect_code]


# Read Task from config file
conf = ConfigParser.ConfigParser()
conf.read("%s/defect.ini" % CONF_ROOT)

for code in conf.sections():
    item_list = conf.items(code)
    d = dict(item_list)

    u = Defect(d['code'], d['label'])
    Defect.defects[d['code']] = u
