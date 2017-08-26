__author__ = 'wasansae-ngow'
from intramanee.common.decorators import JsonSerializable
from intramanee.common.errors import ValidationError, BadParameterError
from intramanee.common import codes, documents as doc
from intramanee.common.room import Room
from django.utils.translation import ugettext as _
from intramanee.common.location import Location
from intramanee.stock.documents import MaterialMaster, InventoryMovement, InventoryMovementEntry, InventoryContent
from intramanee.task.documents import TaskDoc, Confirmation, TaskComponent, ClerkAuxTask, TaskGroup, StoreAuxTask, TASK_PERM_OVERRIDE_ASSIGNEE
from intramanee.sales.documents import SalesOrder
from intramanee.common.calendar import documents as OffHour
from intramanee.common.resource import Resource
from intramanee.common.task import Task
from intramanee.common.utils import print_verbose
from dateutil.relativedelta import relativedelta
from operator import attrgetter
import datetime
import math
from bson import ObjectId
from intramanee.task import signals as task_signals
from intramanee.common.models import IntraUser
from intramanee.common.errors import BadParameterError
from intramanee.common import utils, signals as common_signals
from django.dispatch import receiver

PRODUCTION_ORDER_NUMBER_KEY = 'PRODUCTION_ORDER_NUMBER'
PRODUCTION_ORDER_NUMBER_PREFIX = 'PD'

STAGING_FORM_NUMBER_KEY = 'STAGING_FORM_NUMBER'
STAGING_FORM_NUMBER_PREFIX = 'STG'


class Machine(doc.Authored, Resource):
    code = doc.FieldString()
    manufacturer = doc.FieldString()
    availability = doc.FieldNumeric(choices=Resource.RESOURCE_STATUSES, default=Resource.STATUS_AVAILABLE)

    def validate(self):
        if not Task.filter(self.code[:4]):
            raise ValidationError(_("ERROR_FIRST_4_DIGITS_MUST_BE_TASK_CODE"))

    def set_available(self):
        self.availability = self.STATUS_AVAILABLE

    def set_unavailable(self):
        self.availability = self.STATUS_UNAVAILABLE

    @classmethod
    def factory(cls, code, user, manufacturer=None, **kwargs):
        machine = cls()
        machine.code = code

        if manufacturer:
            machine.manufacturer = manufacturer

        machine.touched(user, **kwargs)
        return machine

    class Meta:
        collection_name = 'machine'


class ProductionOrderComponent(TaskComponent):
    # assign in back end
    cost = doc.FieldNumeric(default=0)

    @classmethod
    def factory(cls, schematic_material, quantity, size_index, **kwargs):
        # init with default schematic
        mm = MaterialMaster.factory(schematic_material.code)

        material = cls()
        material.material = schematic_material.code
        material.quantity = math.ceil((schematic_material.quantity[size_index] * quantity) / mm.scale)
        mm.populate('schematic')
        material.revision = None if mm.schematic is None else mm.schematic.rev_id
        material.uom = schematic_material.counter
        material.cost = schematic_material.cost

        return material

    def __eq__(self, other):
        return self.dox == other.dox

    def __repr__(self):
        return "ProductionOrderComponent material_key=[%s]" % self.material_key()


class ProductionConfirmationComponent(TaskComponent):
    batch = doc.FieldString(none=True)
    value = doc.FieldNumeric(default=0)
    weight = doc.FieldNumeric(default=0)

    @classmethod
    def factory(cls, batch=None, value=None, weight=None, **kwargs):
        o = super(ProductionConfirmationComponent, cls).factory(**kwargs)
        o.batch = batch
        o.value = value
        o.weight = weight
        return o


class ProductionConfirmation(Confirmation):
    # assign from front end
    confirm_yield = doc.FieldNumeric()
    scrap = doc.FieldNumeric(default=0)
    materials = doc.FieldList(doc.FieldNested(ProductionConfirmationComponent))
    movement = doc.FieldList(doc.FieldDoc(InventoryMovement))
    durations = doc.FieldList(doc.FieldDateTime())
    weight = doc.FieldNumeric(none=True)

    @classmethod
    def create(cls, confirm_yield, scrap, durations, weight, materials, **kwargs):
        o = super(ProductionConfirmation, cls).create(**kwargs)
        o.materials = map(lambda x: ProductionConfirmationComponent.factory(**x), materials)
        o.confirm_yield = confirm_yield
        o.scrap = scrap
        o.durations = durations
        o.weight = weight
        return o


class ProductionBaseTask(TaskDoc):
    planned_start = doc.FieldDateTime(none=True)
    planned_end = doc.FieldDateTime(none=True)
    materials = doc.FieldList(doc.FieldNested(ProductionOrderComponent))
    confirmations = doc.FieldList(doc.FieldNested(ProductionConfirmation))

    def find_material(self, material):
        return next((sm for sm in self.materials if sm.material == material.material and
                     sm.size == material.size and
                     sm.revision == material.revision), None)

    def get_total_yield(self):
        conf = filter(lambda x: not x.cancelled, self.confirmations)
        return 0 if not conf else reduce(lambda x, y: x+y, [y.confirm_yield for y in filter(lambda x: not x.cancelled, self.confirmations)])

    def get_total_scrap(self):
        conf = filter(lambda x: not x.cancelled, self.confirmations)
        return 0 if not conf else reduce(lambda x, y: x+y, [y.scrap for y in filter(lambda x: not x.cancelled, self.confirmations)])

    def get_total_confirmed(self):
        return self.get_total_scrap() + self.get_total_yield()


