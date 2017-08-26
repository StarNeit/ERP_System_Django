from intramanee.bot.service import Robot
from intramanee.bot import documents as doc
from intramanee.common import errors as err
from intramanee.common.decorators import ajaxian as ajax_link
from django.conf.urls import patterns, url
from json import JSONDecoder


@ajax_link
def list_stock_requirement(request, material_code, revision=None, size=None):
    if revision is not None:
        revision = int(revision)
    return Robot.list_stock_requirement(material_code, revision, size)


@ajax_link
def mrp_session_endpoint(request):
    if request.method == 'GET':
        # Get sessions
        cond = request.GET.get('cond', None)
        cond = JSONDecoder().decode(cond) if cond is not None else None
        return map(lambda a: {
            '_id': a.object_id,
            'target_materials': map(lambda a: (str(a[0]), a[1], a[2]), [] if a.target_materials is None else a.target_materials),
            'errors': [] if a.errors is None else a.errors,
            'start': a.start,
            'end': a.end
        }, doc.MRPSession.manager.find(pagesize=30, page=0, cond=cond))
    elif request.method == 'POST':
        material_spec = request.POST.get('material_spec', None)
        material_spec = JSONDecoder().decode(material_spec) if material_spec is not None else None
        return Robot.run_mrp(request.user, material_spec)
    raise err.ProhibitedError('Unsupported endpoint')

urlpatterns = patterns('',
                       url(r'list_stock_requirement/(?P<material_code>[^/]+)/?$', list_stock_requirement, name="list_stock_requirement_material_only"),
                       url(r'list_stock_requirement/(?P<material_code>[^/]+)/(?P<revision>[\d+])/?$', list_stock_requirement, name="list_stock_requirement_with_revision"),
                       url(r'list_stock_requirement/(?P<material_code>[^/]+)/(?P<revision>[\d+])/(?P<size>[^/]+)/?$', list_stock_requirement, name="list_stock_requirement"),
                       url(r'mrp/?$', mrp_session_endpoint, name="mrp_session_endpoint"),
                       )