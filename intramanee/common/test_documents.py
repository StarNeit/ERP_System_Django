__author__ = 'peat'
from unittest import TestCase
from intramanee.common.models import IntraUser
from intramanee.common.task import TaskGroup
import intramanee.common.documents as docs


class TestBaseDoc(docs.Doc):
    field_a = docs.FieldString(default="default_value")

    class Meta:
        collection_name = 'test'


class TestExtendDoc(docs.Validatable, TestBaseDoc):
    """
    Also use multiple inheritance
    """
    field_a = docs.FieldNumeric(default=2)
    field_b = docs.FieldString(default="default_value2")

    class Meta:
        collection_name = ':extend'


class TestExtenderDoc(TestExtendDoc):
    field_b = docs.FieldString(default="default_value3")
    field_c = docs.FieldString(default="exclusive_value")

    class Meta:
        collection_name = ':extender'


class TestAssigneeFieldDoc(docs.Doc):
    assignee = docs.FieldAssignee()
    group_assignee = docs.FieldAssignee(default="410")

    class Meta:
        collection_name = 'test-assignee'


class TestListFieldDoc(docs.Doc):
    listing = docs.FieldList(docs.FieldDoc(TestBaseDoc))

    class Meta:
        collection_name = 'test-listing'


class TestTupleFieldDoc(docs.Doc):
    tuple_items = docs.FieldTuple(docs.FieldNumeric(), docs.FieldNumeric(), docs.FieldString())

    class Meta:
        collection_name = 'test-tuple'


class TestingDocumentInheritance(TestCase):

    @classmethod
    def setUpClass(cls):
        TestBaseDoc.manager.delete()
        TestAssigneeFieldDoc.manager.delete()
        TestListFieldDoc.manager.delete()
        IntraUser.objects.create_user('tester', 'TestMan', '123')

    def test_extension(self):
        """
        Test inheritance of class hierarchy, and saving mechanic of Document.

        :return:
        """
        b = TestBaseDoc()
        b.save()

        o = TestExtendDoc()
        o.save()

        d = TestExtendDoc()
        d.field_a = 3
        d.save()

        extend = TestExtendDoc.manager.find()
        # Read the database and make sure that all extended document has a perfect values recorded,
        # even the override ones.
        self.assertTrue(all(o.field_a >= 2 and "default_value2" == o.field_b for o in extend))

        # Read the database with base class, give all instances with respective classes.
        base_extend = TestBaseDoc.manager.find()
        self.assertEqual(len(base_extend), 3)
        self.assertEqual(len(filter(lambda o: isinstance(o, TestBaseDoc), base_extend)), 3)
        self.assertEqual(len(filter(lambda o: isinstance(o, TestExtendDoc), base_extend)), 2)

        # Test for 3rd case
        e = TestExtenderDoc()
        e.field_a = 7
        e.save()
        extender = TestExtenderDoc.manager.find()
        self.assertEqual(len(extender), 1)
        self.assertEqual(7, extender[0].field_a)
        self.assertEqual("default_value3", extender[0].field_b)
        self.assertEqual("exclusive_value", extender[0].field_c)
        self.assertTrue(isinstance(extender[0], TestBaseDoc))
        self.assertTrue(isinstance(extender[0], TestExtendDoc))
        self.assertTrue(isinstance(extender[0], TestExtenderDoc))

        extend_extender = TestExtendDoc.manager.find()
        self.assertEqual(len(extend_extender), 3)
        self.assertTrue(len(filter(lambda o: "default_value2" == o.field_b, extend_extender)), 2)
        self.assertTrue(len(filter(lambda o: "default_value3" == o.field_b, extend_extender)), 1)
        self.assertTrue(len(filter(lambda o: o.field_a > 5, extend_extender)), 1)

        r = TestBaseDoc(o.object_id)
        self.assertFalse(isinstance(r, TestExtendDoc), "Constructor cannot generate correct class instance.")
        print("\tWARNING - Using Constructor with ObjectId to create extended instance is extremely discouraged")

        r = TestBaseDoc.of('_id', o.object_id)
        self.assertTrue(isinstance(r, TestExtendDoc))

    def test_listing_field(self):
        b = TestBaseDoc()
        b.field_a = "500"
        b.save()

        c = TestExtendDoc()
        c.field_a = 300
        c.field_b = "400"
        c.save()

        a = TestListFieldDoc()
        a.listing.append(b)
        a.listing.append(c)
        a.save()

        self.assertEqual(len(a.listing), 2)

        loaded = TestListFieldDoc(a.object_id)
        self.assertEqual(len(loaded.listing), 2)
        self.assertTrue(b.object_id in loaded.listing)
        self.assertTrue(c.object_id in loaded.listing)

        loaded.populate('listing')
        self.assertTrue(isinstance(loaded.listing[0], TestBaseDoc))
        self.assertTrue(isinstance(loaded.listing[1], TestExtendDoc))
        self.assertEqual(loaded.listing[0].field_a, "500")
        self.assertEqual(loaded.listing[1].field_a, 300)
        self.assertEqual(loaded.listing[1].field_b, "400")

        # Check document instantiation (FieldList, default value linked)
        b = TestListFieldDoc()
        self.assertEqual(len(b.listing), 0)

    def test_assignee_field(self):
        u = IntraUser.objects.all()[0]
        a = TestAssigneeFieldDoc()
        # Assignable by code
        a.assignee = u.code
        self.assertTrue(isinstance(a.assignee, IntraUser), "assignee must be IntraUser instance")
        self.assertTrue(isinstance(a.serialized()['assignee'], basestring), "assignee must be string instance")
        self.assertEqual(a.serialized()['assignee'], str(u.code))
        # Assignable by instance
        a.assignee = u
        self.assertTrue(isinstance(a.assignee, IntraUser), "assignee must be IntraUser instance")
        self.assertTrue(isinstance(a.serialized()['assignee'], basestring), "assignee must be string instance")
        self.assertEqual(a.serialized()['assignee'], str(u.code))
        self.assertEqual(a.group_assignee, "410", 'group_assignee must be equals to defualt value')
        # Assigned as group
        a.group_assignee = "414"
        self.assertTrue(isinstance(a.group_assignee, TaskGroup), "once assigned, it should be converted to TaskGroup")
        a.save()

        r = TestAssigneeFieldDoc(a.object_id)
        self.assertTrue(isinstance(r.assignee, IntraUser), 'Assignee must be IntraUser after populated')
        self.assertTrue(isinstance(r.group_assignee, TaskGroup), "Assignee should be mapped to TaskGroup")
        self.assertEqual(r.group_assignee, a.group_assignee, 'group_assignee must be equal')

    def test_options(self):
        # Simple Get and Set
        docs.Options.set('test-key', {'key': 555})
        value = docs.Options.get('test-key')
        self.assertEqual(value, {'key': 555})

        # Test override
        docs.Options.set('test-key', {'key': 900, 'key2': 530})
        value = docs.Options.get('test-key')
        self.assertEqual(value, {'key': 900, 'key2': 530})

    def test_tuple_field(self):
        o = TestTupleFieldDoc()
        good_value = (5, 5, 'test')
        bad_value = (5, 15, 55)

        def bad_assigment():
            o.tuple_items = bad_value

        self.assertRaises(docs.FieldInvalidateError, bad_assigment)
        o.tuple_items = good_value
        o.save()

        loaded = TestTupleFieldDoc(o.object_id)
        self.assertEqual(loaded.tuple_items, good_value)