class ProductionOrderOperation(ProductionBaseTask):
    STATUS_OPEN = 0
    STATUS_RELEASED = 1
    STATUS_READY = 2
    STATUS_STARTED = 3          # Obsoleted
    STATUS_PARTIAL_CONFIRMED = 4
    STATUS_CONFIRMED = 5
    STATUS_DELIVERED = 6
    STATUS_CANCELLED = 10

    OPERATION_STATUSES = (
        (STATUS_OPEN, _('OPERATION_STATUS_OPEN')),                  # Default status
        (STATUS_RELEASED, _('OPERATION_STATUS_RELEASED')),          # Upon ProductionOrder approval
        (STATUS_READY, _('OPERATION_STATUS_READY')),              # Upon BoM is prepared in Stock Room
        (STATUS_STARTED, _('OPERATION_STATUS_STARTED')),            # Upon process started by employee
        (STATUS_PARTIAL_CONFIRMED, _('OPERATION_STATUS_PARTIAL_CONFIRMED')),    # Upon process confirmed partially
        (STATUS_CONFIRMED, _('OPERATION_STATUS_CONFIRMED')),        # Upon process completely confirmed
        (STATUS_DELIVERED, _('OPERATION_STATUS_DELIVERED')),
        (STATUS_CANCELLED, _('OPERATION_STATUS_CANCELLED')),        # Upon process cancelled
    )

    CONTROL_INTERNAL = 0
    CONTROL_EXTERNAL = 1

    CONTROL_KEY = (
        (CONTROL_INTERNAL, _('OPERATION_CONTROL_INTERNAL')),
        (CONTROL_EXTERNAL, _('OPERATION_CONTROL_EXTERNAL')),
    )

    # Member Variables
    status = doc.FieldNumeric(none=False, choices=OPERATION_STATUSES, default=STATUS_OPEN)
    source = doc.FieldList(doc.FieldDoc(TaskDoc))
    """:type : [ProductionOrderOperation]"""
    destination = doc.FieldList(doc.FieldDoc(TaskDoc))
    """:type : [ProductionOrderOperation]"""
    # TODO: costing shit
    labor_cost = doc.FieldNumeric(none=False, default=0.0)
    markup = doc.FieldNumeric(none=False, default=0.0)
    remark = doc.FieldString(none=True)
    group = doc.FieldDoc('operation_group')
    waiting_time = doc.FieldNumeric(none=False, default=0.0)
    staging_duration = doc.FieldNumeric(none=False, default=0.0)
    start_time_offset = 0

    # Unused
    control_key = doc.FieldNumeric(choices=CONTROL_KEY, default=CONTROL_INTERNAL)

    def get_full_duration(self):
        return self.planned_duration + self.waiting_time

    def reset_waiting_time(self, user, **kwargs):
        self.waiting_time = 0
        self.planned_end = self.planned_start + datetime.timedelta(minutes=(self.planned_duration + self.staging_duration))
        self.touched(user, **kwargs)

    def add_group(self, user, group, **kwargs):
        if self.group:
            ValidationError(_("ERROR_OPERATION_ALREADY_ASSIGNED_TO_GROUP"))
        self.group = group
        self.touched(user, **kwargs)

    def remove_group(self, user, **kwargs):
        if not self.group:
            ValidationError(_("ERROR_OPERATION_IS_NOT_IN_GROUP"))
        self.group = None
        self.touched(user, **kwargs)

    def cancel(self, user, **kwargs):
        if self.status == self.STATUS_CANCELLED:
            raise ValidationError(_("ERROR_OPERATION_IS_ALREADY_CANCELLED"))

        self.status = self.STATUS_CANCELLED
        super(ProductionOrderOperation, self).cancel(user, **kwargs)

    def get_confirmable_content(self):
        """
        Used by AJAX call, confirmable_content

        :return: tuple(
                    (list) planned_make_materials,      [ProductionOrderComponent]
                    (list) staged_inventory_content     [InventoryContent]
                )
        :raises ValidationError iff 'has_planned_consumption' is True and staged_materials_list is empty
        """
        # self.materials = [ProductionOrderComponent]
        # extract make/take components from self.materials (ignore case quantity == 0)
        # Make
        planned_make_materials = filter(lambda a: a.quantity < 0, self.materials)
        # Take
        planned_consumption_materials = filter(lambda a: a.quantity > 0, self.materials)

        # Query staged inventory content
        staged_inventory_content = InventoryContent.manager.find(cond={
            'location': Location.factory('STAGING').code,
            'ref_doc.0': self.object_id,
            # TODO: Add ref_doc.1 - to 'task' or match 'task':...
        })

        # Validate throw case
        if len(planned_consumption_materials) > 0 and len(staged_inventory_content) == 0:
            raise ValidationError(_("ERR_TASK_REQUIRED_MATERIALS_BUT_NONE_IS_STAGED: %(task)s") % {
                'task': str(self.object_id)
            })

        return planned_make_materials, staged_inventory_content

    def ready_next_operation_if_possible(self, author, context_room=None):
        """
        Try set next operation status = 'STATUS_READY'

        In doing so, need to perform following checks.
            => all(op.status == DELIVERED for op in self.previous_op())

        :param author
        :param context_room - if provided, search through all next_op with given context.
        :return:
        """
        # Validate & Sanitize parameter
        if context_room is not None and not isinstance(context_room, Room):
            context_room = Room.factory(context_room)

        if context_room:
            def filter_callback(task):
                return task.code in context_room.tasks
        else:
            def filter_callback(task):
                return True

        # identify next operation
        next_ops = self.next_op()
        for next_op in filter(lambda o: filter_callback(o.task), next_ops):
            # Set as Ready if possible
            # perform check

            # If no amount to confirm, ready status is not met.
            if next_op.get_confirmable_quantity() <= 0:
                continue

            # Check if all other operations has DELIVERED its content.
            if all(op.status == self.STATUS_DELIVERED for op in next_op.previous_op()):
                next_op.status = self.STATUS_READY
                next_op.touched(author)
        return True

    @classmethod
    def confirmation_class(cls):
        return ProductionConfirmation

    def confirm(self, user, confirmation, verbose=False, **kwargs):
        # TODO: check if material is staged (status = staged)

        if not isinstance(confirmation, ProductionConfirmation):
            raise BadParameterError(_("ERROR_CONFIRMATION_MUST_BE_PRODUCTION_CONFIRMATION"))

        confirmation.created_by = user
        confirmation.created_on = utils.NOW()
        self.populate('ref_doc')

        # Confirmable quantity can be up to yielded quantity from previous op or production order quantity
        confirmable_qty = self.get_confirmable_quantity()

        accumulated_yield = self.get_total_yield()
        accumulated_scrap = self.get_total_scrap()
        total_qty = accumulated_yield + accumulated_scrap

        print_verbose(verbose, 'Yield: %s, Scrap: %s, Total: %s, Confirmable: %s' % (accumulated_yield, accumulated_scrap, total_qty, confirmable_qty))

        if total_qty > confirmable_qty:
            raise ValidationError(_("ERROR_CONFIRMATION_YIELD_SCRAP_EXCEED: %(quantity)s") % {
                'quantity': confirmable_qty
            })

        posting_yield = confirmation.confirm_yield + confirmation.scrap + total_qty

        if posting_yield > confirmable_qty:
            raise ValidationError(_("ERROR_POSTING_QTY_EXCEED"))

        if posting_yield < 0:
            raise ValidationError(_("ERROR_NEGATIVE_POSTING_QTY"))

        # NOTE: Adjust actual time in operation
        if not self.confirmations:
            self.actual_start = confirmation.actual_start
            print_verbose(verbose, 'First confirmation: setting actual_start - %s' % self.actual_start)

        self.actual_duration += confirmation.actual_duration
        print_verbose(verbose, 'Accumulate actual_duration: %s' % self.actual_duration)

        # if confirmed qty = production order qty, operation is confirmed. otherwise, partial confirmed.
        if posting_yield == self.get_order_quantity():
            self.status = self.STATUS_CONFIRMED
            self.actual_end = confirmation.actual_end
            print_verbose(verbose, 'Completely confirmed: actual_end - %s' % self.actual_end)
        else:
            self.status = self.STATUS_PARTIAL_CONFIRMED
            print_verbose(verbose, 'Partially confirmed')

        super(ProductionOrderOperation, self).confirm(user, confirmation, **kwargs)

        if self.is_first():
            self.ref_doc.set_start(user, confirmation.actual_start)

        if self.status == self.STATUS_CONFIRMED and self.is_last():
            self.ref_doc.confirm(user, confirmation.actual_end)

        # NOTE: check if scrap qty > 0, reduce order active qty
        if confirmation.scrap > 0:
            self.set_order_quantity(confirmation.scrap, user)

    def next_op(self):
        """

        :return: (array) ProductionOrderOperation
        """
        self.populate('destination')
        return self.destination

    def previous_op(self):
        """

        :return [ProductionOrderOperation]:
        """
        self.populate('source')
        return self.source

    def get_confirmable_quantity(self):
        if self.status < self.STATUS_RELEASED or self.status >= self.STATUS_CONFIRMED:
            return 0

        if not self.source:
            return self.get_order_quantity()

        self.populate('source')
        return min([x.get_total_yield() for x in self.source])

    def get_open_confirmable_quantity(self):
        return self.get_confirmable_quantity() - self.get_total_confirmed()

    @classmethod
    def factory(cls, schematic, quantity, size_index, **kwargs):
        """
        Create ProductionOrderOperation with 'source' parameter
        As current schematic does not have an idea of what they are just yet.

        Caution: method invoker is responsible for populate the linkage between each operation
        for this data object instance once it has been created.

        Practically:
            * ProductionOrder#read_bom() invoke method will populate source for us.

        :param schematic:
        :param quantity:
        :param size_index:
        :param kwargs:
        :return:
        """
        operation = cls()
        operation.task = schematic.process
        operation.planned_duration = schematic.duration[size_index] if schematic.process.fixed_duration else schematic.duration[size_index] * quantity
        operation.staging_duration = schematic.staging_duration[size_index]
        operation.labor_cost = schematic.labor_cost
        operation.markup = schematic.markup
        operation.materials = []
        operation.id = schematic.id

        if schematic.materials:
            for schematic_material in schematic.materials:
                # schematic_material = [SchematicMaterial]
                material = ProductionOrderComponent.factory(schematic_material, quantity, size_index)
                if material:
                    operation.materials.append(material)

        return operation

    def ready(self, user, **kwargs):
        self.status = self.STATUS_READY
        self.touched(user, **kwargs)

    def release(self, user, **kwargs):
        self.status = self.STATUS_RELEASED
        self.touched(user, **kwargs)
        # dispatch event
        task_signals.task_released.send(self)

    def cancel_confirmation(self, user, index, reason=None, **kwargs):
        if index > len(self.confirmations)-1:
            raise ValidationError(_("ERROR_CONFIRMATION: Confirmation index %(index)s does not exist") % {'index': index})

        if self.confirmations[index].cancel:
            raise ValidationError(_("ERROR_CONFIRMATION: Confirmation index %(index)s is already cancelled") % {'index': index})

        next_op = self.next_op()
        next_op_confirmed = min(map(lambda x: x.get_total_confirmed(), next_op))
        canceling_total = self.confirmations[index].confirm_yield + self.confirmations[index].scrap

        if next_op_confirmed > self.get_total_confirmed() - canceling_total:
            raise ValidationError(_("ERROR_NEXT_OP_CONFIRMED: Next Task %(task)s is already confirmed %(nx_conf)s qty") %
                                  {'task': next_op.task, 'nx_conf': next_op_confirmed})

        # If confirmation contains movement, cancel movement
        if self.confirmations[index].movement:
            self.confirmations[index].populate('movement')
            cancel_doc = []

            def cancel(mv):
                c = mv.do_cancel(user, reason)
                if c:
                    cancel_doc.append(c)

            map(cancel, self.confirmations[index].movement)

            if cancel_doc:
                self.confirmations[index].movement.extend(cancel_doc)

        super(ProductionOrderOperation, self).cancel_confirmation(user, index, **kwargs)

    def is_parent(self, ref_id):
        self.populate('source')
        return self if ref_id in [o.object_id for o in self.source] else None

    def is_last(self):
        self.populate('ref_doc')
        return self.ref_doc.get_last_operation().object_id == self.object_id

    def is_first(self):
        self.populate('ref_doc')
        return self.ref_doc.get_first_operation().object_id == self.object_id

    def is_same_operation_signature(self, another_operation):
        """

        :param another_operation:
        :return: (bool)
        """
        if another_operation is not ProductionOrderOperation:
            raise ValidationError(_("ERR_CANNOT_COMPARE_OPERATION_INVALID_TYPE: %(type)s") % {
                'type': type(another_operation)
            })

        # Compare task_code
        if self.task.code != another_operation.task.code:
            return False

        # Compare materials
        source_materials = set(map(lambda a: a.material_key(), self.materials))
        target_materials = set(map(lambda a: a.material_key(), another_operation.materials))

        return source_materials == target_materials

    def is_groupable_with(self, another_operation):
        """
        Return whether current task, and the supplied candidate_operation are groupable together.

        :param another_operation:
        :return: (boolean)
        """
        # TODO: Check if task is not confirmed

        # Sanity check
        mode, group_key = self.task.get_batch_initiator()
        if mode is None:
            return False

        # Normal check
        # Check if same task
        # Check if same key materials (How to identify key materials?) - Check if same materials
        if not self.is_same_operation_signature(another_operation):
            return False

        # mode is self grouped
        if mode == 'i':
            return True

        # mode is open-and-close-grouped
        def schematic_walk_and_validate(a, b):
            """
            Check (next step) of both a, and b if is the same, and is the closure case or not.
            Current step should be check before calling this method.

            This method perform the check after calling next_op because its main assumption is
            to let the method caller perform the check logic with its parameter first. In the same
            way this method call itself recursively. It performed next_op then check next_op, and
            use next_op() result as a next iteration parameters.

            :param a: Original ProductionOrderOperation
            :param b: Comparing target of ProductionOrderOperation which is already equals to :param a:
            :return: True if equals, otherwise throws ValidationError
            """
            # GOAL: Look for closure operation to terminate the recusive call.

            # Extract next_operations
            a_ops = a.next_op()
            b_ops = b.next_op()

            # In case sizes is not equal.
            if len(a_ops) != len(b_ops):
                raise ValidationError(_("ERR_OPERATION_DOES_NOT_CONTAIN_IDENTICAL_OPERATION_FOOTPRINT: %(a)s %(b)s") % {
                    'a': a,
                    'b': b
                })

            # If there is no next operation
            if len(a_ops) == 0:
                raise ValidationError(_("ERR_CANNOT_IDENTIFY_CLOSURE_OF_BATCH_GROUP: %(group_key)s") % {
                    'group_key': group_key
                })

            # We does not support parallel case
            if len(a_ops) > 1:
                # Cannot identify closure if there is a parallel case.
                raise ValidationError(_("ERR_OPEN_GROUP_BATCH_CANNOT_HANDLE_PARALLEL_SCHEMATIC"))

            next_a = a_ops[0]
            next_b = b_ops[0]

            # Check if next_a, next_b is same operation
            if not next_a.is_same_operation_signature(next_b):
                raise ValidationError(_("ERR_OPERATION_DOES_NOT_CONTAIN_IDENTICAL_OPERATION_FOOTPRINT: %(a)s %(b)s") % {
                    'a': next_a,
                    'b': next_b
                })

            # Terminate if we have found the closure
            if next_a.task.is_batch_closure(group_key):
                return True

            # Recursively call
            return schematic_walk_and_validate(a_ops[0], b_ops[0])

        # Initiate Recursive call
        return schematic_walk_and_validate(self, another_operation)

    def new_forward_scheduling(self, scheduler):
        new_start_date = self.get_latest_end_date_from_parent() + datetime.timedelta(minutes=self.staging_duration)
        if self.planned_start != new_start_date:
            new_date = scheduler.get_start_end_forward(new_start_date,
                                                       new_start_date + datetime.timedelta(minutes=self.get_full_duration()),
                                                       self.task.continue_on_break)
            self.planned_start = new_date.start
            self.planned_end = new_date.end
            return True
        return False

    def get_order_quantity(self):
        """
        :return: production order active_quantity
        """
        self.populate('ref_doc')
        return self.ref_doc.active_quantity

    def set_order_quantity(self, adjustment, user):
        self.populate('ref_doc')
        self.ref_doc.active_quantity -= adjustment
        self.ref_doc.touched(user)

    def get_latest_end_date_from_parent(self):
        self.populate('source')
        if not self.source:
            return None
        return max([s.planned_end for s in self.source])

    def get_children(self):
        self.populate('ref_doc')
        self.ref_doc.populate('operation')

        children = [o for o in self.ref_doc.operation if o.is_parent(self.object_id)]
        return children if children else None

    class Meta:
        collection_name = ':production_operation'
        references = [('production_order', 'ref_doc')]


