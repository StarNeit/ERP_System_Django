__author__ = 'wasansae-ngow'

import ConfigParser
from intramanee.settings import CONF_ROOT


class Location(object):

    locations = {}

    def __init__(self, location_code, location_label, location_tasks):
        self.code = location_code
        self.label = location_label
        self.tasks = location_tasks

    @staticmethod
    def has(location_code):

        if not isinstance(location_code, basestring):
            raise Exception('Expect input UOM as string')

        return location_code in Location.locations

    @staticmethod
    def task_location(task_number):

        if not isinstance(task_number, (basestring, int)):
            raise Exception('Expect task code as int or string')

        for index in Location.locations:
            if str(task_number) in Location.locations[index].tasks:
                return Location.locations[index]

        return None

    @staticmethod
    def factory(location_code):
        """
        Build and return requested Location object

        :param location_code:
        :return: requested Location Object
        :raise: KeyError if location_name is not found, Exception if
        """
        if not Location.has(location_code):
            raise KeyError('Input location "' + location_code + '" is not defined')

        return Location.locations[location_code]

    def __str__(self):
        """
        A string representation, also used in database query conversion.

        :return:
        """
        return self.code

# Read Location from config file
conf = ConfigParser.ConfigParser()
conf.read('%s/location.ini' % CONF_ROOT)

for code in conf.sections():
    item_list = conf.items(code)
    d = dict(item_list)

    u = Location(d['code'], d['label'], d['tasks'].split(',') if 'tasks' in d else [])
    Location.locations[d['code']] = u
