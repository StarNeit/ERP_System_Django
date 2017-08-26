__author__ = 'peat'

from django.db.models import Model as DjangoModel, ObjectDoesNotExist
from django.forms.models import model_to_dict
from bson import ObjectId
from models import UserFile
from intramanee import IntraUser
from intramanee.common.permissions import register_module_permissions as define_permission
from intramanee.common import task, uoms, signals
from codes import TypedCode, TaskCode
from django.utils.translation import ugettext as _
from utils import DictDiffer, LOG
from errors import ValidationError, BadParameterError, ProhibitedError, ResourceNotFoundError
from codes.models import LOV
import pymongo
from pymongo.errors import BulkWriteError
import datetime, time
import inspect
import six
import re
import copy
import math
from intramanee.common.utils import NOW


"""
Abstract document database provider
"""


# internal connector method.
def _db():
    # FIXME: Need to utilise configuration from settings.py
    return pymongo.MongoClient().my_database


object_id_pttrn = re.compile(r'[a-zA-Z0-9]{24}')

def _objectid(object_id_or_str):
    """

    :param basestring|ObjectId object_id_or_str:
    :return ObjectId:
    """
    if object_id_or_str is None:
        return None
    if isinstance(object_id_or_str, basestring):
        return ObjectId(object_id_or_str)
    return object_id_or_str


def doc_dict(array, key='_id'):
    """
    Utility method creating project document as a dictionary.

    :param array:
    :param key:
    :return dict:
    """
    return dict(map(lambda a: (a[key], a), array))


def _is_objectid(object_id_or_str):
    return isinstance(object_id_or_str, ObjectId) \
           or (isinstance(object_id_or_str, basestring) and object_id_pttrn.match(object_id_or_str) is not None)


class Docs(object):
    db = _db()
    installed = {}              # index for map collection name against doc_class.
    installed_doc_no_map = {}   # index for map doc_no prefix against doc_class.
    _on_delete = {}

    def __init__(self, collection_name):
        super(Docs, self).__init__()
        db_name, sub_name = collection_name.split(":", 1) if ":" in collection_name else (collection_name, None)
        self.collection_name = collection_name
        self.sub_collection_name = sub_name
        self.db_name = db_name
        if db_name is None:
            raise ProhibitedError("Unable to create empty database name document manager")
        self.o = self.db["intradoc_%s" % db_name]

    def single(self, object_id):
        """
        For internal use

        :param object_id:
        :return:
        """
        return self.o.find_one(_objectid(object_id))

    def project(self, cond={}, project=None, sort=None, **kwargs):
        """
        A simple search interface return only necessary fields, leave small footprint.

        :param cond:
        :param project:
        :param kwargs:
        :return: pymongo.Cursor
        """
        page_size = kwargs.pop('page_size', 0)
        page = kwargs.pop('page', 0)
        # inject subtype queries to honor class's manager settings
        if self.sub_collection_name is not None and '_subtype' not in cond:
            cond['_subtype'] = { '$regex': '^%s' % self.sub_collection_name }
        # @see http://api.mongodb.com/python/2.8/api/pymongo/collection.html#pymongo.collection.Collection.find
        return self.o.find(cond, project, page_size*page, page_size, sort=sort)

    def aggregate(self, pipeline, **kwargs):
        # inject subtype queries to honor class's manager settings
        if self.sub_collection_name is not None:
            pipeline = [{'$match': {'_subtype': {'$regex': '^%s' % self.sub_collection_name}}}] + pipeline
        # @see http://api.mongodb.com/python/2.8/api/pymongo/collection.html#pymongo.collection.Collection.aggregate
        return self.o.aggregate(pipeline, **kwargs)

    def group(self, key, condition, initial, reduce, finalize=None, **kwargs):
        # inject subtype queries to honor class's manager settings
        if self.sub_collection_name is not None and '_subtype' not in condition:
            condition['_subtype'] = { '$regex': '^%s' % self.sub_collection_name }
        # @see http://api.mongodb.com/python/2.8/api/pymongo/collection.html#pymongo.collection.Collection.group
        return self.o.group(key, condition, initial, reduce, finalize, **kwargs)

    def write(self, document, **kwargs):
        document['_id'] = kwargs.get('object_id', document['_id'] or None)
        if document['_id'] is None:
            document.pop("_id", None)
        if self.sub_collection_name is not None:
            document['_subtype'] = self.sub_collection_name
        return self.o.save(document)

    def delete(self, cond={}, verbose=False):
        on_delete = self._on_delete[self.db_name] if self.db_name in self._on_delete else []
        if verbose:
            if callable(verbose):
                verbose('Deleting "%s": %s' % (self.db_name, cond))
            else:
                LOG.info('Deleting "%s": %s' % (self.db_name, cond))
        if len(on_delete) > 0:
            # Calculate ids
            ids = self.o.find(cond).distinct('_id')
            map(lambda de: de(ids, verbose), on_delete)
        r = self.o.remove(cond)
        return r['n'] if r['ok'] else 0

    def update(self, user, cond=[]):
        bulk = self.o.initialize_unordered_bulk_op()
        for c in cond:
            event_id = c.pop('event', None)
            if event_id:
                e = Event.create(Event.UPDATED, user, against=event_id)
                c['content'].update({'last_edited': e.object_id})
                bulk.find(c['cond']).update({'$set': c['content']})
            else:
                bulk.find(c['cond']).update({'$set': c['content']})

        try:
            result = bulk.execute()
        except BulkWriteError as bwe:
            result = bwe.details
        return result

    def of(self, field, value):
        """

        :param field:
        :param value:
        :return [Doc]: single document of specific class or None if such field/value does not exists
        """
        r = self.find(cond={
            field: value
        }, pagesize=1)
        return None if len(r) == 0 else r[0]


    def find(self, pagesize=0, page=0, cond=None, **kwargs):
        """

        :param pagesize:
        :param page:
        :param cond:
        :param kwargs:
        :return [Doc]:
        """
        if cond is None:
            cond = {}
        cond.update(kwargs)
        sort = cond.pop('$sort', '_id')
        # IF you are subclass's manager - then you need to queries only subclass items.
        if self.sub_collection_name is not None:
            cond['_subtype'] = { '$regex': '^%s' % self.sub_collection_name }
        cursor = self.o.find(cond)

        # sorting (optional)
        if sort is not None:
            m = re.match('(-?)(.*)', sort)
            if m:
                cursor.sort(m.group(2), pymongo.DESCENDING if m.group(1) == '-' else pymongo.ASCENDING )

        # pagination
        if pagesize > 0:
            cursor.skip(pagesize*page)
            cursor.limit(pagesize)

        # Export result
        def inflater(doc):
            doc_key = self.collection_name
            if '_subtype' in doc:
                subtype = doc.pop('_subtype')
                doc_key = "%s:%s" % (self.db_name, subtype)
            if doc_key not in Docs.installed:
                raise ProhibitedError("Unknown document type:%s" % doc_key)
            o = Docs.installed[doc_key]()
            o.inflate(doc)
            return o
        return map(inflater, cursor)

    def count(self, cond={}, **kwargs):
        cond.update(kwargs)
        return self.o.find(cond, []).count()

    def _create_index(self, key, options):
        index_name = self.o.create_index(key, **options)
        LOG.info("\t=> Created index %s %s = %s" % (key, options, index_name))
        return index_name

    def _add_delete_trigger(self, trigger_source_db_name, reference_field):
        if trigger_source_db_name not in self._on_delete:
            self._on_delete[trigger_source_db_name] = []
        self._on_delete[trigger_source_db_name].append(lambda ids, v: self.delete({reference_field: {'$in': ids}}, v))
        LOG.info("\t=> Created delete trigger: '%s' will chain delete collection='%s', field='%s'" % (trigger_source_db_name, self.db_name, reference_field))

    @classmethod
    def register(cls, doc_class, indices=[], references=[], doc_no_prefix=None):
        """

        :param doc_class: registry document class
        :param indices: list of required index to be added to mongo
        :param references: list of foreign key tuple of ... (collection_name, class_field_name).
        :param doc_no_prefix: prefix of document number
        :return:
        """

        # if sub_name exists Let's validate if the class is an extension of its parent
        if doc_class.manager.sub_collection_name is not None and not issubclass(doc_class, Docs.installed[doc_class.manager.db_name]):
            raise ProhibitedError("Extension of collection must be extension of same class hierarchy.")

        if doc_no_prefix:
            if doc_no_prefix in Docs.installed_doc_no_map:
                raise ProhibitedError("doc_no_prefix already exists.")
            Docs.installed_doc_no_map[doc_no_prefix] = doc_class

        Docs.installed[doc_class.manager.collection_name] = doc_class
        # Call create_index
        map(lambda (k, o): doc_class.manager._create_index(k, o), indices)
        map(lambda (c, f): doc_class.manager._add_delete_trigger(c, f), references)

    @classmethod
    def of_doc_no(cls, doc_no):
        """
        Automated retrival of documents

        :param doc_no:
        :return Doc:
        """
        doc_keys = filter(lambda a: re.compile('^%s' % a).match(doc_no) is not None, Docs.installed_doc_no_map.keys())
        for key in doc_keys:
            doc_class = Docs.installed_doc_no_map[key]
            a = doc_class.of('doc_no', doc_no)
            if a is not None:
                return a
        if len(doc_keys) == 0:
            raise BadParameterError(_("ERR_SUPPORTED_DOCUMENT_PREFIX: %(doc_no)s") % {
                'doc_no': doc_no
            })
        raise ResourceNotFoundError(_("ERR_INVALID_DOCUMENT_NUMBER: %(doc_no)s") % {
            'doc_no': doc_no
        })


    @classmethod
    def factory(cls, collection_name, object_id=None):
        if object_id is None:
            return Docs.installed[collection_name]()
        man = cls.installed[collection_name].manager
        raw = man.single(object_id)
        doc_key = man.db_name
        if '_subtype' in raw:
            subtype = raw.pop('_subtype')
            doc_key = "%s:%s" % (man.db_name, subtype)
        if doc_key not in Docs.installed:
            raise ProhibitedError("Unknown document type:%s" % doc_key)
        o = cls.installed[doc_key]()
        o.inflate(raw)
        return o

    @classmethod
    def factory_doc(cls, collection_name):
        if collection_name in cls.installed:
            return cls.installed[collection_name]
        raise ProhibitedError('Unknown collection_name %s' % collection_name)


