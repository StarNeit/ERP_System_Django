__author__ = 'peat'

from intramanee.decorator import menu_item, inject_data
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import requires_csrf_token
from intramanee.common.task import Task


@menu_item('material-list')
def material_list(request):
    return TemplateResponse(request, 'stock/material_list.html', {'page_title': _('PAGE_TITLE_MATERIALS')})


@requires_csrf_token
@inject_data(active_menu='material-new',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def material_new(request):
    return TemplateResponse(request, 'stock/material_new.html', {'page_title': _('PAGE_TITLE_CREATE_MATERIAL')})


@requires_csrf_token
@inject_data(active_menu='material-edit',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def material_edit(request, pk):
    return TemplateResponse(request, 'stock/material_new.html', {'page_title': _('PAGE_TITLE_EDIT_MATERIAL'), 'material_id': pk})


@requires_csrf_token
@inject_data(active_menu='inventory-dashboard',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def inventory_dashboard(request):
    return TemplateResponse(request, 'stock/dashboard.html', {'page_title': _('PAGE_TITLE_INVENTORY_DASHBOARD'), 'collapse_on_start': True})


@requires_csrf_token
@menu_item('movement-new')
def movement_new(request):
    return TemplateResponse(request, 'stock/movement_new.html', {'page_title': _('PAGE_TITLE_CREATE_MOVEMENT')})


@requires_csrf_token
@menu_item('movement-detail')
def movement_detail(request, pk):
    return TemplateResponse(request, 'stock/movement_new.html', {'page_title': _('PAGE_TITLE_MOVEMENT'), 'doc_id': pk})


@inject_data(tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def material_tags(request):
    return TemplateResponse(request, 'stock/material_tag.html', {})


@requires_csrf_token
@inject_data(active_menu='requisition',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def requisition_new(request):
    return TemplateResponse(request, 'stock/requisition_new.html', {'page_title': _('PAGE_TITLE_MATERIAL_REQUISITION')})
