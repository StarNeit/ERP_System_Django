__author__ = 'peat'

import time
import re
from errors import ProhibitedError, BadParameterError, ValidationError
from json import JSONDecoder
from codes import SPEC2PROCESS
from service import IdLookupAPI, CRUDApi, DocumentHelperApi, choices as choices_api, TypedCodeAvoidEncoder as Encoder
from forms import GenericFileUploadForm
from decorators import ajaxian as ajax_link
from uoms import UOM
from intramanee.common.calendar.documents import OffHoursRange
from intramanee.randd import documents as randd_doc

from django.http.response import Http404
from django.conf.urls import patterns, url
from bson import ObjectId
from datetime import datetime

lookup = IdLookupAPI()
crud = CRUDApi()

_against_reference_pattern = re.compile(r'(([a-z_-]+)/)?([a-f\d]{24})', re.I)


def _transmute_object_id(d):
    """
    Update all objectId pattern to bson.ObjectId() object
    """
    if isinstance(d, dict):
        return dict(map(lambda (a, b): (a, _transmute_object_id(b)), d.iteritems()))
    elif isinstance(d, list):
        return list(map(lambda b: _transmute_object_id(b), d))
    elif isinstance(d, basestring):
        m = _against_reference_pattern.match(d)
        if m and m.group(2) is not None:
            return [ObjectId(m.group(3)), m.group(2)]
        elif m and m.group(3) is not None:
            return ObjectId(m.group(3))
    return d


@ajax_link
def echo(request, message):
    request.user.can(randd_doc.Design.ACTION_WRITE(), "approve", throw='challenge')
    print message
    return message


@ajax_link
def idLookup(request, source):
    return lookup.lookup(source, request.GET.get('typed'), **JSONDecoder().decode(request.GET.get('args', "{}")))


@ajax_link
def next_token(request):
    return lookup.next_token(request.GET.get('current'), request.GET.get('typed'))


@ajax_link(good_operations="POST")
def add_token(request):
    content = JSONDecoder().decode(request.POST.get('content'))
    return lookup.add_token(request.POST.get('current'), content, request.user)


@ajax_link(good_operations="POST")
def lov(request, group):
    content = JSONDecoder().decode(request.POST.get('content'))
    return lookup.add_lov(group, content, request.user)


@ajax_link
def tokenize(request):
    return lookup.extract(request.GET.get('code'))


@ajax_link(good_operations="POST")
def upload_file(request):
    request.POST['author'] = request.user
    form = GenericFileUploadForm(request.POST, request.FILES)
    if form.is_valid():
        form.save()
        return form.instance and {
            'id': form.instance.id,
            'domain': form.instance.domain,
            'sub_domain': form.instance.sub_domain,
            'author': form.instance.author.id,
            'file': form.instance.file.name,
            'doc': form.instance.doc and time.mktime(form.instance.doc.timetuple()) or ''
        }
    else:
        return form.errors


@ajax_link
def design_rules(request):
    return JSONDecoder().decode(Encoder().encode(SPEC2PROCESS))


@ajax_link
def uoms(request):
    return JSONDecoder().decode(Encoder().encode(UOM.uoms))


@ajax_link(good_operations="GET")
def choices(request):
    types = JSONDecoder().decode(request.GET.get('types', "{}"))
    return JSONDecoder().decode(Encoder().encode(choices_api(types)))


@ajax_link(good_operations="POST")
def translate(request):
    queries = JSONDecoder().decode(request.POST.get('q', "{}"))

    def trans_each(k):
        print("\t  %s: count=%s %s" % (k[0], len(k[1]), k[1]))
        return lookup.translate(k[0], k[1])
    print("\t[AJAX] translate ...")
    return map(trans_each, queries.iteritems())


# CRUD API
@ajax_link(good_operations="POST")
def write(request, model_name):
    content = JSONDecoder().decode(request.POST.get('content'))
    options = JSONDecoder().decode(request.POST.get('options'))
    print("\t[AJAX] write(%s) author=%s, options=%s" % (model_name, request.user, options))
    o = crud.write(request.user, model_name, content, options)
    return str(o.object_id)


@ajax_link(good_operations="POST")
def update(request):
    content = JSONDecoder().decode(request.POST.get('content'))
    print("\t[AJAX] update author=%s" % request.user)
    o = crud.update(request.user, content)
    return str(o)


@ajax_link(good_operations="POST")
def sync(request):
    content = JSONDecoder().decode(request.POST.get('content'))
    print("\t[AJAX] sync author=%s" % request.user)
    o = crud.sync(content)
    return o


