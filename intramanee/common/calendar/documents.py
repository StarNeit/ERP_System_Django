__author__ = 'peat'
import parser
from intramanee.common import documents as docs
from datetime import datetime
from intramanee.settings import OFFHOURS_ICS_URL
from intramanee.common.errors import ProhibitedError


class OffHoursRange(docs.Doc):
    start = docs.FieldDateTime()
    end = docs.FieldDateTime()

    @classmethod
    def sync(cls, are_touching=None):
        """

        :param are_touching:
        :return:
        """
        if are_touching is None:
            are_touching = lambda x, y: y - x == 1

        offhours = OffHours.manager.find(cond={
            '$sort': 'start_time'
        })
        output = []

        new_start = None
        new_end = None

        length = len(offhours)
        for i, offhour in enumerate(offhours):
            if new_start is None:
                new_start = offhour.start_time
                new_end = offhour.end_time
            elif new_end >= offhour.start_time or are_touching(new_end, offhour.start_time):
                new_end = max(offhour.end_time, new_end)
            else:
                output.append([new_start, new_end])
                new_start = offhour.start_time
                new_end = offhour.end_time

            # Last item
            if i + 1 == length:
                output.append([new_start, new_end])

        bulk = cls.manager.o.initialize_ordered_bulk_op()
        bulk.find({}).remove()      # delete everything
        for entry in output:
            bulk.insert({'start': entry[0], 'end': entry[1]})
        print bulk.execute()

    @classmethod
    def between(cls, start_time=None, end_time=None):
        """
        Query any items that overlaps between start_time, and end_time
        if both start_time: and end_time: is omitted, start_time=now() will be used.

        :param start_time: optional
        :param end_time: optional
        :return:
        """
        # Sanitize input
        if start_time is None and end_time is None:
            start_time = datetime.now()

        # Build condition
        cond = {
            "end": {"$gt": start_time},
            "$sort": "start"
        }
        if end_time is not None:
            cond["start"] = {"$lt": end_time}

        return cls.manager.find(cond=cond)

    class Meta:
        collection_name = "offhours-range"
        indices = [
            ([("start_time", 1)], {"background": True, "sparse": False}),   # improve search performance
            ([("end_time", -1)], {"background": True, "sparse": False})     # improve search performance
        ]


class OffHours(docs.Doc):
    start_time = docs.FieldDateTime()
    end_time = docs.FieldDateTime()
    uid = docs.FieldString()

    def __init__(self, object_id=None):
        super(OffHours, self).__init__(object_id)

    def __lt__(self, other):
        return self.start_time < other.start_time

    def __gt__(self, other):
        return self.start_time > other.start_time

    def __repr__(self):
        return "%s [%s - %s]" % (self.uid, self.start_time, self.end_time)

    @staticmethod
    def sync(ics_url=None, verbose=False):
        ics_url = ics_url if ics_url is not None else OFFHOURS_ICS_URL
        if ics_url is None:
            raise ProhibitedError("unable to sync() ics_url must not be null")
        if verbose:
            print("Performing sync with URL=%s" % ics_url)
        # download from ics_url
        p = parser.CalendarParser(ics_url=ics_url)
        bulk = OffHours.manager.o.initialize_ordered_bulk_op()
        for event in p.parse_calendar():
            uid = "%s/%s" % (event.recurrence_id, event.uid)
            bulk.find({'uid': uid}).upsert().update({'$set': {
                'uid': uid,
                'start_time': event.start_time,
                'end_time': event.end_time
            }})
        r = bulk.execute()
        if verbose:
            print("Sync result:")
            for o in r.iteritems():
                print("\t%s = %s" % o)
        OffHoursRange.sync()
        return r

    class Meta:
        collection_name = "offhours"
        indices = [
            ([("uid", 1)], {"unique": True, "sparse": False}),
            ([("start_time", 1)], {"background": True, "sparse": False})    # improve search performance
        ]