# Exception
class FieldInvalidateError(Exception):

    def __init__(self, value, message, name="No name"):
        super(FieldInvalidateError, self).__init__('Field "%s" value="%s" type="%s" message="%s"' %
                                                   (name, value, re.sub("(<type\s'|'>$)", "", str(type(value))), message))


# FieldSpec
class FieldSpec(object):

    def __init__(self, classes, **kwargs):
        super(FieldSpec, self).__init__()
        if isinstance(classes, tuple):
            self.classes = classes
        else:
            self.classes = (classes,)
        self.transient = kwargs.get('transient', False)   # if set, it is Subclass responsibility to handle data injection through populate method.
        self.validators = kwargs.get('validators', [])
        self.default = kwargs.get('default', None)
        self.choices = kwargs.get('choices', {})
        self.lov = kwargs.get('lov', None)
        self.max_length = kwargs.get('max_length', 0)
        self.fixed_length = kwargs.get('fixed_length', None)
        self.none = kwargs.get('none', True)
        self.key = kwargs.get('key', None)
        self.omit_if_none = kwargs.get('omit_if_none', False)       # If value is none, act as transient

        # Make sure self.choices is dictionary
        self.choices = dict(self.choices)

        self.builtin_validators = []

        # Create built-in validators
        if not self.none:
            self.add_named_validator(lambda v: v is None, "Cannot assign None to Non-none field.")
        if len(self.classes) > 0:
            self.add_named_validator(lambda v: not isinstance(v, self.classes), "Invalid class expected %s" % (self.classes, ))
        if self.choices is not None and len(self.choices) > 0:
            self.add_named_validator(lambda v: v not in self.choices, "Value is not within choices.")
        if self.lov is not None:
            self.add_named_validator(lambda v: LOV.objects.filter(group=self.lov, code=v).count() > 0, "Value is not within LOV choices.")
        if self.max_length > 0:
            self.add_named_validator(lambda v: len(v) > self.max_length, "Value is not be longer than %s." % self.max_length)
        if self.fixed_length is not None:
            self.add_named_validator(lambda v: len(v) == self.fixed_length, "Value must be %s long." % self.fixed_length)

        def validate_and_raise(lambda_callback, throw):
            def wrapped(v, n):
                if lambda_callback(v):
                    raise FieldInvalidateError(v, throw, n)
            return wrapped

        for i, v in enumerate(self.validators):
            if isinstance(v, tuple) and callable(v[0]) and isinstance(v[1], basestring):
                self.validators[i] = validate_and_raise(v[0], v[1])

        self.field_name = None

    def assign_field_name(self, field_name):
        self.field_name = field_name

    def __get__(self, instance, owner):
        # Access via class method
        if instance is None:
            return self
        v = instance.dox.get(self.field_name, None)
        if v is None and self.default is not None:
            v = instance.dox[self.field_name] = copy.deepcopy(self.default)
        return v

    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError("Cannot assign attribute!")
        value = self.from_python(value)
        self.validate(value, self.field_name)
        instance.dox[self.field_name] = value

    def add_named_validator(self, callback, message):
        def callme(value, name):
            if callback(value):
                raise FieldInvalidateError(value, message, name)
        self.builtin_validators.append(callme)

    def validate(self, value, name):
        if self.none and value is None:
            return
        map(lambda v: v(value, name), self.builtin_validators + self.validators)

    def to_serialized(self, value):
        return value

    def from_serialized(self, value):
        return value

    def to_document(self, value):
        return value

    def from_document(self, value):
        return value

    def from_python(self, value):
        return value

    def populate(self, value, next_path):
        """
        Normally you don't need to override this method.
        This method act as a manipulation of the values for nested Doc only.
        / As nested doc may easily caused a 'Circular reference problem'. So we need
        user to explicitly called for population of such field.
        :param next_path:
        :return: void
        """
        return value

    def is_required(self):
        return not self.none


