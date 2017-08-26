__author__ = 'haloowing'

from django.template.response import TemplateResponse
from .decorator import menu_item


@menu_item('home')
def dashboard(request):
    return TemplateResponse(request, 'common/dashboard.html')

