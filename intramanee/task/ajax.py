# Ajax
from json import JSONDecoder
from django.utils.translation import ugettext as _
from intramanee.common.errors import BadParameterError
from django.conf.urls import patterns, url
from intramanee.common.decorators import ajaxian as ajax_link
from intramanee.common.utils import NOW
# Logic
import documents as task_doc

# FIXME: Deprecated?
@ajax_link(good_operations="POST")
def confirm_store_aux_task(request, id):
    """
    StoreAuxTask does NOT associate itself with UserActiveTask when it started.

    Therefore we can just confirm it with synthetic actual_data (NOW(), NOW(), 0)

    :param request:
    :param id:
    :return:
    """
    # extract incoming materials
    materials = JSONDecoder().decode(request.POST.get('materials'))

    # lookup for aux_task first
    try:
        aux_task = task_doc.StoreAuxTask(id)
    except ValueError:
        raise BadParameterError(_("ERR_INVALID_STORE_AUX_TASK: %(id)s") % {'id': id})

    # Build confirmation
    confirm = task_doc.AuxiliaryTaskConfirmation.factory(NOW(), NOW(), 0, request.user)

    # Extract materials for confirmation
    def convert_materials(material_dict):
        return task_doc.TaskComponent.factory(material_dict['material'],
                                              material_dict['revision'],
                                              material_dict['size'],
                                              material_dict['quantity'])
    confirm.materials = map(convert_materials, materials)

    # Submit to confirm
    aux_task.confirm(request.user, confirm)
    return True

# FIXME: Deprecated?
@ajax_link(good_operations="POST")
def confirm_clerk_aux_task(request, id):
    """
    ClerkAuxTask does start by associate itself with UserActiveTask before it proceeds.

    Meaning that we will need to stop current association of UserActiveTask. And we calculate
    the end date from that point

    :param request:
    :param id:
    :return:
    """
    # extract incoming materials
    materials = JSONDecoder().decode(request.POST.get('materials'))

    # lookup for aux_task first
    aux_task = task_doc.ClerkAuxTask(id)

    # Build confirmation
    confirm = task_doc.AuxiliaryTaskConfirmation.factory(NOW(), NOW(), 0, request.user)

    # Extract materials for confirmation
    def convert_materials(material_dict):
        return task_doc.TaskComponent.factory(material_dict['material'],
                                              material_dict['revision'],
                                              material_dict['size'],
                                              material_dict['quantity'])

    confirm.materials = map(convert_materials, materials)

    # Submit to confirm
    aux_task.confirm(request.user, confirm)
    return True


urlpatterns = patterns('',
                       url(r'aux/store/(?P<id>[^/]{24})/confirm$', confirm_store_aux_task, name="confirm_store_aux_task"),
                       url(r'aux/clerk/(?P<id>[^/]{24})/confirm$', confirm_clerk_aux_task, name="confirm_clerk_aux_task"),
                       )