class FieldObjectId(FieldSpec):

    def __init__(self, **kwargs):
        super(FieldObjectId, self).__init__(ObjectId, **kwargs)

    def from_serialized(self, value):
        return value and ObjectId(value)

    def to_serialized(self, value):
        return value and str(value)

    @staticmethod
    def new_id():
        return ObjectId()


class FieldSpecDjangoModel(FieldSpec):
    """
    FieldSpec - Using Django Model

    This field will always populate itself, see from_document, to_document
    """
    def __init__(self, clz, **kwargs):
        assert not isinstance(clz, (tuple, list)) and issubclass(clz, DjangoModel)
        self.django_model = clz
        self.serialized_fields = kwargs.get('serialized_fields', None)
        self.lazy_delete = kwargs.get('lazy_delete', True)            # Automatically disregard value if it is invalid
        super(FieldSpecDjangoModel, self).__init__(clz, **kwargs)

    def from_document(self, value):
        try:
            o = value and self.django_model.objects.get(pk=value)
            return o
        except ObjectDoesNotExist as e:
            # Object no longer exists
            if self.lazy_delete:
                return None     # disregard it
            return value

    def to_document(self, value):
        if value and isinstance(value, self.django_model):
            return ObjectId(value.pk)
        return value

    def from_serialized(self, value):
        out = self.from_document(value)
        return out

    def to_serialized(self, value):
        if not value and self.lazy_delete:
            return None
        elif isinstance(value, ObjectId):
            return str(value)
        return model_to_dict(value, self.serialized_fields)

    def populate(self, value, next_path):
        if not isinstance(value, self.django_model):
            return self.from_document(value)
        return value


class FieldIntraUser(FieldSpecDjangoModel):

    def __init__(self, **kwargs):
        kwargs.update({
            'serialized_fields': ('id', 'code', 'first_name', 'last_name')
        })
        super(FieldIntraUser, self).__init__(IntraUser, **kwargs)


class FieldAssignee(FieldSpec):
    """
    Special case - FieldAssignee accepts both, IntraUser and group identification (String)
    """
    def __init__(self, **kwargs):
        self.django_model = IntraUser
        super(FieldAssignee, self).__init__((basestring, IntraUser, task.TaskGroup), **kwargs)

    def from_document(self, value):
        return self.from_python(value)

    def from_python(self, value):
        if value:
            if isinstance(value, (IntraUser, task.TaskGroup)):
                return value
            elif _is_objectid(value):
                return self.django_model.objects.get(pk=value)
            elif isinstance(value, (basestring, int)):
                if len(str(value)) == 3:
                    return task.TaskGroup.factory(value)
                else:
                    return IntraUser.objects.get(code=value)
        return None

    def to_document(self, value):
        if isinstance(value, IntraUser):
            return ObjectId(value.pk)
        elif isinstance(value, task.TaskGroup):
            return value.code
        return value

    def from_serialized(self, value):
        return self.from_document(value)

    def to_serialized(self, value):
        if isinstance(value, IntraUser):
            return str(value.code)
        elif _is_objectid(value):
            return str(IntraUser.objects.get(pk=value).code)
        elif isinstance(value, task.TaskGroup):
            return str(value.code)
        return value

    def populate(self, value, next_path):
        if not isinstance(value, (self.django_model, task.TaskGroup)):
            if _is_objectid(value):
                return self.django_model.objects.get(pk=value)
            else:
                return task.TaskGroup.factory(value)
        return value


class FieldUserFile(FieldSpecDjangoModel):

    def __init__(self, **kwargs):
        self.store_id = kwargs.get('store_id', False)
        if self.store_id:
            kwargs.update({
                'serialized_fields': ('id',)
            })
        else:
            kwargs.update({
                'serialized_fields': ('domain', 'sub_domain', 'id', 'file', 'author')
            })
        super(FieldUserFile, self).__init__(UserFile, **kwargs)

    def to_serialized(self, value):
        ret = super(FieldUserFile, self).to_serialized(value)
        if ret is None:
            return None
        if not self.store_id:
            ret.update({
                'file': ret['file'].name,
                'doc': value.doc and time.mktime(value.doc.timetuple()) or None,
            })
        else:
            ret = ret and ret['id'] or None
        return ret