class ProductionGroupedOperation(ProductionBaseTask):
    STATUS_OPEN = 0
    STATUS_PARTIALLY_CONFIRMED = 1
    STATUS_CONFIRMED = 2
    STATUS_CANCELLED = 3

    GROUP_STATUS = (
        (STATUS_OPEN, _('GROUP_OPERATION_STATUS_OPEN')),
        (STATUS_PARTIALLY_CONFIRMED, _('GROUP_OPERATION_STATUS_PARTIALLY_CONFIRMED')),
        (STATUS_CONFIRMED, _('GROUP_OPERATION_STATUS_CONFIRMED')),
        (STATUS_CANCELLED, _('GROUP_OPERATION_STATUS_CANCELLED')),
    )

    TYPE_PLAN = 0
    TYPE_ACTUAL = 1

    GROUP_TYPE = (
        (TYPE_PLAN, _('GROUP_TYPE_PLAN')),
        (TYPE_ACTUAL, _('GROUP_TYPE_ACTUAL')),
    )

    quantity = doc.FieldNumeric(default=0)
    status = doc.FieldNumeric(default=STATUS_OPEN, choices=GROUP_STATUS)
    source = doc.FieldDoc('operation_group')
    type = doc.FieldNumeric(default=TYPE_PLAN, choices=GROUP_TYPE)

    def invoke_set_status(self, user, _status):
        # Update status per form validation
        status = int(_status)
        if status in [ProductionOrder.STATUS_CANCELLED]:
            self.cancel(user)
        return self

    @classmethod
    def clear_all(cls, user, verbose=None, **kwargs):
        groupable_tasks = [v.code for i, v in Task.tasks.iteritems() if v.batch > 1]
        prods = ProductionOrder.manager.find(0, 0, {'status': {'$lt': ProductionOrder.STATUS_CONFIRMED}})

        operation_query = {'ref_doc': {'$in': [p.object_id for p in prods]},
                           'task': {'$in': groupable_tasks},
                           'status': {'$lt': ProductionOrderOperation.STATUS_PARTIAL_CONFIRMED},
                           'group': {'$ne': None}}
        testing_query = kwargs.pop("testing", None)
        if testing_query and isinstance(testing_query, dict):
            operation_query.update(testing_query)

        ops = ProductionOrderOperation.manager.find(0, 0, operation_query)
        print_verbose(verbose, "Query operation with condition: %s" % operation_query)
        print_verbose(verbose, "Result: %s" % [o.object_id for o in ops])

        # Cancel all existing groups
        existing_groups = []
        for o in ops:
            if o.group:
                o.populate('group')
                if o.group not in existing_groups:
                    existing_groups.append(o.group)
                    if verbose:
                        print("Group: %s found and is cancelled" % o.group.object_id)

        if existing_groups:
            map(lambda x: x.cancel(user, reschedule=True), ops)

    @classmethod
    def automate_group(cls, user, verbose=None, **kwargs):
        """
        1. get production order with status
            - Open
            - Planned
            - Released
        2. get operations within production order
        :return:
        """
        groupable_tasks = [v.code for i, v in Task.tasks.iteritems() if v.batch > 1]
        prods = ProductionOrder.manager.find(0, 0, {'status': {'$lt': ProductionOrder.STATUS_CONFIRMED}})

        operation_query = {'ref_doc': {'$in': [p.object_id for p in prods]},
                           'task': {'$in': groupable_tasks},
                           'status': {'$lt': ProductionOrderOperation.STATUS_PARTIAL_CONFIRMED},
                           'group': None}
        testing_query = kwargs.pop("testing", None)
        if testing_query and isinstance(testing_query, dict):
            operation_query.update(testing_query)

        ops = ProductionOrderOperation.manager.find(0, 0, operation_query)
        print_verbose(verbose, "Query operation with condition: %s" % operation_query)
        print_verbose(verbose, "Result: %s" % ops)

        ops = sorted(ops, key=attrgetter('task'))
        ops = sorted(ops, key=attrgetter('planned_start'))
        grouped = {}
        for o in ops:
            if o.task.code not in grouped:
                grouped[o.task.code] = {}

            if str(o.planned_start.date()) not in grouped[o.task.code]:
                grouped[o.task.code][str(o.planned_start.date())] = []

            grouped[o.task.code][str(o.planned_start.date())].append(o)

        print_verbose(verbose, "Tasks to be processed: %s" % grouped)

        for g in grouped:
            print_verbose(verbose, "Processing task: %s" % str(g))
            for d in grouped[g]:
                print_verbose(verbose, "Processing date: %s" % str(d))
                group_buffer = grouped[g][d]
                while True:
                    print_verbose(verbose, "Round: %s" % group_buffer)
                    results = cls.get_groupable(group_buffer)

                    if results['groupable']:
                        new_group = cls()
                        new_group.task = grouped[g][d][0].task
                        new_group.schedule(user, results['groupable'])

                        group_buffer = results['remaining']
                    else:
                        break

    @staticmethod
    def get_groupable(operations):
        """

        :param operations: list of operation task object_id or ProductionOrderOperation objects
        :return: dictionary {'groupable': list of groupable tasks, 'remaining': list of remaining tasks}
        """
        # NOTE : implement grouping check logic here
        results = {'groupable': [], 'remaining': []}

        # If operations list is empty, return empty result
        if not operations:
            return results

        for op in operations:
            if isinstance(op, ProductionOrderOperation):
                results['groupable'].append(op)
            else:
                results['groupable'].append(ProductionOrderOperation(op))

        # operations task must be batch
        base_task = results['groupable'][0].task
        if base_task.batch < 2:
            print(_("ERROR_TASK_NOT_SUPPORT_BATCH: %(taskcode)s: %(tasklabel)s") % {'taskcode': base_task.code,
                                                                                    'tasklabel': base_task.label})
            results['groupable'] = []
            return results

        # operations must be of the same task
        def result_filter(key, compare_to, method=None):
            for op in results['groupable']:
                key_to_compare = op.__getattribute__(key).__getattribute__(method)() if method else op.__getattribute__(key)
                if key_to_compare == compare_to:
                    buffer_result.append(op)
                else:
                    results['remaining'].append(op)

        buffer_result = []
        result_filter('task', base_task)
        results['groupable'] = buffer_result
        # results['groupable'] = filter(lambda x: x.task == base_task, results['groupable'])
        # results['remaining'] = list(set(results['groupable']).difference(set(results['groupable'])))
        if len(results['groupable']) < 2:
            print(_("ERROR_GROUP_MUST_BE_OF_THE_SAME_TASK"))
            results['groupable'] = []
            return results

        # operations must be started within the same date
        base_start = results['groupable'][0].planned_start
        # operation_objects = filter(lambda x: x.planned_start.date() == base_start.date(), operation_objects)
        buffer_result = []
        result_filter('planned_start', base_start.date(), 'date')
        results['groupable'] = buffer_result
        if len(results['groupable']) < 2:
            print(_("ERROR_GROUP_MUST_BE_IN_THE_SAME_DATE"))
            results['groupable'] = []
            return results

        # operations quantity can't be more than batch quantity in task
        def check_quantity(ops):
            result = []
            quantity = 0
            for op in ops:
                quantity += op.get_order_quantity()
                if quantity <= base_task.batch:
                    result.append(op)
                else:
                    results['remaining'].append(op)
            return result

        results['groupable'] = check_quantity(results['groupable'])
        if len(results['groupable']) < 2:
            print(_("ERROR_FIRST_OP_EXCEED_MAX_BATCH: Max: %(maxbatch)s") % {'maxbatch': base_task.batch})
            results['groupable'] = []
            return results

        return results

    def invoke_set_type(self, user, _type):
        if _type not in [k for k, v in self.GROUP_TYPE]:
            raise ValidationError(_("ERROR_TYPE_DOES_NOT_EXIST"))
        self.type = _type
        self.touched(user)

    def reschedule(self, user):
        # NOTE: if less than 2 operations left, cancel group
        operations = ProductionOrderOperation.manager.find(0, 0, {'group': self.object_id})
        if len(operations) < 2:
            self.cancel(user)
        else:
            return self.schedule(user, operations)

    def schedule(self, user, group_operations):
        latest_start = None
        self.planned_duration = 0
        for op in group_operations:
            op.add_group(user, self, bypass=True)
            self.quantity += op.get_order_quantity()
            # NOTE: Confirmed hardcode the cast task here
            if self.task.code == 5331:
                self.planned_duration = self.planned_duration if self.planned_duration > op.planned_duration else op.planned_duration
            else:
                self.planned_duration += op.planned_duration
            if not latest_start:
                latest_start = op.planned_start
            else:
                latest_start = op.planned_start if op.planned_start > latest_start else latest_start

        # carry out forward scheduling and assign new date
        schedule_start = latest_start - relativedelta(months=3)
        schedule_end = latest_start + relativedelta(months=6)
        scheduler = Scheduler(schedule_start, schedule_end)
        # NOTE: for batch group, it is allow to end in offhour (from Dec 3rd meeting)
        new_schedule = scheduler.get_start_end_forward(latest_start, latest_start + datetime.timedelta(minutes=self.planned_duration), True)
        self.planned_start = new_schedule.start
        self.planned_end = new_schedule.end

        def recursive_forward_scheduling(operation, sch, u):
            children = operation.get_children()
            if not children:
                return None
            for child in children:
                if child.new_forward_scheduling(sch):
                    child.touched(u, bypass=True)
                    if child.group:
                        child.populate('group')
                        child.group.reschedule(user)
                    recursive_forward_scheduling(child, sch, u)

        for op in group_operations:
            if op.planned_start != self.planned_start:
                op.planned_start = self.planned_start
            op.planned_end = self.planned_end
            delta = op.planned_end - (op.planned_start + datetime.timedelta(minutes=op.planned_duration))
            op.waiting_time = int(round((delta.seconds + int(round(delta.microseconds/1000000.0)))/60))
            op.touched(user, bypass=True)
            recursive_forward_scheduling(op, scheduler, user)

        self.touched(user)
        return self

    def invoke_set_operation(self, user, _operations):
        """

        :param user:
        :param _operations: list of object id or string containing list of object id separated by ","
        :return:
        """
        if not _operations:
            raise BadParameterError(_("Operations are required"))

        if isinstance(_operations, basestring):
            operations = _operations.split(",")
        else:
            operations = _operations

        # Get groupable operations object
        group_operations = self.get_groupable(operations)['groupable']

        if not group_operations:
            return None

        self.task = group_operations[0].task

        # Updating existing group, check previously grouped operations and compare change
        if self.last_edited:
            prev_operations = ProductionOrderOperation.manager.find(0, 0, {'group': self.object_id})
            prev_object_id = [o.object_id for o in prev_operations]
            diff = set(prev_object_id).difference(set([g.object_id for g in group_operations]))
            for op in prev_operations:
                if op.object_id in diff:
                    op.remove_group(user, bypass=True)

        return self.schedule(user, group_operations)

    def confirm(self, user, confirmation, **kwargs):
        # TODO : Implement confirmation
        operations = ProductionOrderOperation.manager.find(0, 0, {'group': self.object_id})

        loops = ({'index': x, 'operation': o} for x, o in enumerate(operations))

        map(lambda x: x['operation'].confirm(user, confirmation[x['index']]), loops)

    def cancel(self, user, **kwargs):
        if self.status == self.STATUS_CANCELLED:
            raise ValidationError(_("ERROR_GROUP_IS_ALREADY_CANCELLED"))

        if self.status > self.STATUS_CONFIRMED:
            raise ValidationError(_("ERROR_GROUP_IS_ALREADY_CONFIRMED"))

        reschedule = kwargs.pop("reschedule", None)
        chain = kwargs.pop("chain", None)

        # remove group from operations
        operations = ProductionOrderOperation.manager.find(0, 0, {'group': self.object_id})
        map(lambda x: x.remove_group(user, bypass=True, **kwargs), operations)
        map(lambda x: x.reset_waiting_time(user, bypass=True, **kwargs), operations)

        ref_docs = []

        def add_ref_doc(key):
                if key not in ref_docs:
                    ref_docs.append(ProductionOrder(key))

        # NOTE: chain remove all group in the same operation-group tree
        if chain:
            map(lambda x: add_ref_doc(x.ref_doc[0]), operations)
            map(lambda x: x.invoke_remove_group(user), ref_docs)

        # NOTE: compact and reschedule all the order
        if reschedule > 0:
            if not ref_docs:
                map(lambda x: add_ref_doc(x.ref_doc[0]), operations)
            map(lambda x: x.schedule_order(forward=True, compact=True), ref_docs)
            map(lambda x: x.touched(user), ref_docs)

        # change status to cancel and update group
        self.status = self.STATUS_CANCELLED
        super(ProductionGroupedOperation, self).cancel(user, bypass=True, **kwargs)

    def cancel_confirmation(self, user, index, **kwargs):
        # TODO : Implement cancel confirmation
        pass

    class Meta:
        collection_name = 'operation_group'
        require_permission = True


