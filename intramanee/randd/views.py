__author__ = 'peat'

from intramanee.decorator import menu_item, inject_data
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import requires_csrf_token
from intramanee.common.task import Task


@menu_item('randd-task')
def rd_task(request):
    return TemplateResponse(request, 'randd/tasks.html', {'page_title': _('PAGE_TITLE_TASKS')})


@menu_item('randd-design-list')
def design_list(request):
    return TemplateResponse(request, 'randd/design_list.html', {'page_title': _('PAGE_TITLE_DESIGNS')})


@requires_csrf_token
@inject_data(active_menu='randd-design-new',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def design_new(request):
    return TemplateResponse(request, 'randd/design_new.html', {'page_title': _('PAGE_TITLE_CREATE_DESIGN'), 'collapse_on_start': True})


@requires_csrf_token
@inject_data(active_menu='randd-design-edit',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def design_edit(request, pk):
    return TemplateResponse(request, 'randd/design_new.html', {'page_title': _('PAGE_TITLE_EDIT_DESIGN'), 'design_id': pk, 'collapse_on_start': True})