class FieldTypedCode(FieldSpec):

    def __init__(self, typed_code_class=TypedCode, **kwargs):
        assert typed_code_class is not None
        assert issubclass(typed_code_class, TypedCode)
        self.typed_code_class = typed_code_class
        self.allow_incomplete = kwargs.get('allow_incomplete', False)
        super(FieldTypedCode, self).__init__(typed_code_class, **kwargs)

    def to_document(self, value):
        return value and str(value)

    def from_document(self, value):
        try:
            return value and TypedCode.translate(value, 'object', self.allow_incomplete) or None
        except ValidationError:
            LOG.warning('Failed to translate field TypeCode: %s' % value)
            return value

    def from_serialized(self, value):
        o = value and TypedCode.translate(value, 'object', self.allow_incomplete) or None
        if o is not None and not isinstance(o, self.typed_code_class):
            raise ValidationError('Invalid code type %s' % value)
        return o

    def from_python(self, value):
        if isinstance(value, basestring):
            value = self.from_serialized(value)
        return value

    def to_serialized(self, value):
        return self.to_document(value)


class FieldTask(FieldSpec):

    def __init__(self, **kwargs):
        super(FieldTask, self).__init__(task.Task)

    def to_document(self, value):
        return value and value.code

    def from_python(self, value):
        if isinstance(value, int):
            return task.Task.factory(value)
        return value

    def from_document(self, value):
        return value and task.Task.factory(value.replace("task-", "") if isinstance(value, basestring) else value)

    def from_serialized(self, value):
        return self.from_document(value)

    def to_serialized(self, value):
        return "task-%s" % value.code if value else None


class FieldUom(FieldSpec):

    def __init__(self, **kwargs):
        super(FieldUom, self).__init__(uoms.UOM)

    def to_document(self, value):
        return value and value.code

    def from_document(self, value):
        return uoms.UOM.factory(value) if value and isinstance(value, basestring) else value

    def to_serialized(self, value):
        return value and str(value)

    def from_serialized(self, value):
        return self.from_document(value)

    def from_python(self, value):
        return self.from_document(value)


class FieldDateTime(FieldSpec):

    def __init__(self, **kwargs):
        super(FieldDateTime, self).__init__(datetime.datetime, **kwargs)

    def from_serialized(self, value):
        return value and datetime.datetime.fromtimestamp(value)

    def to_serialized(self, value):
        return value and time.mktime(value.timetuple())


class FieldBoolean(FieldSpec):

    def __init__(self, **kwargs):
        super(FieldBoolean, self).__init__(bool, **kwargs)

    def from_python(self, value):
        return value and bool(value) or value

    def from_serialized(self, value):
        return value and bool(value) or value


class FieldNumeric(FieldSpec):

    def __init__(self, **kwargs):
        super(FieldNumeric, self).__init__((int, float, long), **kwargs)

    def to_document(self, value):
        if isinstance(value, float):
            return round(value, 2)
        return value


class FieldString(FieldSpec):

    def __init__(self, **kwargs):
        super(FieldString, self).__init__(basestring, **kwargs)

    def from_python(self, value):
        return value and unicode(value) or value

    def from_serialized(self, value):
        return value and unicode(value) or value


class FieldAnyDoc(FieldSpec):

    def __init__(self, **kwargs):
        super(FieldAnyDoc, self).__init__((tuple, list, Doc), **kwargs)

    def to_document(self, value):
        if value and isinstance(value, (tuple, list)):
            return [value[0], value[1]]         # Make sure we have a list placed there.
        if value and isinstance(value, Doc):
            return [value.object_id, value.manager.collection_name]
        return None

    def from_document(self, value):
        # Must supplied as [id, type]
        return value

    def from_serialized(self, value):
        # Must supplied, [id, type]
        if not self.none and value is None:
            raise BadParameterError(_("ERR_CANNOT_DESERIALIZED_NONE_VALUE_FOR_NON_NULLABLE_FIELD"))

        # IF there is coming value then use it.
        if value is not None:
            assert isinstance(value, (tuple, list)) and len(value) == 2 and isinstance(value[1], basestring)
            value[0] = _objectid(value[0])
        return value

    def to_serialized(self, value):
        if value and isinstance(value, Doc):
            return value.serialized()
        return value

    def populate(self, value, next_path):
        r = value
        if isinstance(value, (tuple, list)):
            r = Docs.factory(value[1], value[0])
        if next_path:
            assert isinstance(r, Doc)
            r.populate(next_path)
        return r

    @staticmethod
    def as_value_for_query(any_doc_valid_value):
        """
        Handling data type "any_doc"

        :param any_doc_valid_value:
        :return:
        """
        if isinstance(any_doc_valid_value, (tuple, list)) and len(any_doc_valid_value) == 2 \
                and isinstance(any_doc_valid_value[0], ObjectId):
            # assume you are a valid any_doc value
            return any_doc_valid_value[0], any_doc_valid_value[1]
        if isinstance(any_doc_valid_value, Doc):
            return any_doc_valid_value.object_id, any_doc_valid_value.manager.collection_name
        raise BadParameterError(_("ERR_UNABLE_TO_INTERPRET_SUCH_VALUE_AS_ANY_DOC: %(value)s") % {
            'value': any_doc_valid_value
        })