@ajax_link(good_operations="GET")
def read_one(request, model_name, pk):
    args = _transmute_object_id(JSONDecoder().decode(request.GET.get('args', "{}")))
    print("\t[AJAX] read_1(%s / %s) author=%s, options=%s" % (model_name, pk, request.user, args))
    o = crud.read_one(request.user, model_name, pk, **args)
    return Http404() if o is None else o


@ajax_link(good_operations="GET")
def read(request, model_name, pagesize=20, page=0):
    args = _transmute_object_id(JSONDecoder().decode(request.GET.get('args', "{}")))
    print("\t[AJAX] read(%s) pagesize=%s, page=%s, by=%s, options=%s" % (model_name, pagesize, page, request.user, args))
    return crud.read(request.user, model_name, int(pagesize), int(page), **args)


@ajax_link(good_operations="GET")
def count(request, model_name):
    return crud.count(request.user, model_name, **JSONDecoder().decode(request.GET.get('args', "{}")))


@ajax_link(good_operations="DELETE")
def delete(request, model_name, pk):
    return crud.delete(request.user, model_name, pk)


# Document Revision API
@ajax_link(good_operations="GET")
def next_revision(request, model_name, rev_unique_id):
    """
    Request for next revision id of specific data_model

    :param request:
    :param model_name:
    :param rev_unique_id:
    :return:
    """
    return DocumentHelperApi.next_revision(model_name, rev_unique_id)


@ajax_link(good_operations="GET")
def list_revision(request, model_name, rev_unique_id):
    return DocumentHelperApi.list_revision(model_name, rev_unique_id)


@ajax_link(good_operations="GET")
def user_can(request, action):
    if request.user is not None:
        request.user.can(action, None, True)
        return "OK"
    raise ProhibitedError('Required valid session!')


@ajax_link
def material_revisions(request, code):
    return DocumentHelperApi.material_revisions(code)


@ajax_link
def offhours_between(request, start_time, end_time):
    start = datetime.fromtimestamp(float(start_time))
    end = datetime.fromtimestamp(float(end_time))

    def convert(o):
        return [time.mktime(o.start.timetuple()), time.mktime(o.end.timetuple())]

    return map(convert, OffHoursRange.between(start, end))


@ajax_link
def newid(request, count):
    return map(lambda o: ObjectId(), range(0, int(count)))


urlpatterns = patterns('',
                       url(r'newid/(?P<count>\d+)$', newid, name="newid"),
                       url(r'material/revisions/(?P<code>.+)$', material_revisions, name="api_material_revisions"),
                       url(r'echo/(?P<message>[^/]+)/$', echo, name="echo"),
                       url(r'idlookup/(?P<source>[^/]+)/$', idLookup, name="idlookup"),
                       url(r'next_token/$', next_token, name="next_token"),
                       url(r'add_token/$', add_token, name="add_token"),
                       url(r'lov/(?P<group>[^/]+)/?$', lov, name="lov"),
                       url(r'upload/$', upload_file, name="upload"),
                       url(r'static/design_rules/$', design_rules, name="design_rules"),
                       url(r'static/choices/$', choices, name="choices"),
                       url(r'translate/$', translate, name="translate"),
                       url(r'tokenize/$', tokenize, name="tokenize"),
                       url(r'crud/delete/(?P<model_name>[^/]+)/(?P<pk>[^/]{24})/$', delete, name="crud_delete"),
                       url(r'crud/write/(?P<model_name>[^/]+)/$', write, name="crud_write"),
                       url(r'crud/update/$', update, name="crud_update"),
                       url(r'crud/sync/$', sync, name="crud_sync"),
                       url(r'crud/read/(?P<model_name>.+)/(?P<pagesize>\d+)/(?P<page>\d+)/', read, name="crud_read"),
                       url(r'crud/read/(?P<model_name>[^/]+)/(?P<pk>[^/]+)/', read_one, name="crud_read_one"),
                       url(r'crud/count/(?P<model_name>[^/]+)/', count, name="crud_count"),
                       url(r'documents/rev/(?P<model_name>[^/]+)/(?P<rev_unique_id>[^/]+)/next/', next_revision, name="revision_next"),
                       url(r'documents/rev/(?P<model_name>[^/]+)/(?P<rev_unique_id>[^/]+)/list/', list_revision, name="revision_list"),
                       url(r'permission/can/(?P<action>[^/]+)', user_can, name="user_can"),
                       url(r'offhours/between/(?P<start_time>[0-9]+(\.[0-9]+)?)/(?P<end_time>[0-9]+(\.[0-9]+)?)/?', offhours_between, name="offhours_between"),
                       )

