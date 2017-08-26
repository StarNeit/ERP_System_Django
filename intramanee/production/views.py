__author__ = 'haloowing'

from intramanee.decorator import menu_item, inject_data
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.utils.translation import gettext_noop
from django.views.decorators.csrf import requires_csrf_token
from django.forms.models import model_to_dict
from intramanee.common.task import Task
from intramanee.common.models import IntraUser
from intramanee.production.documents import Machine, ProductionOrder, ProductionGroupedOperation, ProductionProposal, ProductionOrderOperation, MaterialStagingForm
from datetime import datetime


@menu_item('production-order-list')
def production_order_list(request):
    return TemplateResponse(request, 'production/production_order_list.html', {'page_title': _('PAGE_TITLE_PRODUCTION_ORDERS')})


@requires_csrf_token
@inject_data(tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def production_dashboard(request, pk):
    gettext_noop('ROOM_TITLE_5340')
    gettext_noop('ROOM_TITLE_5390')
    gettext_noop('ROOM_TITLE_5400')
    gettext_noop('ROOM_TITLE_5430')
    return TemplateResponse(request, 'production/dashboard.html', {'page_title': _('PAGE_TITLE_DASHBOARD') + ' : ' + _('ROOM_TITLE_' + pk), 'collapse_on_start': True, 'active_menu': 'production-dashboard-' + pk, 'room_id': pk})


@requires_csrf_token
@inject_data(active_menu='production-order-new',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def production_order_new(request):
    return TemplateResponse(request, 'production/production_order_new.html', {'page_title': _('PAGE_TITLE_CREATE_PRODUCTION_ORDER')})


@requires_csrf_token
@inject_data(active_menu='production-order-edit',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def production_order_edit(request, pk):
    return TemplateResponse(request, 'production/production_order_new.html', {'page_title': _('PAGE_TITLE_EDIT_PRODUCTION_ORDER'), 'order_id': pk, 'collapse_on_start': True})


@requires_csrf_token
@inject_data(active_menu='production-order-operation',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def production_order_operation(request, pk, sk):
    design = None
    try:
        production_order = ProductionOrder(pk)
        design = production_order.design()
    except ValueError as e:
        pass
    return TemplateResponse(request, 'production/production_order_operation.html', {
        'page_title': _('PAGE_TITLE_OPERATION'),
        'order_id': pk,
        'operation_id': sk,
        'design': design.as_json() if design is not None else None,
        'collapse_on_start': True
    })


@inject_data(tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def job_tags(request):
    return TemplateResponse(request, 'production/job_tags.html', {})


@inject_data(tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def staging_form_print(request, pk):
    doc = MaterialStagingForm(pk)
    return TemplateResponse(request, 'production/staging_form_print.html', {'doc_id': pk, 'doc': doc.as_json()})


@inject_data(active_menu='staging-form',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def staging_form(request, pk):
    doc = MaterialStagingForm(pk)
    return TemplateResponse(request, 'production/staging_form.html', {'doc_id': pk, 'doc': doc.as_json(), 'page_title': _('PAGE_TITLE_STAGING_FORM')})


@requires_csrf_token
@inject_data(active_menu='operation-group-manager',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def operation_group_manager(request):
    return TemplateResponse(request, 'production/batch.html', {'page_title': _('PAGE_TITLE_OPERATION_GROUP_MANAGER')})


def get_order_and_groups():
    orders = ProductionOrder.manager.find(cond={
         '$or': [
             {
                 'status': {
                     '$lt': ProductionOrder.STATUS_CONFIRMED
                 }
             },
             {
                 'status': ProductionOrder.STATUS_CONFIRMED,
                 'actual_end': {
                     '$gte': datetime.now().replace(hour=0, second=0, minute=0, microsecond=0)
                 }
             }
         ],
         '$sort': 'doc_no'
    })
    operations = (oid for o in orders for oid in o.operation)
    operations = ProductionOrderOperation.manager.find(cond={
        '_id': {'$in': list(operations)}
    })

    def find_operation(op_id):
        return next((o for o in operations if o.object_id == op_id), None)

    def loop_orders(o):
        for i, op in enumerate(o.operation):
            new_op = find_operation(op)
            if new_op:
                o.operation[i] = new_op

    map(loop_orders, orders)

    groups = ProductionGroupedOperation.manager.find(cond={
        '_id': {'$in': list((op.group for op in operations if op.group))}
    })

    return map(ProductionOrder.serialized, orders), map(ProductionGroupedOperation.serialized, groups)


def get_proposal():
    proposal = ProductionProposal.get()
    return proposal.serialized() if proposal is not None else None


@requires_csrf_token
@inject_data(active_menu='planning-tool',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()),
             machines=lambda: [{u.code: {'availability': u.availability}} for u in Machine.manager.find(0)],
             operators=lambda: dict(map(lambda u: (str(u.code), model_to_dict(u, ['first_name', 'last_name', 'permissions'])), IntraUser.objects.all())),
             orders_and_groups=get_order_and_groups,
             proposal=get_proposal)
def planning_tool(request):
    return TemplateResponse(request, 'production/tool.html', {'page_title': _('PAGE_TITLE_PLANNING'), 'collapse_on_start': True})


@inject_data(active_menu='stock-requirement')
def stock_requirement(request):
    return TemplateResponse(request, 'production/stock_requirement.html', {'page_title': _('PAGE_TITLE_STOCK_REQUIREMENT')})


@inject_data(active_menu='mrp')
def mrp(request):
    return TemplateResponse(request, 'production/mrp.html', {'page_title': _('PAGE_TITLE_MRP')})