class TimeRange(object):
    start = None
    end = None

    def __init__(self, start, end):
        self.start = start
        self.end = end

    def overlap(self, ref):
        return True if self.start < ref.end and self.end > ref.start else False

    def diff(self):
        return self.end - self.start


class Scheduler(TimeRange):
    off_hours = []

    def __init__(self, start, end):
        super(Scheduler, self).__init__(start, end)
        self.off_hours = OffHour.OffHoursRange.between(start, end)

    def is_off_hour(self, ref, exclusive):
        if exclusive:
            off_list = [o for o in self.off_hours if o.start < ref < o.end]
        else:
            off_list = [o for o in self.off_hours if o.start < ref <= o.end]

        if off_list:
            return off_list[0]
        else:
            return None

    def get_start_end_forward(self, start, end, allow_off_hour):
        result_range = TimeRange(start, end)
        start_range = self.is_off_hour(start, True)
        if start_range:
            shift = start_range.end - result_range.start
            result_range.start = start_range.end
            result_range.end += shift

        if not allow_off_hour:
            for off_hour in self.off_hours:
                if result_range.overlap(off_hour):
                    shift = off_hour.end - off_hour.start
                    result_range.end += shift

        return result_range

    def get_start_end_backward(self, start, end, allow_off_hour):
        result_range = TimeRange(start, end)
        end_range = self.is_off_hour(end, False)
        if end_range:
            shift = end_range.start - result_range.end
            result_range.end = end_range.start
            result_range.start += shift

        if not allow_off_hour:
            for off_hour in self.off_hours:
                if result_range.overlap(off_hour):
                    shift = off_hour.end - off_hour.start
                    result_range.start -= shift

        return result_range


