from intramanee.common.errors import BadParameterError, ValidationError
from intramanee.common.models import IntraUser
from django.conf.urls import patterns, url
from intramanee.common.decorators import ajaxian as ajax_link
import documents as prod_doc
from bson import ObjectId
from json import JSONDecoder
from intramanee.common.room import Room
from datetime import datetime
from intramanee.production.documents import UserActiveTask, TaskDoc, ProductionOrder, ProductionOrderOperation, StoreAuxTask
from django.utils.translation import ugettext as _
from intramanee.task.documents import ClerkAuxTask
from intramanee.stock.documents import MaterialMaster
from itertools import chain


@ajax_link(good_operations="POST")
def release(request):
    results = []
    orders = JSONDecoder().decode(request.POST.get('orders'))

    def release_order(o):
        order = prod_doc.ProductionOrder(o)
        try:
            order.release(request.user)
            results.append(order.object_id)
        except ValidationError:
            pass

    map(release_order, orders)
    return results


@ajax_link(good_operations=("POST", "GET"))
def room_dashboard(request, room_code, doc_no, action):
    try:
        room = Room.factory(room_code)
    except KeyError:
        raise BadParameterError(_("ERR_UNABLE_TO_IDENTIFY_ROOM"))

    if request.method == 'POST':
        if action is None:
            raise BadParameterError.required('action')

        if action == 'deliverable':
            """
            POST Method, action="deliverable"

            Probe Job Tags for delivery candidates

            If condition met: all(previous_op.status == DELIVERED) and ClerkAuxTask.is_confirmed() then adjust operation
            status to READY.

            :returns [{}] deliverable
            """
            if doc_no is None or len(doc_no) == 0:
                raise BadParameterError.required('production_order_doc_no')

            production_order = ProductionOrder.of('doc_no', doc_no)

            # User requested to update these task as "Ready"
            if production_order is None:
                raise BadParameterError(_("ERR_UNKNOWN_PRODUCTION_ORDER: %(doc_no)s") % {
                    'doc_no': doc_no
                })
            ready_operations = production_order.pending_tasks(lambda operation: operation.task in room.tasks)

            # Only previous operation of ready_operations where by ...
            #   => prev_op.status == STATUS_CONFIRMED
            def traverse():
                for ready_op in ready_operations:
                    for prev_op in ready_op.previous_op():
                        if prev_op.status == ProductionOrderOperation.STATUS_CONFIRMED:
                            yield prev_op
            return map(lambda a: {
                'doc_no': a.doc_no,
                'object_id': str(a.object_id),
                'task': a.task.code
            }, traverse())
        elif action == "delivered":
            """
            POST Method, action="delivered"

            Assign Delivered status to provided doc_no, and set next_op to ready if possible...

            :raises BadParameter if doc_no is not ``TaskDocNo``
            :returns Boolean
            """
            if doc_no is None or len(doc_no) == 0:
                raise BadParameterError.required('task_doc_no')

            production_order_operation = ProductionOrderOperation.of('doc_no', doc_no)

            if production_order_operation is None:
                raise BadParameterError(_("ERR_UNKNOWN_PRODUCTION_ORDER_OPERATION_DOC_NO: %(doc_no)s") % {
                    'doc_no': doc_no
                })

            # Check if we can set this doc status to ready or not?
            if production_order_operation.status != ProductionOrderOperation.STATUS_CONFIRMED:
                raise ValidationError(_("ERR_UNABLE_TO_UPDATE_UNCONFIRMED_OPERATION_TO_DELIVERED: %(doc_no)s") % {
                    'doc_no': doc_no
                })

            # Update the status
            production_order_operation.status = ProductionOrderOperation.STATUS_DELIVERED
            production_order_operation.touched(request.user)

            production_order_operation.ready_next_operation_if_possible(author=request.user, context_room=room)
            return True

        raise BadParameterError(_("ERR_UNSUPPORTED_ACTION: %(action)s") % {
            'action': action
        })

    if request.method == 'GET':
        # Query all parent task within the room
        results = ProductionOrderOperation.manager.find(cond={
            'planned_start': {
                '$lt': datetime.today().replace(hour=23, minute=59, second=59)
            },
            '$and': [
                {'status': {'$gte': ProductionOrderOperation.STATUS_RELEASED}},
                {'status': {'$lt': ProductionOrderOperation.STATUS_CONFIRMED}}
            ],
            'task': {
                '$in': room.tasks
            }
        })
        ref_docs = list(set(o.ref_doc[0] for o in results))

        orders = ProductionOrder.manager.project({'_id': {'$in': ref_docs}},
                                                 project=['_id', 'doc_no'])
        # query clerk's auxiliary task status
        aux_tasks = ClerkAuxTask.manager.aggregate([
            {"$group": {"_id": "$parent_task", "status": {"$min": "$status"}}}
        ])
        aux_tasks = dict((a['_id'], a['status']) for a in aux_tasks['result'])

        def process_task_output(a):
            r = a.serialized()
            # patch with previous_op statues
            previous_ops = []
            for prev_op in a.previous_op():
                previous_ops.append({
                    'object_id': str(prev_op.object_id),
                    'task': prev_op.task.code,
                    'doc_no': prev_op.doc_no,
                    'status': prev_op.status
                })
            r['previous_ops'] = previous_ops
            # patch with aux_task status
            key = a.object_id
            r['clerk_confirmed'] = aux_tasks[key] if key in aux_tasks else 0
            return r

        return {
            'orders': dict(map(lambda a: (str(a['_id']), a['doc_no']), orders)),
            'tasks': map(process_task_output, results),
            'activities': map(lambda a: a.as_json(), UserActiveTask.probe_all(results))
        }