class FieldDoc(FieldSpec):

    def __init__(self, doc_class_or_collection_name, **kwargs):
        if isinstance(doc_class_or_collection_name, tuple):
            raise ValueError('FieldDoc only accept single document type')
        self.doc_class_or_collection_name = doc_class_or_collection_name
        self.doc_class = None
        super(FieldDoc, self).__init__((ObjectId, Doc), **kwargs)

    def to_document(self, value):
        if value and isinstance(value, self.doc_clz()):
            return value.object_id
        elif value and isinstance(value, ObjectId):
            return value
        return None

    def from_document(self, oid):
        return oid

    def from_serialized(self, oid):
        if isinstance(oid, dict):
            clz = self.doc_clz()
            inst = clz()
            if '_id' in oid:
                inst.object_id = ObjectId(oid.pop('_id'))
            inst.deserialized(oid)
            return inst
        return oid and ObjectId(oid)

    def to_serialized(self, value):
        if value and isinstance(value, self.doc_clz()):
            return value.serialized()
        elif value and isinstance(value, ObjectId):
            return value
        return None

    def populate(self, value, next_path):
        r = value
        if r is None:
            return r

        # populate self first.
        if isinstance(value, ObjectId):
            r = Docs.factory(self.doc_clz().manager.collection_name, value)

        # try to populate next_path
        if next_path:
            assert isinstance(r, self.doc_clz())
            r.populate(next_path)
        return r

    def from_python(self, value):
        # Case given from AnyDoc
        if isinstance(value, (tuple, list)) and len(value) == 2 and isinstance(value[1], basestring):
            # Verify if value[1] is correct collection_name
            supplied_class = self.collection_to_class(value[1])
            required_class = self.doc_clz()

            if not issubclass(supplied_class, required_class):
                raise ValueError('FieldDoc accept only %s' % required_class)
            return value[1]
        return value

    def doc_clz(self):
        """
        sanitize self.doc_class to be Document class object. (if it was given as string)
        :return: document class object,
        """
        if self.doc_class is None:
            self.doc_class = self.collection_to_class(self.doc_class_or_collection_name)
        return self.doc_class

    @classmethod
    def collection_to_class(cls, doc_class_or_collection_name):
        if isinstance(doc_class_or_collection_name, basestring):
            # resolve it to class instead
            doc_class = Docs.installed[doc_class_or_collection_name]
            if doc_class is None:
                raise ValueError('Unknown doc_class %s' % doc_class_or_collection_name)
        else:
            doc_class = doc_class_or_collection_name
        if not issubclass(doc_class, Doc):
            raise ValueError('Expected doc_class to be subclass of Doc')
        return doc_class



class FieldTuple(FieldSpec):

    def __init__(self, *args, **kwargs):
        for a in args:
            if not isinstance(a, FieldSpec):
                raise ValueError('element_fieldspec must be FieldSpec instance')
        kwargs.update({
            'validators': [
                self._validate_element
            ] + kwargs.get('validators', [])
        })
        self.element_fieldspecs = args
        super(FieldTuple, self).__init__((tuple, list), **kwargs)

    def to_document(self, value):
        if value is None:
            return []
        return map(lambda v: self.element_fieldspecs[v[0]].to_document(v[1]), enumerate(value))

    def from_document(self, value):
        if value is None:
            return ()
        if not isinstance(value, list):
            raise ValidationError('value %s is not list' % value)
        return tuple(map(lambda v: self.element_fieldspecs[v[0]].from_document(v[1]), enumerate(value)))

    def from_serialized(self, value):
        if value is None:
            return ()
        v = map(lambda v: self.element_fieldspecs[v[0]].from_serialized(v[1]), enumerate(value))
        return v

    def to_serialized(self, value):
        if value is None:
            return []
        v = map(lambda v: self.element_fieldspecs[v[0]].to_serialized(v[1]), enumerate(value))
        return v

    def _validate_element(self, value, name):
        if len(value) != len(self.element_fieldspecs):
            raise ValidationError('FieldSpecTuple expected equal tuple size')

        if value is None:
            return []
        # incoming value is sure be tuple or list, so we need to iterate that
        map(lambda v: self.element_fieldspecs[v[0]].validate(v[1], name), enumerate(value))