class ProductionOrder(doc.Authored):
    STATUS_OPEN = 0
    STATUS_PLANNED = 1
    STATUS_RELEASED = 2
    STATUS_CONFIRMED = 3
    STATUS_CLOSED = 4
    STATUS_CANCELLED = 5

    PRODUCTION_ORDER_STATUSES = (
        (STATUS_OPEN, _('PRODUCTION_ORDER_STATUS_OPEN')),
        (STATUS_PLANNED, _('PRODUCTION_ORDER_STATUS_PLANNED')),
        (STATUS_RELEASED, _('PRODUCTION_ORDER_STATUS_RELEASED')),
        (STATUS_CONFIRMED, _('PRODUCTION_ORDER_STATUS_CONFIRMED')),
        (STATUS_CLOSED, _('PRODUCTION_ORDER_STATUS_CLOSED')),
        (STATUS_CANCELLED, _('PRODUCTION_ORDER_STATUS_CANCELLED')),
    )

    TYPE_STANDARD = 0
    TYPE_REWORK = 1

    PRODUCTION_ORDER_TYPES = (
        (TYPE_STANDARD, _('PRODUCTION_ORDER_TYPE_STANDARD')),
        (TYPE_REWORK, _('PRODUCTION_ORDER_TYPE_REWORK')),
    )

    doc_no = doc.FieldString(none=True)     # Running Number
    material = doc.FieldTypedCode(codes.StockCode, none=False)
    revision = doc.FieldNumeric(none=True)
    quantity = doc.FieldNumeric(default=1, none=False)
    active_quantity = doc.FieldNumeric(none=False)
    estimate_yield_quantity = doc.FieldNumeric(default=1, none=False)
    uom = doc.FieldUom(none=False)
    location = doc.FieldString(default=Location.locations['STORE'].code, none=False)
    size = doc.FieldString(none=True)
    status = doc.FieldNumeric(none=False, choices=PRODUCTION_ORDER_STATUSES, default=STATUS_OPEN)
    planned_start = doc.FieldDateTime()
    actual_start = doc.FieldDateTime()
    planned_end = doc.FieldDateTime()
    actual_end = doc.FieldDateTime()
    ref_doc = doc.FieldDoc(SalesOrder, none=True)
    ref_doc_item = doc.FieldNumeric(none=True)
    cancelled = doc.FieldDoc('event', none=True)
    operation = doc.FieldList(doc.FieldDoc(ProductionOrderOperation))
    mrp_session = doc.FieldDoc('mrp-session', none=True)
    original_doc = doc.FieldDoc('production_order', none=True)
    original_doc_item = doc.FieldNumeric(none=True)
    type = doc.FieldNumeric(default=TYPE_STANDARD, choices=PRODUCTION_ORDER_TYPES, none=False)
    remark = doc.FieldString(none=True)

    @classmethod
    def factory(cls, material_code, revision, size, due_date, quantity, user, **kwargs):
        """

        :param codes.StockCode material_code:
        :param int revision:
        :param basestring size:
        :param datetime.datetime due_date:
        :param int quantity:
        :param IntraUser user:
        :param kwargs:
        :return:
        """
        ref_doc = kwargs.pop('ref_doc', None)
        ref_doc_item = kwargs.pop('ref_doc_item', None)
        remark = kwargs.pop('remark', None)
        if ref_doc_item is not None and not isinstance(ref_doc_item, int):
            raise BadParameterError('ref_doc_item must be integer')
        if remark is None and ref_doc is not None and ref_doc_item is not None and remark is None:
            remark = ref_doc.remark

        # Validate if such material code exists
        scrap_percentage = kwargs.pop('scrap_percentage', 0)

        order = cls()
        order.material = material_code
        order.revision = revision
        order.size = size
        order.estimate_yield_quantity = quantity
        order.quantity = round(quantity * (1 + scrap_percentage), 0)
        order.active_quantity = round(quantity * (1 + scrap_percentage), 0)
        order.planned_end = due_date
        order.mrp_session = kwargs.pop('mrp_session_id', None)
        order.read_bom()
        order.mrp_scheduling()
        order.ref_doc = ref_doc
        order.ref_doc_item = ref_doc_item
        order.remark = remark
        order.touched(user, **kwargs)
        return order

    def set_start(self, user, start, **kwargs):
        self.actual_start = start
        self.touched(user, **kwargs)

    def confirm(self, user, actual_end, **kwargs):
        self.status = self.STATUS_CONFIRMED
        self.actual_end = actual_end
        self.touched(user, **kwargs)

    def mrp_scheduling(self, scheduler=None):
        self.schedule_order(scheduler=scheduler)
        if self.planned_start.date() < datetime.datetime.today().date():
            self.planned_start = datetime.datetime.today()
            self.schedule_order(forward=True, scheduler=scheduler)

    def schedule_order(self, forward=None, scheduler=None, compact=None):
        if forward and not self.planned_start:
            raise ValidationError(_("ERROR_PLANNED_START_IS_REQUIRED"))

        if not forward and not self.planned_end:
            raise ValidationError(_("ERROR_PLANNED_END_IS_REQUIRED"))

        self.populate('operation')

        # 1st iteration: calculate offset for every operation
        for operation in self.operation:
            if compact:
                operation.waiting_time = 0
            if operation.source:
                operation.populate('source')
                max_duration = 0
                for s in operation.source:
                    source_operation = self.get_operation(s.object_id)
                    # include staging_duration
                    offset = source_operation.start_time_offset + source_operation.staging_duration + source_operation.get_full_duration()
                    max_duration = max(offset, max_duration)
                operation.start_time_offset = max_duration
            else:
                operation.start_time_offset = 0

        last_longest_operation = None
        leaves = self.get_leaf_operations()

        for l in leaves:
            if not last_longest_operation or (last_longest_operation.start_time_offset +
                                              last_longest_operation.staging_duration +
                                              last_longest_operation.get_full_duration()) < \
                                             (l.start_time_offset +
                                              l.staging_duration +
                                              l.get_full_duration()):
                last_longest_operation = l

        whole_offset = last_longest_operation.start_time_offset + last_longest_operation.staging_duration + last_longest_operation.get_full_duration()
        start_of_today = datetime.datetime.today()
        shift_offset = 0

        # backward scheduling
        if not forward:
            temp_planned_start = self.planned_end - datetime.timedelta(minutes=whole_offset)
            shift_offset = temp_planned_start - start_of_today
        # forward scheduling
        else:
            shift_offset = self.planned_start - start_of_today

        # second iteration, calculate plannedStartDate based on start time or end time of header
        for operation in self.operation:
            operation.planned_start = start_of_today + \
                                      datetime.timedelta(minutes=(operation.start_time_offset + operation.staging_duration)) + \
                                      shift_offset
            operation.planned_end = operation.planned_start + datetime.timedelta(minutes=(operation.get_full_duration()))
            del operation.start_time_offset

        if not scheduler:
            ref_time = self.planned_start or self.planned_end
            schedule_start = ref_time - relativedelta(months=3)
            schedule_end = ref_time + relativedelta(months=6)
            scheduler = Scheduler(schedule_start, schedule_end)

        # third iteration, adjust tree with off hours
        # backward scheduling
        if not forward:
            self.backward_scheduling(scheduler)
            new_start = self.get_min_start()
            sources = self.get_source_operations()
            for s in sources:
                s.planned_start = new_start
            self.forward_scheduling(scheduler)
        # forward scheduling
        else:
            self.forward_scheduling(scheduler)

        # update production order planned start and end date from operation data
        self.update_planned_date_from_operation()

    def backward_scheduling(self, scheduler):
        for operation in self.operation[::-1]:
            children = operation.get_children()
            if children:
                min_start_date = None
                for c in children:
                    children_operation = self.get_operation(c.object_id)
                    temp_start = children_operation.planned_start - datetime.timedelta(minutes=children_operation.staging_duration)
                    staging_range = scheduler.get_start_end_backward(temp_start, children_operation.planned_start, False)
                    if not min_start_date or staging_range.start < min_start_date:
                        min_start_date = staging_range.start
                operation.planned_start = min_start_date - datetime.timedelta(minutes=operation.get_full_duration())

            temp_end = operation.planned_start + datetime.timedelta(minutes=operation.get_full_duration())
            new_range = scheduler.get_start_end_backward(operation.planned_start, temp_end, operation.task.continue_on_break)
            operation.planned_start = new_range.start
            operation.planned_end = new_range.end

    def forward_scheduling(self, scheduler):
        self.populate('operation')
        for operation in self.operation:
            if operation.source:
                operation.populate('source')
                max_end_date = None
                for s in operation.source:
                    source_operation = self.get_operation(s.object_id)
                    if not max_end_date or max_end_date < source_operation.planned_end:
                        max_end_date = source_operation.planned_end
                operation.planned_start = max_end_date + datetime.timedelta(minutes=operation.staging_duration)

            # check if staging time range is in offhour
            staging_range = scheduler.get_start_end_forward(operation.planned_start - datetime.timedelta(minutes=operation.staging_duration),
                                                            operation.planned_start, False)
            temp_start = staging_range.end
            temp_end = temp_start + datetime.timedelta(minutes=operation.get_full_duration())
            new_range = scheduler.get_start_end_forward(temp_start, temp_end, operation.task.continue_on_break)
            operation.planned_start = new_range.start
            operation.planned_end = new_range.end

    def supply_quantity(self):
        return min(self.active_quantity, self.estimate_yield_quantity)

    def read_bom(self):
        self.validate()

        if self.status > self.STATUS_OPEN:
            raise ValidationError(_("ERROR_ONLY_OPEN_ORDER_CAN_REREAD_BOM"))

        material = MaterialMaster.factory(self.material)
        schematic = filter(lambda r: self.revision == r.rev_id, material.revisions())[0]
        size_index = 0
        if self.size:
            size_index = [index for index, content in enumerate(schematic.conf_size) if content == self.size][0]

        self.operation = []
        for sch in schematic.schematic:
            operation = ProductionOrderOperation.factory(sch, self.quantity, size_index if sch.is_configurable else 0)
            if operation:
                self.operation.append(operation)

        # NOTE: translate source from schematic to operation reference
        def map_destination(parent, destination):
            if len(parent.destination) > 0:
                parent.destination.append(destination)
            else:
                parent.destination = [destination]

        def assign_source_destination(op):
            op.ref_doc = self
            if op.id:
                source = filter(lambda y: y.id == op.id, schematic.schematic)[0].source
                if source:
                    op.source = [o for o in self.operation if o.id in source]
                    map(lambda x: map_destination(x, op), op.source)

        map(assign_source_destination, self.operation)

    def update_planned_date_from_operation(self):
        self.populate('operation')
        self.planned_start = min([o.planned_start for o in self.operation])
        self.planned_end = max([o.planned_end for o in self.operation])

    def get_operation(self, object_id):
        result = [o for o in self.operation if o.object_id == object_id]
        return result[0] if result else None

    def get_active_operation(self):
        self.populate('operation')
        for o in self.operation:
            if o.status < ProductionOrderOperation.STATUS_PARTIAL_CONFIRMED:
                return o

    def get_min_start(self):
        self.populate('operation')
        operation_start = [o.planned_start for o in self.operation if o.planned_start is not None]
        return min(operation_start) if operation_start else None

    def get_max_end(self):
        self.populate('operation')
        operation_end = [o.planned_end for o in self.operation if o.planned_end is not None]
        return max(operation_end) if operation_end else None

    def get_last_operation(self):
        self.populate('operation')
        return self.operation[-1]

    def get_first_operation(self):
        self.populate('operation')
        return self.operation[0]

    def get_source_operations(self):
        self.populate('operation')
        operation_without_source = [o for o in self.operation if not o.source]
        return operation_without_source if operation_without_source else None

    def get_leaf_operations(self):
        self.populate('operation')
        leaf_operations = filter(lambda x: x.get_children() is None, self.operation)
        return leaf_operations if leaf_operations else None

    def get_edge_operations(self):
        """

        :return: [ProductionOrderOperation] - all operations that are confirmable, and not yet confirmed.
        """
        self.populate('operation')
        return filter(lambda x: x.status < ProductionOrderOperation.STATUS_CONFIRMED and x.get_confirmable_quantity() > 0, self.operation)

    def cancel(self, user, **kwargs):
        if self.status == self.STATUS_CANCELLED:
            raise ValidationError(_("ERROR_ORDER_IS_ALREADY_CANCELLED"))

        if self.status >= self.STATUS_CONFIRMED:
            raise ValidationError(_("ERROR_UNABLE_TO_CANCEL_ORDER_CONFIRMED"))

        self.populate('operation')
        for operation in self.operation:
            operation.cancel(user, bypass=True, **kwargs)

        self.status = self.STATUS_CANCELLED
        self.cancelled = doc.Event.create(doc.Event.CANCELLED, user, against=self)
        self.touched(user, **kwargs)

    def validate(self):
        material = MaterialMaster.factory(self.material)

        if str(material.procurement_type) != 'I':
            raise ValidationError(_("ERROR_PROCUREMENT_TYPE: %(material)s procurement type has to be I but it is %(procurementtype)s") % {'material': self.material.code, 'procurementtype': material.procurement_type})

        if not material.schematic:
            raise ValidationError(_("ERROR_NO_SCHEMATIC: %(material)s does not have schematic") % {'material': self.material.code})

        if not self.uom:
            self.uom = material.uom

        if self.uom != material.uom:
            raise ValidationError(_("ERROR_UOM_DOES_NOT_MATCH: %(material)s based UoM is %(uom)s") % {'material': self.material.code, 'uom': material.uom})

        if not self.active_quantity:
            self.active_quantity = self.quantity

        revisions = material.revisions()
        if revisions:
            revision_list = [rev.rev_id for rev in revisions]
            if self.revision is None:
                pass
            if self.revision not in revision_list:
                raise ValidationError(_("ERROR_REVISION_DOES_NOT_EXIST: revision %(material)s only has revision %(revisionlist)s request revision=%(rev)s") % {'material': self.material.code, 'revisionlist': revision_list, 'rev': self.revision})

            schematic = filter(lambda r: self.revision == r.rev_id, revisions)[0]
            if self.size and self.size not in schematic.conf_size:
                raise ValidationError(_("ERROR_SIZE_DOES_NOT_EXIST: %(material)s revision %(materialrevision)s only has size %(sizelist)s") % {'material': self.material.code, 'materialrevision': schematic.rev_id, 'sizelist': schematic.conf_size})

    def touched(self, user, **kwargs):
        # Check permission
        if not kwargs.pop("automated", False):
            self.assert_permission(user, self.PERM_W)

        self.populate('operation')
        for op in self.operation:
            op.ref_doc = self
            op.touched(user, bypass=True, **kwargs)

        super(ProductionOrder, self).touched(user, **kwargs)

    def invoke_set_status(self, user, _status):
        # Update status per form validation
        status = int(_status)
        if status in [ProductionOrder.STATUS_RELEASED]:
            self.release(user)
        elif status in [ProductionOrder.STATUS_CONFIRMED]:
            self.confirm(user)
        elif status in [ProductionOrder.STATUS_CANCELLED]:
            self.cancel(user)

        return self

    def invoke_remove_group(self, user, reschedule=None):
        """

        :param user:
        :param detach:
        :return:
        """

        if not isinstance(reschedule, int) and reschedule:
            reschedule = int(reschedule)
        self.populate('operation')
        operations = [o for o in self.operation if o.group]
        if not operations:
            return None

        grouped = []

        def add_group(key):
            if key not in grouped:
                grouped.append(key)

        map(lambda x: add_group(x.group), operations)
        map(lambda x: ProductionGroupedOperation(x).cancel(user, chain=True, reschedule=reschedule), grouped)
        map(lambda x: x.remove_group(user, bypass=True), operations)
        map(lambda x: x.reset_waiting_time(user, bypass=True), operations)
        if reschedule > 0:
            self.schedule_order(forward=True, compact=True)

        return self

    def release(self, user, **kwargs):
        # Check permission
        if not kwargs.pop("automated", False):
            self.assert_permission(user, self.PERM_W)

        # TODO : change prod order, operation status, gen task for staging, costing
        if self.status >= self.STATUS_RELEASED:
            raise ValidationError(_("ERROR_PROD_ALREADY_RELEASED:"))

        def check_release(o):
            if not isinstance(o.assignee, IntraUser):
                raise ValidationError(_("ERROR_OPERATION_NOT_ASSIGNED"))

        self.populate('operation')
        map(check_release, self.operation)
        map(lambda x: x.release(user, bypass=True, **kwargs), self.operation)

        self.status = self.STATUS_RELEASED
        self.touched(user, **kwargs)

    def pending_tasks(self, filter_callback):
        """
        Check all unconfirmed task, see if any of them is ready

        :param filter_callback: callable to filter out the tasks.
        :return:
        """
        tasks = ProductionOrderOperation.manager.find(cond={
            'status': {'$lt': ProductionOrderOperation.STATUS_CONFIRMED},
            'ref_doc.0': self.object_id,
            'ref_doc.1': 'production_order'
        })
        return filter(lambda task: filter_callback(task), tasks)

    def material_master(self):
        """

        :return: MaterialMaster associated to this ProductionOrder
        """
        if self.material is None:
            return None
        return MaterialMaster.of('code', str(self.material))

    def design(self):
        """

        :return: Design associated to this ProductionOrder
        """
        mm = self.material_master()
        if mm is None:
            return None
        schematic = mm.revision(self.revision)
        if schematic is None:
            return None
        schematic.populate('source')
        return schematic.source

    def save(self):
        if not self.doc_no:
            self.doc_no = doc.RunningNumberCenter.new_number(PRODUCTION_ORDER_NUMBER_KEY)

        super(ProductionOrder, self).save()

    class Meta:
        collection_name = 'production_order'
        require_permission = True
        permission_write = ['cancel']
        doc_no_prefix = PRODUCTION_ORDER_NUMBER_PREFIX

