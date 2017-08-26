__author__ = 'wasansae-ngow'

import ConfigParser
from intramanee.settings import CONF_ROOT
from intramanee.common.decorators import JsonSerializable


class Room(object, JsonSerializable):

    rooms = {}

    def __init__(self, room_code, room_label, room_tasks):
        self.code = room_code
        self.label = room_label
        self.tasks = room_tasks

    def as_json(self):
        return {
            'code': self.code,
            'label': self.label,
            'tasks': self.tasks
        }

    @staticmethod
    def has(room_code):

        if not isinstance(room_code, basestring):
            raise Exception('Expect input UOM as string')

        return room_code in Room.rooms

    @staticmethod
    def task_room(task_number):

        if not isinstance(task_number, (basestring, int)):
            raise Exception('Expect task code as int or string')

        for index in Room.rooms:
            if int(task_number) in Room.rooms[index].tasks:
                return Room.rooms[index]

        return None

    @staticmethod
    def factory(room_code):
        """
        Build and return requested Room object

        :param room_code:
        :return: requested Room Object
        :raise: KeyError if room_name is not found, Exception if
        """
        if not Room.has(room_code):
            raise KeyError('Input room "' + room_code + '" is not defined')

        return Room.rooms[room_code]

# Read Room from config file
conf = ConfigParser.ConfigParser()
conf.read('%s/room.ini' % CONF_ROOT)

for code in conf.sections():
    item_list = conf.items(code)
    d = dict(item_list)

    u = Room(d['code'], d['label'], [int(n) for n in d['tasks'].split(',') if n])
    Room.rooms[d['code']] = u