class FieldList(FieldSpec):

    def __init__(self, element_fieldspec, **kwargs):
        if not isinstance(element_fieldspec, FieldSpec):
            raise ValueError('element_fieldspec must be FieldSpec instance')
        validators = {
            'default': [],
            'validators': [
                self._validate_element
            ] + kwargs.get('validators', [])
        }
        kwargs.update(validators)
        self.element_fieldspecs = element_fieldspec
        self.remove_none_values = kwargs.pop('remove_none_values', False)
        super(FieldList, self).__init__((tuple, list), **kwargs)

    def to_document(self, value):
        if value is None:
            return []
        return map(lambda v: self.element_fieldspecs.to_document(v), value)

    def from_document(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValidationError('value %s is not list' % value)
        return map(lambda v: self.element_fieldspecs.from_document(v), value)

    def from_serialized(self, value):
        if value is None:
            return []
        v = map(lambda v: self.element_fieldspecs.from_serialized(v), value)
        if self.remove_none_values:
            v = filter(lambda v: v is not None, v)
        return v

    def to_serialized(self, value):
        if value is None:
            return []
        v = map(lambda v: self.element_fieldspecs.to_serialized(v), value)
        if self.remove_none_values:
            v = filter(lambda v: v is not None, v)
        return v

    def _validate_element(self, value, name):
        # incoming value is sure be tuple or list, so we need to iterate that
        map(lambda v: self.element_fieldspecs.validate(v, name), value)

    def populate(self, value, next_path):
        value = map(lambda v: self.element_fieldspecs.populate(v, next_path), value)
        value = filter(lambda v: v is not None, value)
        return value


class FieldNested(FieldSpec):

    def __init__(self, field_spec_aware_class, **kwargs):
        assert field_spec_aware_class is not None
        assert issubclass(field_spec_aware_class, _FieldSpecAware)
        self.field_spec_aware_class = field_spec_aware_class
        super(FieldNested, self).__init__(FieldSpecAware, **kwargs)

    def from_document(self, raw_document):
        spec_aware = self.field_spec_aware_class()
        spec_aware.inflate(raw_document)
        return spec_aware

    def to_document(self, value):
        if value is not None:
            assert isinstance(value, self.field_spec_aware_class), "Value must be %s got %s" % (self.field_spec_aware_class, value)
            return value.document()
        else:
            spec_aware = self.field_spec_aware_class()
            return spec_aware.document()

    def from_serialized(self, nested_dict):
        spec_aware = self.field_spec_aware_class()
        spec_aware.deserialized(nested_dict)
        return spec_aware

    def to_serialized(self, value):
        if value is not None:
            assert isinstance(value, self.field_spec_aware_class), "Value must be %s got %s" % (self.field_spec_aware_class, value)
            return value.serialized()
        else:
            spec_aware = self.field_spec_aware_class()
            return spec_aware.serialized()

    def populate(self, value, next_path):
        if value is not None:
            assert isinstance(value, self.field_spec_aware_class), "Value must be %s got %s" % (self.field_spec_aware_class, value)
            return value.populate(next_path)
        else:
            spec_aware = self.field_spec_aware_class()
            return spec_aware.populate(next_path)


# Using FieldSpec
def _fieldspecs(clazz):
    def is_field_spec(clz):
        o = {key: fs for key, fs in clz.__dict__.iteritems() if isinstance(fs, FieldSpec)}
        ProhibitedError.raise_if('_id' in o, "_id is reserved keyword")
        ProhibitedError.raise_if('_subtype' in o, "_subtype is reserved keyword")
        return o

    mro = inspect.getmro(clazz)
    fields = reduce(lambda x, y: dict(x.items() + is_field_spec(y).items()), reversed(mro), {})
    doc_key_map = dict(map(lambda (x, f): (f.key or x, x), fields.iteritems()))
    return fields, doc_key_map


class _FieldSpecAware(object):

    def __init__(self):
        super(_FieldSpecAware, self).__init__()
        self.__dict__['fields'], self.__dict__['doc_key_map'] = _fieldspecs(self.__class__)
        for key in self.__dict__['fields']:
            f = self.__dict__['fields'][key]
            if isinstance(f, FieldSpec):
                f.assign_field_name(key)
        self.dox = {}

    def is_fieldspec(self, item):
        return item in self.fields

    def fieldspec(self, item):
        if self.is_fieldspec(item):
            return self.fields[item]
        else:
            return None

    def populate(self, path):
        (cp, sp, next_path) = path.partition('.')
        if cp in self.fields:
            fs = self.fields[cp]
            try:
                self.dox[cp] = fs.populate(self.dox.get(cp, fs.default), next_path)
            except Exception as e:
                LOG.error("Populate field '%s' failed: %s" % (path, e))
        return self

    def validate(self):
        map(lambda (k, fs): fs.validate(self.dox.get(k, fs.default), k), self.fields.iteritems())

    def document(self):
        """
        Reverse of inflate
        :return:
        """
        write_fields = filter(lambda (k, f): False == f.transient, self.fields.iteritems())
        def proc(key, f):
            value = f.to_document(self.dox.get(key, f.default))
            if value is None and f.omit_if_none:
                return "omitted", value
            return f.key or key, value
        o = dict(map(lambda (k, f): proc(k, f), write_fields))
        if "omitted" in o:
            del o["omitted"]
        return o

    def inflate(self, raw_document):
        """
        Reverse of document()

        :param document: nested dictionary from database
        :return Doc:
        """
        if raw_document is not None and isinstance(raw_document, dict):
            def bypass(document_key, value, error_policy='print'):
                """
                Assign value directly to dox dict, skip validation process
                :param key:
                :param value:
                :return:
                """
                # Skip reserved keywords
                if document_key in ['_subtype']:
                    return
                if document_key not in self.doc_key_map:
                    if error_policy == 'raise':
                        raise ValueError('%s is not FieldSpec' % document_key)
                    else:
                        LOG.warning("\tField => '%s' ignored, unmatched field in model %s" % (document_key, self.__class__))
                        return
                key = self.doc_key_map[document_key]
                fs = self.fieldspec(key)
                if fs is not None:
                    # Only save value to dox, if value is not None
                    if value is not None:
                        self.dox[key] = fs.from_document(value)
                        return

            map(lambda (k, v): bypass(k, v), raw_document.iteritems())

    def serialized(self):
        return dict(map(lambda (k, f): (f.key or k, f.to_serialized(self.dox.get(k, f.default))), self.fields.iteritems()))

    def deserialized(self, serialized):
        """
        Reverse of document()
        :param serialized: nested dictionary from database
        :return:
        """
        if serialized is not None and isinstance(serialized, dict):
            def deserialized(document_key, value):
                key = self.doc_key_map[document_key]
                fs = self.fieldspec(key)
                if fs is not None:
                    if value is None and fs.is_required() and fs.default is None:
                        raise ValueError("Key %s is supplied, and is required field, but value is none" % document_key)
                    self.__setattr__(key, fs.from_serialized(value or fs.default))
                else:
                    LOG.waning("Field %s is not a FieldSpec, ignored by deserialized" % key)
            map(lambda (k, v): deserialized(k, v), serialized.iteritems())


class _FieldSpecAwareMetaClass(type):
    def __new__(cls, clsname, bases, dct):
        meta = 'Meta' in dct and dct['Meta'].__dict__ or {}
        # register myself to Doc repository
        if 'collection_name' in meta:
            collection_name = meta['collection_name']

            if re.compile('^:').match(collection_name):
                # find "first" parent class with manager
                parent_collection_name = next((x.manager.collection_name for x in bases if hasattr(x, 'manager')), None)
                if parent_collection_name is None:
                    raise ProhibitedError("Unable to extend empty non-discoverable parent class")
                collection_name = "%s%s" % (parent_collection_name, collection_name)

            dct['manager'] = Docs(collection_name)
            clx = super(_FieldSpecAwareMetaClass, cls).__new__(cls, clsname, bases, dct)
            # Register Foreign key and index
            # > http://api.mongodb.org/python/current/api/pymongo/collection.html#pymongo.collection.Collection.create_index
            Docs.register(clx,
                          meta['indices'] if 'indices' in meta else [],
                          meta['references'] if 'references' in meta else [],
                          meta['doc_no_prefix'] if 'doc_no_prefix' in meta else None
                          )
            # Permission registration
            default = meta.pop("require_permission", False)
            define_permission(collection_name,
                              read=meta.pop('permission_read', default),
                              write=meta.pop('permission_write', default),
                              delete=meta.pop('permission_delete', default))

            LOG.info('FieldSpecAware "%s" is created and discoverable via "%s"' % (clsname, collection_name))
        else:
            clx = super(_FieldSpecAwareMetaClass, cls).__new__(cls, clsname, bases, dct)
            LOG.info('FieldSpecAware "%s" is created.' % clsname)
        return clx


# Public class
class FieldSpecAware(six.with_metaclass(_FieldSpecAwareMetaClass, _FieldSpecAware)):
    pass


class Doc(FieldSpecAware):
    PERM_W = 'write'
    PERM_R = 'read'
    PERM_D = 'delete'
    object_id = FieldObjectId(key="_id")
    manager = None
    """:type : Docs"""

    def __init__(self, object_id=None):
        super(Doc, self).__init__()
        self.object_id = _objectid(object_id)
        self._injected_object_id = None
        self.load()

    @classmethod
    def ACTION(cls, operation):
        """

        :param basestring operation:
        :return:
        """
        return "%s+%s" % (cls.manager.collection_name, operation)

    @classmethod
    def ACTION_WRITE(cls):
        return cls.ACTION(cls.PERM_W)

    @classmethod
    def ACTION_READ(cls):
        return cls.ACTION(cls.PERM_R)

    @classmethod
    def ACTION_DELETE(cls):
        return cls.ACTION(cls.PERM_D)

    @classmethod
    def of(cls, field, value):
        """
        Factory the first document of repective class that matched given field and value key pair.

        :param basestring field:
        :param value:
        :return: None if material does not exists
        """
        return cls.manager.of(field, value)

    def load(self):
        if self.object_id is not None:
            raw = self.manager.single(self.object_id)
            if not raw:
                raise ValueError('Unknown document_id=%s' % self.object_id)
            self.inflate(raw)
        else:
            self._injected_object_id = ObjectId()
            self.object_id = self._injected_object_id

    def is_new(self):
        return self._injected_object_id is not None and self.object_id == self._injected_object_id

    def save(self):
        self.validate()
        self.object_id = self.manager.write(self.document())
        self._injected_object_id = None     # ObjectId has been commited.
        return self.object_id

    def delete(self):
        """
        Delete document by its own main_id

        :return:
        """
        self.manager.delete({
            '_id': self.object_id
        })

    def invoke(self, user, requested_operation):
        """
        Custom model operation exeuction, allow remote execution.

        :param requested_operation: (String)
        :return: self, facilitate pipeline operations
        """
        method, parameter = requested_operation.split(" ", 1)
        self.__class__.__dict__['invoke_%s' % method](self, user, parameter)
        return self

    def assert_permission(self, user, action, *args):
        if self.manager.collection_name is None:
            raise BadParameterError(_("Unable to check permission against non-modeled document"))
        user.can("%s+%s" % (self.manager.collection_name, action), args[0] if len(args) > 0 else None, True)


class RunningNumberPolicy(object):

    def next(self, rnc):
        r = rnc.next_value
        rnc.next_value = rnc.next_value + 1
        rnc.save()
        return r


class MonthlyRunningNumberPolicy(RunningNumberPolicy):

    prefix = None

    def __init__(self, prefix=None, digits=4):
        self.prefix = prefix
        self.digits = digits

    def next(self, rnc):
        today_threshold = int('{:%y%m}'.format(datetime.datetime.today())) * int(math.pow(10, self.digits))
        if rnc.next_value < today_threshold:
            rnc.next_value = today_threshold

        new_number = str(super(MonthlyRunningNumberPolicy, self).next(rnc))
        return self.prefix + new_number if self.prefix else new_number


class DailyRunningNumberPolicy(RunningNumberPolicy):

    def __init__(self, prefix=None, digits=4):
        self.prefix = prefix
        self.digits = digits

    def next(self, rnc):
        prefixed_date = int('{:%y%m%d}'.format(datetime.datetime.today()))
        today_threshold = prefixed_date * int(math.pow(10, self.digits))
        if rnc.next_value < today_threshold:
            rnc.next_value = today_threshold

        new_number = str(super(DailyRunningNumberPolicy, self).next(rnc))
        return self.prefix + new_number if self.prefix else new_number


class RunningNumberCenter(Doc):
    """
    Policy, such batch number will be created, and assumed that the number
    will be successfully consumed by next process.
    :return: new batch number obeys format: YYMMDD##### or YYMM####
    """
    policies = {}
    name = FieldString(none=False)
    next_value = FieldNumeric(default=1)

    def __init__(self, object_id=None):
        super(RunningNumberCenter, self).__init__(object_id)

    @staticmethod
    def new_number(key):
        if key not in RunningNumberCenter.policies:
            raise BadParameterError("%s key is not recognized in RunningNumberPolicy" % key)

        policy = RunningNumberCenter.policies[key]
        pair = RunningNumberCenter.manager.find(cond={'name': key})
        if len(pair) == 0:
            o = RunningNumberCenter()
            o.name = key
            o.save()
            pair.append(o)

        # proceed to next number
        return policy.next(pair[0])

    @staticmethod
    def register_policy(key, policy):
        RunningNumberCenter.policies[key] = policy

    class Meta:
        collection_name = 'number-center'


class Event(Doc):
    CREATED = 'N'
    UPDATED = 'U'
    DELETED = 'D'
    SUBMIT_FOR_APPROVAL = 'S'
    REJECTED = 'R'
    APPROVED = 'A'
    CANCELLED = 'C'
    UNDEFINED = '?'
    FINISHED = 'F'
    WHAT = (
        (UNDEFINED, _("EVENT_TYPE_UNDEFINED")),
        (CREATED, _("EVENT_TYPE_CREATED")),
        (UPDATED, _("EVENT_TYPE_UPDATED")),
        (DELETED, _("EVENT_TYPE_DELETED")),
        (SUBMIT_FOR_APPROVAL, _("EVENT_SUBMIT_FOR_APPROVAL")),
        (REJECTED, _("EVENT_TYPE_REJECTED")),
        (APPROVED, _("EVENT_TYPE_APPROVED")),
        (CANCELLED, _("EVENT_TYPE_CANCELLED")),
        (FINISHED, _("EVENT_TYPE_FINISHED")),
    )

    who = FieldIntraUser(none=False)
    what = FieldString(choices=WHAT, default=UNDEFINED)
    detail = FieldSpec(dict, none=True)
    when = FieldDateTime()
    against = FieldAnyDoc()

    def __init__(self, object_id=None):
        super(Event, self).__init__(object_id)

    @staticmethod
    def create(what, who, **kwargs):
        e = Event(None)
        e.what = what
        e.who = who
        e.when = kwargs.pop('when', NOW())
        e.against = kwargs.pop('against', None)
        e.detail = Event.sanitize(kwargs.pop('detail', None))
        e.save()
        return e

    @staticmethod
    def sanitize(generic_dict):
        """
        Manipulate generic_dict into message, and string

        :param dict generic_dict:
        :return:
        """
        if generic_dict is None:
            return None
        return generic_dict

    class Meta:
        collection_name = 'event'


class Authored(Doc):
    created_by = FieldIntraUser(none=False)
    edited_by = FieldIntraUser()
    last_edited = FieldDoc(Event)

    def touched(self, user, **kwargs):
        """

        :param IntraUser user:
        :param kwargs:
        :return:
        """
        is_new = False
        if self.is_new():
            is_new = True
            self.created_by = user
            e = Event.create(Event.CREATED, user, against=self)
        else:
            e = Event.create(Event.UPDATED, user, against=self, detail={'message': kwargs.pop("message", None)})
        if self.created_by is None:
            # created_by is missing due to user is deleted or invalid.
            self.created_by = e.who
        self.last_edited = e
        self.edited_by = e.who
        self.save()
        signals.doc_touched.send(self.__class__, is_new=is_new, instance=self)


class ApprovableDoc(Authored):
    NEW = 'N'
    EDITED = 'E'
    APPROVED = 'A'
    REJECTED = 'R'
    WAITING_FOR_APPROVAL = 'W'
    STATUSES = (
        (NEW, _("APPROVAL_STATUS_NEW")),
        (EDITED, _("APPROVAL_STATUS_EDITED")),
        (APPROVED, _("APPROVAL_STATUS_APPROVED")),
        (REJECTED, _("APPROVAL_STATUS_REJECTED")),
        (WAITING_FOR_APPROVAL, _("APPROVAL_STATUS_WAITING_FOR_APPROVAL"))
    )

    approved_by = FieldIntraUser()
    last_approved = FieldSpec(Event)
    status = FieldString(choices=STATUSES, default=NEW)

    def __init__(self, object_id=None, **kwargs):
        super(ApprovableDoc, self).__init__(object_id)
        self.change_set = None

    def deserialized(self, serialized):
        before = {}
        if not self.is_new():
            before = self.serialized()
        super(ApprovableDoc, self).deserialized(serialized)

        diff = DictDiffer(before, self.serialized())
        self.change_set = diff and diff.elaborate() or {}

    def touched(self, user, **kwargs):
        self.status = kwargs.get('status', self.status)
        if self.is_new():
            self.created_by = user
            e = Event.create(Event.CREATED, user, against=self)
        elif self.status == ApprovableDoc.APPROVED:
            e = Event.create(Event.APPROVED, user, against=self)
        elif self.status == ApprovableDoc.WAITING_FOR_APPROVAL:
            e = Event.create(Event.SUBMIT_FOR_APPROVAL, user, against=self)
        else:
            e = Event.create(Event.UPDATED, user, against=self, detail={'change_set': self.change_set})

        if self.created_by is None:
            # created_by is missing due to user is deleted or invalid.
            self.created_by = e.who
        self.last_edited = e
        self.edited_by = e.who
        self.save()


class Revisioned(Doc):
    rev_unique_id = FieldObjectId()
    rev_id = FieldNumeric(default=1)

    def save(self):
        # Automatically inject the rev_unique_id if data is not yet given
        # make sure we have the rev_unique_id
        if self.rev_unique_id is None:
            self.rev_unique_id = FieldObjectId.new_id()

        # Validate if rev_id + rev_unique_id is already exists
        condition_check = {
            'rev_unique_id': self.rev_unique_id,
            'rev_id': self.rev_id
        }
        if not self.is_new():
            condition_check['_id'] = {'$ne': self.object_id}

        if self.manager.count(condition_check) > 0:
            raise ValueError("Invalid revision identity (%s rev%s)" % (self.rev_unique_id, self.rev_id))
        super(Revisioned, self).save()

    def next_revision_id(self, rev_unique_id):
        r = self.manager.o.find({'rev_unique_id': _objectid(rev_unique_id)}, ['rev_id'], 0, 1).sort('rev_id', pymongo.DESCENDING)
        return r and r[0] and (r[0]['rev_id'] + 1) or 1

    def list_revision_ids(self, rev_unqiue_id):
        r = self.manager.o.find({'rev_unique_id': _objectid(rev_unqiue_id)}, ['rev_id']).sort('rev_id', pymongo.DESCENDING)
        o = dict(map(lambda a: (a['rev_id'], str(a['_id'])), r))
        return o

    def list_latest_revisions(self, pagesize=20, page=0, **kwargs):
        r = self.manager.o.aggregate([{ "$sort": {"last_edited": -1}},
                                      { "$group": { "_id": "$rev_unique_id", "max_rev_id": { "$max": "$rev_id" } }},
                                      { "$skip": page * pagesize },
                                      { "$limit": pagesize }])
        return map(lambda o: self.manager.find(1, 0, {'rev_unique_id': o['_id'], 'rev_id': o['max_rev_id']})[0], r['result'])

    def revisions_count(self):
        return len(self.manager.o.distinct("rev_unique_id"))


class Validatable(Doc):

    def __init__(self, objectid=None):
        super(Validatable, self).__init__(objectid)
        self.validation_errors = []

    def validate_data(self, throw=True, **kwargs):
        self.validation_errors = self.validate_for_errors(**kwargs)
        if throw and any(len(errs) > 0 for errs in self.validation_errors):
            raise ValidationError(self.validation_errors)
        return self

    def validate_for_errors(self, **kwargs):
        return [["Validatable required validate_for_error to be implemented"]]

    def serialized(self):
        o = super(Validatable, self).serialized()
        o["errors"] = self.validation_errors
        return o


class Options(Doc):
    key = FieldString()
    value = FieldSpec(dict)

    @classmethod
    def get(cls, key, default_value=None):
        found = cls.manager.find(pagesize=1, cond={
            'key': key
        })
        if len(found) > 0:
            return found[0].value
        return default_value

    @classmethod
    def set(cls, key, value):
        found = cls.manager.find(pagesize=1, cond={
            'key': key
        })
        if len(found) > 0:
            found[0].value = value
            return found[0].save()
        else:
            o = Options()
            o.key = key
            o.value = value
            return o.save()


    class Meta:
        collection_name = 'options'
        indices = [
            ([('key', 1)] , {'unique': True})
        ]
