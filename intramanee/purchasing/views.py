from intramanee.decorator import menu_item, inject_data
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import requires_csrf_token
from django.forms.models import model_to_dict
from intramanee.common.task import Task
from intramanee.common.models import IntraUser


@menu_item('pr-list')
def pr_list(request):
    return TemplateResponse(request, 'purchasing/pr_list.html', {'page_title': _('PAGE_TITLE_PURCHASE_REQUISITIONS')})


@menu_item('pr-view')
def pr_view(request, pk):
    return TemplateResponse(request, 'purchasing/pr_view.html', {'page_title': _('PAGE_TITLE_PURCHASE_REQUISITION'), 'pr_id': pk})