# Register the running number policy.
doc.RunningNumberCenter.register_policy(PRODUCTION_ORDER_NUMBER_KEY, doc.DailyRunningNumberPolicy(PRODUCTION_ORDER_NUMBER_PREFIX))


class ProductionProposal(doc.Authored):
    data = doc.FieldSpec(dict)
    start = doc.FieldDateTime()

    @classmethod
    def get(cls):
        plans = ProductionProposal.manager.find(pagesize=1, cond={
            '$sort': '-start'
        })
        return None if len(plans) == 0 else plans[0]

    class Meta:
        collection_name = 'proposal'
        require_permission = True
        permission_write = ['approve']
        indices = [
            ([("start", 1)], {"expireAfterSeconds": 0})
        ]


class UserActiveTask(doc.Authored, JsonSerializable):
    user = doc.FieldIntraUser()
    operation = doc.FieldDoc('task')
    durations = doc.FieldList(doc.FieldDateTime())

    def pause(self):
        if len(self.durations) % 2 == 0:
            raise ValidationError("Operation is already paused")
        # pause is allowed
        self.durations.append(utils.NOW())

    def resume(self):
        if len(self.durations) % 2 == 1:
            raise ValidationError("Operation is already active")
        self.durations.append(utils.NOW())

    def stop(self, author, **details):
        """
        Create Confirmation as per requested by stop operation

        :return production_operation object
        """
        self.populate('operation')

        # Enclose the duration
        if len(self.durations) % 2 == 1:
            self.durations.append(utils.NOW())

        # Initialize default values
        details['actual_start'] = details.pop('actual_start', self.durations[0])
        details['actual_end'] = details.pop('actual_end', self.durations[-1])
        details['actual_duration'] = details.pop('actual_duration', math.floor(self.elapsed() / 60))
        details['assignee'] = details.pop('assignee', self.user)
        details['durations'] = self.durations

        # Create designated confirmation
        confirmation_class = self.operation.confirmation_class()
        try:
            confirmation = confirmation_class.create(**details)
        except KeyError as e:
            raise BadParameterError(_('ERR_CANNOT_CREATE_CONFIRMATION: %(confirmation_class)s#create() %(key_error)s') % {
                'confirmation_class': confirmation_class,
                'key_error': e
            })
        except TypeError as e:
            raise BadParameterError(_('ERR_CANNOT_CREATE_CONFIRMATION: %(confirmation_class)s#create() %(error)s %(details)s') % {
                'confirmation_class': confirmation_class,
                'error': e,
                'details': details
            })

        self.operation.confirm(author, confirmation)
        return confirmation

    def elapsed(self):
        """
        :return total duration elapsed in seconds
        """
        durations = self.durations
        if len(durations) % 2 == 1:
            durations.append(utils.NOW())

        total = 0
        for i in range(0, len(durations), 2):
            delta = durations[i+1] - durations[i]
            total += delta.seconds
        return total

    @classmethod
    def probe_all(cls, operations=[]):
        return cls.manager.find(cond={
            'operation': {'$in': map(lambda a: a.object_id, operations)}
        })

    @classmethod
    def probe(cls, user=None, operation=None):
        cond = {}

        if user is not None:
            cond['user'] = doc._objectid(user.id)
        if operation is not None:
            cond['operation'] = operation.object_id

        o = cls.manager.find(cond=cond)
        if len(o) > 0:
            return o[0]
        return None

    @classmethod
    def start(cls, assignee, operation, author, **kwargs):
        """
        Start given operation with an assignee.

        Support flags
        * skip_assignee_check
        * allow_restart (supported for operation = AuxiliaryTask)

        :raises ValidationError:
        :param IntraUser assignee:
        :param ProductionOrderOperation operation:
        :param IntraUser author:
        :param kwargs:
        :return: UserActiveTask
        """
        flag_skip_assignee_check = kwargs.pop('skip_assignee_check', True)
        flag_allow_restart = kwargs.pop('allow_restart', False)

        if not isinstance(assignee, IntraUser):
            raise ValidationError(_("ERR_INVALID_DATA_TYPE: %(type)s") % {'type': 'IntraUser'})

        # Try probe it first
        activity = cls.probe(operation=operation)

        # Validate if operation is not being carried out by others
        if not flag_allow_restart and activity is not None:
            raise ValidationError(_("ERR_OPERATION_IN_PROGRESS: %(operation)s") % {'operation': operation})

        # At this point, if we don't have activity create a new one
        if activity is None:
            activity = UserActiveTask()

        # Check if active_task is ready for claiming
        if isinstance(operation, ProductionOrderOperation):
            if flag_allow_restart:
                raise ValidationError(_("ERR_FLAG_ALLOW_RESTART_IS_NOT_SUPPORTED"))
            previous_op_count = len(operation.previous_op())
            if operation.get_confirmable_quantity() <= 0 or (previous_op_count == 0 and operation.status is not ProductionOrderOperation.STATUS_RELEASED) or (previous_op_count > 0 and operation.status is not ProductionOrderOperation.STATUS_READY):
                raise ValidationError(_("ERR_OPERATION_IS_NOT_READY_TO_START: %(operation)s %(status)s") % {
                    'operation': operation,
                    'status': operation.status
                })

        # Override assignee of operation if not met.
        need_assign = False
        if isinstance(operation.assignee, IntraUser):
            if not assignee.is_same_user(operation.assignee):
                if not flag_skip_assignee_check:
                    if author.can("task@write+%s" % TASK_PERM_OVERRIDE_ASSIGNEE, throw="challenge"):
                        need_assign = True
                    else:
                        raise ValidationError(_("ERR_UNMATCHED_ASSIGNEE"))
                else:
                    need_assign = True
        elif isinstance(operation.assignee, TaskGroup):
            need_assign = True

        if need_assign:
            # Check if assignee applicable
            operation.assert_assignee(assignee)
            operation.assignee = assignee
            operation.touched(author)

        # (Re) assign activity
        activity.operation = operation
        activity.user = assignee
        activity.durations = [utils.NOW()]
        activity.touched(author)
        return activity

    def as_json(self):
        return {
            'user': self.user.code,
            'operation': self.operation if isinstance(self.operation, ObjectId) else self.operation.object_id,
            'duration': self.durations
        }

    class Meta:
        collection_name = 'user_active_task'
        require_permission = False
        indices = [
            ([("operation", 1)], {"unique": 1})
        ]


