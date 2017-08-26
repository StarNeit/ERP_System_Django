# Ajax
from json import JSONDecoder
from django.utils.translation import ugettext as _
from intramanee.common.errors import BadParameterError, ValidationError
from intramanee.common.models import IntraUser
from django.conf.urls import patterns, url
from intramanee.common.decorators import ajaxian as ajax_link
from intramanee.common.utils import NOW

# Logic
from intramanee.production import documents as prod_doc
from intramanee.stock import documents as stock_doc
from intramanee.task import documents as task_doc
from intramanee.common.documents import doc_dict, Docs
from intramanee.common.location import Location

# API
from intramanee.stock.service import ReturningAPI


@ajax_link(good_operations="GET")
def holding_pen(request):
    """
    Query all tasks to be prepared within today.

    :param request:
    :return: [{
        '_id': <store_aux_task_id>
        'materials': [ ],
        'status': <store_aux_status>,
        /* parent task */
        'parent_task': <parent_task_id>,
        'parent_task_code': <parent_task_code>,
        'planned_start': <parent_task_planned_start>,
        'planned_end': <parent_task_planned_end>,
        /* production order */
        'po_doc_no': <production_order_doc_no>,
        'po_id': <production_order_id>
        /* activity */
        'activity': <activity_object>?
    }]
    """
    # today operation tasks
    parent_tasks = doc_dict(prod_doc.ProductionOrderOperation.manager.project({
        'planned_start': {
            '$lt': NOW().replace(hour=23, minute=59, second=59)
        },
        '$and': [
            {'status': {'$gte': prod_doc.ProductionOrderOperation.STATUS_RELEASED}},
            {'status': {'$lt': prod_doc.ProductionOrderOperation.STATUS_CONFIRMED}}
        ]
    }, project=['task', 'ref_doc', 'planned_start', 'planned_end']))

    # all store aux tasks associated
    aux_tasks = task_doc.StoreAuxTask.manager.find(cond={
        'status': {'$lt': task_doc.StoreAuxTask.STATUS_DELIVERED},
        'parent_task': {
            '$in': parent_tasks.keys()
        }
    })

    # transmute StoreAuxTask object to correct materials

    # valid_parent_tasks
    def transmute_and_patch_parent_task(aux_task_object):
        # transmute (to dict())
        aux_task = {
            '_id': aux_task_object.object_id,
            'doc_no': aux_task_object.doc_no,
            'parent_task': aux_task_object.parent_task,
            'status': aux_task_object.status,
            'materials': map(lambda a: a.serialized(), aux_task_object.list_components())
        }

        # patch parent_task
        parent_task_id = aux_task_object.parent_task
        pt = parent_tasks[parent_task_id]
        aux_task.update({
            'parent_task_code': pt['task'],
            'planned_start': pt['planned_start'],
            'planned_end': pt['planned_end'],
            'po_id': pt['ref_doc'][0]
        })
        return aux_task
    aux_tasks = map(transmute_and_patch_parent_task, aux_tasks)

    # valid production orders
    product_orders = doc_dict(prod_doc.ProductionOrder.manager.project({
        '_id': {
            '$in': map(lambda a: a['po_id'], aux_tasks)
        }
    }, project=['doc_no']))

    # activities
    activities = doc_dict(prod_doc.UserActiveTask.manager.project({
        'operation': {
            '$in': map(lambda a: a['_id'], aux_tasks)
        }
    }), 'operation')

    def patch_with_production_order_and_activity(aux_task):
        aux_task_id = aux_task['_id']
        aux_task.update({
            'po_doc_no': product_orders[aux_task['po_id']]['doc_no'],
            'activity': activities[aux_task_id] if aux_task_id in activities else None
        })
        return aux_task

    return map(patch_with_production_order_and_activity, aux_tasks)


@ajax_link(good_operations="GET")
def return_candidates(request, doc_no):
    return ReturningAPI.return_candidates(doc_no)


@ajax_link(good_operations="POST")
def return_materials(request, doc_no, type):
    """
    Returning Materials - please see #return_candidates for more information.

    :param request:
    :param doc_no:
    :param type:
    :return:
    """
    # Required parameters
    return_list = JSONDecoder().decode(request.POST.get('return_list'))
    if return_list is None or len(return_list) == 0:
        raise BadParameterError.required('return_list')

    return ReturningAPI.return_materials(user=request.user,
                                         doc_no=doc_no,
                                         mode=type,
                                         return_list=return_list)


@ajax_link(good_operations="POST")
def create_material_requisition(request, doc_no):
    """

    :param request:
    :param basestring doc_no:
    :return:
    """
    # Required parameters
    material_list = JSONDecoder().decode(request.POST.get('material_list'))
    return ReturningAPI.create_material_requisition(request.user, doc_no, material_list)

urlpatterns = patterns('',
                       url(r'material_requisition/(?P<doc_no>[^/]+)/', create_material_requisition, name="create_material_requisition"),
                       url(r'return_materials/(?P<doc_no>[^/]+)/(?P<type>[^/]+)/', return_materials, name="return_materials"),
                       url(r'return_candidates/(?P<doc_no>[^/]+)/', return_candidates, name="return_candidates"),
                       url(r'holding_pen/$', holding_pen, name="holding_pen"),
                       )
