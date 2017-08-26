__author__ = 'haloowing'

from intramanee.decorator import menu_item, inject_data
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.utils.translation import gettext_noop
from django.views.decorators.csrf import requires_csrf_token
from django.forms.models import model_to_dict
from intramanee.common.task import Task
from intramanee.common.models import IntraUser


@requires_csrf_token
@inject_data(active_menu='qc-dashboard',
             tasks=map(lambda o: o[1].serialize(), Task.tasks.iteritems()))
def dashboard(request):
    return TemplateResponse(request, 'quality/dashboard.html', {'page_title': _('PAGE_TITLE_DASHBOARD'), 'collapse_on_start': True, 'room_id': 5450})