class MaterialStagingForm(doc.Authored, JsonSerializable):
    """
    Holding collection of ClerkAuxiliaryTask
    """
    doc_no = doc.FieldString(none=True)
    tasks = doc.FieldList(doc.FieldDoc(ClerkAuxTask))

    def as_json(self):
        self.populate('tasks')

        def processor(a):
            operation = ProductionOrderOperation(a.parent_task)
            order = ProductionOrder(operation.ref_doc[0])
            return {
                '_id': str(a.object_id),
                'assignee': str(a.assignee),
                'task': a.task.code,
                'planned_duration': a.planned_duration,
                'actual_duration': a.actual_duration,
                'ref_doc': [str(a.ref_doc[0]), a.ref_doc[1]],
                'ref_doc_no': a.store_task().doc_no,
                'parent_task_code': operation.task.code,
                'production_doc_no': order.doc_no,
                'status': a.status,
                'materials': map(lambda b: {
                    'material': str(b.material),
                    'quantity': b.quantity,
                    'uom': str(b.uom),
                    'revision': b.revision,
                    'size': b.size
                }, a.list_components())     # replace a.materials with a.list_components() instead.
            }

        return {
            '_id': str(self.object_id),
            'doc_no': self.doc_no,
            'tasks': map(processor, self.tasks)
        }

    @classmethod
    def factory(cls, parent_task_ids):
        """

        :param parent_task_ids: array of parent_task_ids (ObjectId)
        :return: MaterialStagingForm, None if failed to extract any AuxiliaryTask from parent_tasks
        """
        o = cls()
        o.tasks = map(lambda a: a['_id'], ClerkAuxTask.manager.project(cond={
            'parent_task': {'$in': map(doc._objectid, parent_task_ids)},
            'status': ClerkAuxTask.STATUS_OPEN
        }, project=['_id']))
        if len(o.tasks) > 0:
            return o
        return None

    def save(self):
        if not self.doc_no:
            self.doc_no = doc.RunningNumberCenter.new_number(STAGING_FORM_NUMBER_KEY)

        super(MaterialStagingForm, self).save()

    class Meta:
        collection_name = 'material_staging_form'
        doc_no_prefix = STAGING_FORM_NUMBER_PREFIX