@ajax_link(good_operations=("POST", "GET"))
def activity_endpoint(request, identification, action=None):
    try:
        identification = ObjectId(identification)
    except:
        raise BadParameterError('id %s is not valid bson.ObjectId')

    operation_doc_id = identification
    # Check if operation exists
    try:
        op = TaskDoc.manager.factory('task', operation_doc_id)
    except ValueError:
        raise BadParameterError('Unknown operation %s' % operation_doc_id)

    if request.method == 'GET':
        # probe for status
        previous_op_count = len(op.previous_op())
        if op.get_confirmable_quantity() <= 0 or (previous_op_count == 0 and op.status != ProductionOrderOperation.STATUS_RELEASED) or (previous_op_count > 0 and op.status != ProductionOrderOperation.STATUS_READY):
            return False
        r = UserActiveTask.probe(operation=op)
        return r.as_json() if r is not None else None

    if request.method == 'POST':

        # identify intention
        action = 'start' if action is None or action == '' else action

        # really perform the actions
        if action == 'start':
            # user code is required from this point
            user_code = request.POST.get('user_code')
            if not user_code:
                raise BadParameterError(_('ERR_USER_CODE_REQUIRED'))
            try:
                assignee = IntraUser.objects.get(code=user_code)
            except:
                raise BadParameterError('Unknown user %s' % user_code)

            o = UserActiveTask.start(assignee=assignee, operation=op, author=request.user)
            return o.as_json()

        # from this point we will need the probed object
        activity = UserActiveTask.probe(operation=op)

        if activity is None:
            raise BadParameterError(_("ERR_ACTIVITY_NOT_YET_STARTED"))

        if action in ['pause', 'resume']:
            if action == 'pause':
                activity.pause()
            if action == 'resume':
                activity.resume()
            activity.touched(request.user)
            return activity.as_json()

        if action == 'stop':
            # Anything that the task should required upon its confirm method.
            confirmation_details = JSONDecoder().decode(request.POST.get('details'))

            # Stop task with details
            activity.stop(request.user, **confirmation_details)

            # Delete active task
            UserActiveTask.manager.delete(cond={
                '_id': activity.object_id
            })
            return action

    raise BadParameterError(_("ERR_INVALID_OPERATION"))


@ajax_link(good_operations="POST")
def material_staging_form(request):
    tasks = filter(lambda a: a, request.POST.get('tasks', '').split(','))
    o = prod_doc.MaterialStagingForm.factory(tasks)
    if o is None:
        raise BadParameterError(_("ERR_FAILED_TO_IDENTIFY_AUXILIARY_TASKS"))
    o.touched(request.user)
    return o.object_id


@ajax_link(good_operations="GET")
def confirmable_content(request, operation_id):
    op = prod_doc.ProductionOrderOperation(operation_id)
    planned_make_materials, staged_inventory_content = op.get_confirmable_content()

    # Shape the output
    def shape_output():
        # [ProductionOrderComponent]
        for mat in planned_make_materials:
            yield {
                'material': str(mat.material),
                'quantity': -1 * mat.quantity,
                'uom': mat.uom,
                'value': 0,
                'weight': 0
            }
        # [InventoryContent]
        for inv_content in staged_inventory_content:
            yield {
                'material': str(inv_content.material),
                'quantity': -1 * inv_content.quantity,
                'uom': str(MaterialMaster.get(inv_content.material).uom),
                'batch': str(inv_content.batch),
                'value': -1 * inv_content.value,
                'weight': -1 * inv_content.weight
            }
    return list(shape_output()), op.get_confirmable_quantity()


@ajax_link(good_operations="POST")
def task_endpoint(request, task_object_id, action):
    if action == "revert":
        task = TaskDoc.of('_id', ObjectId(task_object_id))
        # Sanity check
        if task is None:
            raise BadParameterError(_("ERR_UNKNOWN_DOCUMENT_ID: %(document_id)s") % {
                'document_id': task_object_id
            })

        if not isinstance(task, StoreAuxTask):
            raise BadParameterError(_("ERR_CANNOT_REVERT_TASK: %(task_type)s") % {
                'task_type': type(task)
            })

        return task.revert(request.user)

    raise BadParameterError(_("ERR_INVALID_ACTION: %(action)s") % {
        'action': action
    })

urlpatterns = patterns('',
                       url(r'release', release, name="release"),
                       url(r'activity/task/(?P<identification>[^/]{24})/(?P<action>(stop|pause|resume)?)', activity_endpoint, name="activity_endpoint"),
                       url(r'task/(?P<task_object_id>[^/]{24})/(?P<action>(revert)?)', task_endpoint, name="task_endpoint"),
                       url(r'room_dashboard/(?P<room_code>[^/]+)/(?P<doc_no>([^/]+)?)/?(?P<action>(deliverable|delivered)?)/?', room_dashboard, name="room_dashboard"),
                       url(r'confirmable_content/(?P<operation_id>[^/]{24})/', confirmable_content, name="confirmable_content"),
                       url(r'material_staging_form/?', material_staging_form, name="material_staging_form")
                       )
