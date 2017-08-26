from documents import OffHours, OffHoursRange
from unittest import TestCase
from datetime import datetime
from pymongo.errors import DuplicateKeyError


class TestCalendar(TestCase):

    @classmethod
    def setUpClass(cls):
        print("Clean up all Offhours content")
        OffHours.manager.delete()

    def test_calendar_write(self):
        o = OffHours()
        o.start_time = datetime(2000, 11, 10, 0)
        o.end_time = datetime(2000, 11, 11, 0)
        o.uid = "test:collide_me"
        o.save()

        r = OffHours(o.object_id)
        self.assertEqual(r.object_id, o.object_id)
        self.assertEqual(r.start_time, o.start_time)
        self.assertEqual(r.end_time, o.end_time)
        self.assertEqual(r.uid, o.uid)

        dup = OffHours()
        dup.end_time = datetime.now()
        dup.start_time = datetime.now()
        dup.uid = o.uid
        self.assertRaises(DuplicateKeyError, lambda: dup.save())

    def test_calendar_query(self):
        def is_between(offhour, bracket):
            return bracket[0] <= offhour.end and bracket[1] >= offhour.start

        # Prepare date information
        item_indices = xrange(1, 31)
        for i in item_indices:
            o = OffHours()
            o.start_time = datetime(2000, 12, i, 12)
            o.end_time = datetime(2000, 12, i, 13)
            o.uid = "test_query:%s" % i
            o.save()

        OffHoursRange.sync()

        count = OffHours.manager.count(cond={
            'uid': {
                '$regex': '^test_query'
            }
        })
        self.assertEqual(count, len(item_indices))

        # Test Query based on datetime - call static between method?
        # : against now()
        output = OffHoursRange.between(start_time=datetime.now())
        self.assertEqual(0, len(output), "Query against current minute should return 0 results")
        # : against start
        start_time = datetime(2000, 12, 1, 0)
        output = OffHoursRange.between(start_time=datetime(2000, 12, 1, 0))
        count = len(item_indices)
        self.assertEqual(count, len(output), "Query against start day should return %s results" % count)
        self.assertTrue(all(o.end > start_time for o in output), "All results must be within range.")
        # : between start + 2 days
        bracket = (datetime(2000, 12, 1, 0), datetime(2000, 12, 3, 0))
        output = OffHoursRange.between(start_time=bracket[0], end_time=bracket[1])
        self.assertEqual(2, len(output), "Query between start day, and +2 days should return 2 results")
        self.assertTrue(all(is_between(o, bracket) for o in output), "All results must be within range.")
        # : between overlapping start_time
        bracket = (datetime(2000, 12, 1, 12, 30), datetime(2000, 12, 3, 12, 30))
        output = OffHoursRange.between(start_time=bracket[0], end_time=bracket[1])
        self.assertEqual(3, len(output), "Query between start day, and +2 days (overlap) should return 3 results")
        self.assertTrue(all(is_between(o, bracket) for o in output), "All results must be within range.")

    @classmethod
    def tearDownClass(cls):
        ics_url = "https://www.google.com/calendar/ical/syllistudio.com_8m87hbkid7o5bqfrf5sn0crei8%40group.calendar.google.com/public/basic.ics"
        OffHours.sync(ics_url)