# Register the running number policy.
doc.RunningNumberCenter.register_policy(STAGING_FORM_NUMBER_KEY,
                                        doc.DailyRunningNumberPolicy(prefix=STAGING_FORM_NUMBER_PREFIX, digits=3))


@receiver(common_signals.doc_touched, sender=MaterialStagingForm)
def start_clerk_aux_tasks(sender, **kwargs):
    """
    Start all auxiliary clerk task upon MaterialStagingForm first touched (create)

    :param sender:
    :param kwargs:
    :return:
    """
    instance = kwargs.pop('instance', None)
    is_new = kwargs.pop('is_new', False)
    if not (instance and is_new):
        return
    instance.populate('tasks')
    for t in instance.tasks:
        UserActiveTask.start(assignee=instance.created_by,
                             operation=t,
                             author=instance.created_by,
                             skip_assignee_check=True,
                             allow_restart=True)


@receiver(task_signals.task_confirmed, sender=ProductionOrderOperation)
def create_movement_upon_operation_confirmation(sender, instance, code, confirmation, **kwargs):
    # TODO: Calculate and post Movements
    contents = []

    def populate_content(m):
        if m.quantity < 0:
            i = InventoryMovementEntry.factory(m.material,
                                               m.quantity,
                                               location=Location.factory('STAGING').code,
                                               ref_doc=instance,
                                               value=m.value,
                                               weight=m.weight,
                                               batch=m.batch)
        else:
            i = InventoryMovementEntry.factory(m.material,
                                               m.quantity,
                                               location=Location.factory('STAGING').code,
                                               ref_doc=instance,
                                               value=m.value,
                                               weight=m.weight)
        contents.append(i)

    map(populate_content, confirmation.materials)

    # TODO: Extract consumptions from Confirmation
    # Process consumption object
    # => Extract positive quantity - GR Production Order
    positive_items = [m for m in contents if m.quantity > 0]
    pending = []
    if len(positive_items) > 0:
        gr = InventoryMovement.factory(InventoryMovement.GR_BP, positive_items, instance)
        gr.created_by = confirmation.created_by
        gr.validate()
        pending.append(gr)

    # => Extract negative quantity - GI Production Order
    negative_items = [m for m in contents if m.quantity < 0]
    if len(negative_items) > 0:
        gi = InventoryMovement.factory(InventoryMovement.GI_PD, negative_items, instance)
        gi.created_by = confirmation.created_by
        gi.validate()
        pending.append(gi)

    for p in pending:
        p.touched(confirmation.created_by)
        instance.confirmations[-1].movement.append(p)

    if len(pending) > 0:
        instance.touched(confirmation.created_by)
