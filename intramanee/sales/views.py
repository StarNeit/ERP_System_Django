__author__ = 'peat'

from intramanee.decorator import menu_item
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import requires_csrf_token

@menu_item('sales-order-list')
def sales_order_list(request):
    return TemplateResponse(request, 'sales/sales_order_list.html', {'page_title': _('PAGE_TITLE_SALES_ORDERS')})

@requires_csrf_token
@menu_item('sales-order-new')
def sales_order_new(request):
    return TemplateResponse(request, 'sales/sales_order_new.html', {'page_title': _('PAGE_TITLE_CREATE_SALES_ORDER')})

@requires_csrf_token
@menu_item('sales-order-edit')
def sales_order_edit(request, pk):
    return TemplateResponse(request, 'sales/sales_order_new.html', {'page_title': _('PAGE_TITLE_EDIT_SALES_ORDER'), 'order_id': pk})
