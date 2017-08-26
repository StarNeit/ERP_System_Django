from intramanee.common import documents as doc, task
from intramanee.common.errors import BadParameterError, ValidationError
from django.utils.translation import ugettext as _
from intramanee.common.task import TaskGroup, Task
from intramanee.common import utils, codes, room, decorators
from intramanee.common.models import IntraUser
from intramanee.common.location import Location
from intramanee.stock.documents import MaterialMaster, InventoryMovement, InventoryMovementEntry, MOVEMENT_LOV_KEY
from django.dispatch import receiver
import signals
from itertools import chain
from intramanee.common.codes.models import LOV

TASK_NUMBER_KEY = 'TASK_NUMBER'
TASK_NUMBER_PREFIX = 'T'
TASK_PERM_OVERRIDE_ASSIGNEE = 'override_assignee'


class Confirmation(doc.FieldSpecAware):
    # assign from frontend
    actual_start = doc.FieldDateTime(none=True)     # datetime
    actual_duration = doc.FieldNumeric(none=True)   # seconds
    actual_end = doc.FieldDateTime(none=True)       # datetime
    assignee = doc.FieldAssignee()                  # user_code, object_id, group_code

    # automatically injected
    created_by = doc.FieldIntraUser()
    created_on = doc.FieldDateTime()
    cancelled = doc.FieldDoc('event', none=True)

    def cancel(self, cancelled_by, **kwargs):
        self.cancelled = doc.Event.create(doc.Event.CANCELLED, cancelled_by, **kwargs)

    def is_cancelled(self):
        return self.cancelled is not None

    @classmethod
    def create(cls, actual_start, actual_end, actual_duration, assignee, **kwargs):
        """
        A convenient method to convert **details from AJAX to python confirm object.

        :param actual_start:
        :param actual_end:
        :param actual_duration:
        :param assignee:
        :return:
        """
        o = cls()
        o.actual_start = actual_start
        o.actual_end = actual_end
        o.actual_duration = actual_duration
        o.assignee = assignee
        o.created_by = kwargs.pop('created_by', assignee)
        o.created_on = kwargs.pop('created_on', utils.NOW())
        return o

    # TODO: Confirm if Task will be confirmed by the responsible person


class TaskDoc(doc.Authored):
    task = doc.FieldTask(none=False)
    """:type : Task"""
    planned_duration = doc.FieldNumeric(none=True)      # save in minutes
    actual_start = doc.FieldDateTime(none=True)
    actual_duration = doc.FieldNumeric(none=True, default=0)
    actual_end = doc.FieldDateTime(none=True)
    assignee = doc.FieldAssignee()
    confirmations = doc.FieldList(doc.FieldNested(Confirmation))
    ref_doc = doc.FieldAnyDoc()
    cancelled = doc.FieldDoc('event')
    details = doc.FieldSpec(dict, none=True)
    doc_no = doc.FieldString(none=True)

    def validate(self):
        if not self.task:
            raise ValidationError(_("ERROR_TASK_IS_REQUIRED"))

        if self.assignee is None:
            self.assignee = self.task.default_assignee()

    def assert_assignee(self, assignee):
        """
        Validate if assignee as IntraUser is applicable for the task.

        :param assignee:
        :return:
        """
        if isinstance(assignee, IntraUser):
            if not assignee.can("write", self.task.code):
                raise ValidationError(_("ERR_INVALID_ASSIGNEE: %(user)s %(task_code)s") % {
                    'user': self.assignee,
                    'task_code': self.task.code
                })
        elif isinstance(assignee, TaskGroup):
            if self.task.default_assignee() is not self.assignee:
                raise ValidationError(_("ERR_INVALID_ASSIGNEE: %(group)s %(task_code)s") % {
                    'task_code': self.task.code,
                    'group': self.assignee
                })

    def cancel_confirmation(self, user, index, **kwargs):
        self.confirmations[index].cancelled = doc.Event.create(doc.Event.CANCELLED, user)

        self.touched(user, **kwargs)

    def cancel(self, user, **kwargs):
        if self.cancelled:
            raise ValidationError(_("ERROR_TASK_IS_ALREADY_CANCELLED"))

        self.cancelled = doc.Event.create(doc.Event.CANCELLED, user, against=self)

        self.touched(user, **kwargs)

    @classmethod
    def confirmation_class(cls):
        return Confirmation

    def confirm(self, user, confirmation, **kwargs):
        if not isinstance(confirmation, Confirmation):
            raise BadParameterError(_("ERROR_CONFIRMATION_MUST_BE_INSTANCE_OF_CONFIRMATION"))

        # for first confirmation, init array. otherwise, append it
        if len(self.confirmations) > 0:
            self.confirmations.append(confirmation)
        else:
            self.confirmations = [confirmation]

        # dispatch event
        signals.task_confirmed.send(self.__class__,
                                    instance=self,
                                    code=str(task.code),
                                    confirmation=confirmation)
        self.touched(user, **kwargs)

    def touched(self, user, **kwargs):
        bypass = kwargs.pop("bypass", None)
        if not kwargs.pop("automated", False) and not bypass:
            self.assert_permission(user, self.PERM_W, self.task.code)
        super(TaskDoc, self).touched(user, **kwargs)

    def save(self):
        if not self.doc_no:
            self.doc_no = doc.RunningNumberCenter.new_number(TASK_NUMBER_KEY)

        super(TaskDoc, self).save()

    class Meta:
        collection_name = 'task'
        require_permission = True
        permission_write = task.Task.get_task_list() + [TASK_PERM_OVERRIDE_ASSIGNEE]
        doc_no_prefix = TASK_NUMBER_PREFIX

# Register the running number policy.
doc.RunningNumberCenter.register_policy(TASK_NUMBER_KEY, doc.DailyRunningNumberPolicy(prefix=TASK_NUMBER_PREFIX, digits=5))


class TaskComponent(doc.FieldSpecAware, decorators.JsonSerializable):
    # assign from front end
    material = doc.FieldTypedCode(codes.StockCode)  # TypedCode
    quantity = doc.FieldNumeric(default=1, none=False)
    uom = doc.FieldUom(none=False)
    revision = doc.FieldNumeric(none=True)
    size = doc.FieldString(none=True)

    @classmethod
    def factory(cls, material, revision, size, quantity, uom=None, **kwargs):
        c = cls()
        c.material = material
        c.revision = revision
        c.size = size
        c.quantity = quantity
        c.uom = uom if uom is not None else MaterialMaster.get(material).uom
        return c

    def as_json(self):
        return {
            'material': str(self.material),
            'quantity': self.quantity,
            'uom': self.uom,
            'revision': self.revision,
            'size': self.size
        }

    def material_key(self):
        return "%sr%s-%s" % (self.material, self.revision, self.size)

    def __repr__(self):
        return "TaskComponent material_key=[%s]" % self.material_key()


class AuxiliaryTaskComponent(TaskComponent):
    weight = doc.FieldNumeric(default=None)

    @classmethod
    def factory(cls, material, revision, size, quantity, uom=None, weight=None, **kwargs):
        c = super(AuxiliaryTaskComponent, cls).factory(material, revision, size, quantity, uom, **kwargs)
        c.weight = weight
        return c

    def as_json(self):
        json = super(AuxiliaryTaskComponent, self).as_json()
        json['weight'] = self.weight
        return json

    @classmethod
    def transmute(cls, input_component):
        if not isinstance(input_component, TaskComponent):
            raise BadParameterError(_("ERR_CANNOT_TRANSUMTE: %(input_class)s to %(output_class)s") % {
                'input_class': type(input_component),
                'output_class': cls
            })
        return cls.factory(material=input_component.material,
                           revision=input_component.revision,
                           size=input_component.size,
                           quantity=input_component.quantity,
                           uom=input_component.uom,
                           weight=None)


class AuxiliaryTaskConfirmation(Confirmation):
    completed = doc.FieldBoolean(default=True, transient=True)
    materials = doc.FieldList(doc.FieldNested(AuxiliaryTaskComponent))

    @classmethod
    def create(cls, materials, **kwargs):
        o = super(AuxiliaryTaskConfirmation, cls).create(**kwargs)
        o.completed = kwargs.pop('completed', True)

        # FIXME: Translate given materials to TaskComponent
        def define_material(m):
            if 'weight' not in m:
                m['weight'] = None

            if 'uom' not in m:
                m['uom'] = None

            component = AuxiliaryTaskComponent.factory(m['material'], m['revision'], m['size'],
                                                       m['quantity'], uom=m['uom'], weight=m['weight'])
            if len(o.materials) > 0:
                o.materials.append(component)
            else:
                o.materials = [component]

        map(define_material, materials)
        return o


class AuxiliaryTask(TaskDoc):
    STATUS_OPEN = 0
    STATUS_CONFIRMED = 1
    STATUSES = (
        (STATUS_OPEN, _("STATUS_OPEN")),
        (STATUS_CONFIRMED, _("STATUS_CONFIRMED"))
    )
    status = doc.FieldNumeric(default=STATUS_OPEN, choices=STATUSES)
    parent_task = doc.FieldDoc('task', none=False)
    """:type TaskDoc"""
    materials = doc.FieldList(doc.FieldNested(AuxiliaryTaskComponent))
    confirmations = doc.FieldList(doc.FieldNested(AuxiliaryTaskConfirmation))

    def invoke_set_status(self, user, _status, **kwargs):
        # Update status per form validation
        status = int(_status)
        if status in [self.STATUS_CONFIRMED]:
            self.confirm(user, **kwargs)
        return self

    def get_parent_task(self):
        """

        :return TaskDoc: parent task
        """
        self.populate('parent_task')
        return self.parent_task

    def list_components(self):
        """

        :return [AuxiliaryTaskComponent]:
        """
        valid_confirmations = filter(lambda c: not c.cancelled, self.confirmations)
        if len(valid_confirmations) > 0:
            return list(chain.from_iterable(v.materials for v in valid_confirmations))
        return self.materials

    @classmethod
    def factory(cls, parent_task, components=None):
        target_task, duration, assignee = cls.default_parameters(parent_task)
        if target_task is None:
            return None

        if components:
            if not isinstance(components, list) or not reduce(lambda x, y: isinstance(x, dict) and isinstance(y, dict), components):
                raise BadParameterError("Component should be list of dict")

            components = map(lambda a: AuxiliaryTaskComponent.factory(material=a['material'],
                                                                      revision=a['revision'],
                                                                      size=a['size'],
                                                                      quantity=a['quantity'],
                                                                      uom=a['uom'],
                                                                      weight=a['weight']), components)
        else:
            components = filter(lambda a: a.quantity > 0, parent_task.materials[:])
            components = map(AuxiliaryTaskComponent.transmute, components)

        t = cls()
        t.status = cls.STATUS_OPEN
        t.task = target_task
        t.parent_task = parent_task
        t.planned_duration = duration
        t.assignee = assignee
        t.materials = components
        if len(t.materials) <= 0:
            return None
        return t

    @classmethod
    def default_parameters(cls, parent_task):
        """
        Retrieve auxiliary task_code to be created for specific parent_task document

        :param parent_task:
        :return task.Task: None if such parent_task does not required any aux_task
        """
        return None, parent_task.staging_duration, IntraUser.robot()

    def find_material(self, material):
        return next((sm for sm in self.materials if sm.material == material.material and
                     sm.size == material.size and
                     sm.revision == material.revision), None)

    @classmethod
    def confirmation_class(cls):
        return AuxiliaryTaskConfirmation

    def confirm(self, user, confirmation, **kwargs):
        """

        :param IntraUser user:
        :param AuxiliaryTaskConfirmation confirmation:
        :param dict kwargs: materials
        :return:
        """
        if self.status >= self.STATUS_CONFIRMED:
            raise ValidationError(_("ERROR_TASK_STATUS_CANT_CONFIRM: %(status)s") % {'status': self.status})

        if not confirmation:
            raise ValidationError(_("ERROR_CONFIRMATION_IS_REQUIRED"))

        if not isinstance(confirmation, AuxiliaryTaskConfirmation):
            raise ValidationError(_("ERROR_CONFIRMATION_MUST_BE_AUX_TASK_CONFIRMATION"))

        if not confirmation.materials:
            raise ValidationError(_("ERROR_MATERIAL_IS_REQUIRED"))

        if not self.confirmations:
            self.actual_start = confirmation.actual_start

        self.actual_duration += confirmation.actual_duration

        # if confirmation is marked completed, set status to confirmed
        if confirmation.completed:
            self.actual_end = confirmation.actual_end
            self.status = self.STATUS_CONFIRMED

        super(AuxiliaryTask, self).confirm(user, confirmation, **kwargs)


class ClerkAuxTask(AuxiliaryTask):
    """
    A Paired task for *Clerk* vs *Store*
    """
    @classmethod
    def default_parameters(cls, parent_task):
        r = room.Room.task_room(parent_task.task.code)

        if r is None:
            return None, parent_task.staging_duration, IntraUser.robot()
        t = task.Task.factory(r.code)
        return t, parent_task.staging_duration, t.default_assignee()

    def store_task(self):
        """

        :return StoreAuxTask: store task
        """
        self.populate('ref_doc')
        if isinstance(self.ref_doc, StoreAuxTask):
            # Save it from re-populate itself
            self.ref_doc.ref_doc = self
            return self.ref_doc
        raise ValueError(_("ERR_INVALID_DATA_STATE: %(reason)s") % {
            'reason': 'clerk_aux_task ref_doc is not store_aux_task'
        })

    def list_components(self):
        """
        Override the parent method so that on default case, store_task will be used as main source of output.

        :return:
        """
        valid_confirmations = filter(lambda c: not c.cancelled, self.confirmations)
        if len(valid_confirmations) > 0:
            return chain.from_iterable(v.materials for v in valid_confirmations)
        return self.store_task().list_components()

    def confirm(self, user, confirmation, **kwargs):
        # TODO: confirm by getting materials from StoreAuxTask

        super(ClerkAuxTask, self).confirm(user, confirmation)

        # NOTE: if clerk task is fulfilled, update store task to delivered
        if self.status == self.STATUS_CONFIRMED:
            self.store_task().set_delivered(user)

    def revert(self, user, reverted_content):
        """
        Gradually degrade the state of the flow, if ClerkAuxTask is confirmed.
        Then revert it to OPEN

        :param IntraUser user:
        :param [dict] reverted_content: List of items calling in reversion process.
        :return:
        """
        # Degrade myself to OPEN STATUS.
        if self.status is self.STATUS_CONFIRMED:
            # Degrade myself first
            self.status = self.STATUS_OPEN

            # Cancel the confirmations
            for conf in filter(lambda c: not c.is_cancelled(), self.confirmations):
                conf.cancel(cancelled_by=user)

            # We also need to degrade our friend instance
            store_task = self.store_task()

            # Let it degrade my friend as well.
            # Degrade store_task status
            store_task.status = StoreAuxTask.STATUS_CONFIRMED

            # Cascade the reversion calls
            r = store_task.revert(user)
            if r:
                signals.task_reverted.send(self.__class__,
                                           instance=self,
                                           reverted_content=reverted_content)
                self.touched(user)
            return r
        return False

    class Meta:
        collection_name = ':clerk'


class StoreAuxTask(AuxiliaryTask):
    """
    Paired task for *Store* vs *Clerk*
    """
    STATUS_OPEN = 0
    STATUS_CONFIRMED = 1
    STATUS_DELIVERED = 2
    STATUSES = (
        (STATUS_OPEN, _("STATUS_OPEN")),
        (STATUS_CONFIRMED, _("STATUS_CONFIRMED")),
        (STATUS_DELIVERED, _("STATUS_DELIVERED"))
    )
    status = doc.FieldNumeric(default=STATUS_OPEN, choices=STATUSES)

    @classmethod
    def default_parameters(cls, parent_task):
        t = task.Task.factory(5322)
        return t, parent_task.staging_duration, t.default_assignee()

    def clerk_task(self):
        """

        :return TaskDoc: Clerk Task
        """
        self.populate('ref_doc')
        if isinstance(self.ref_doc, ClerkAuxTask):
            # Save it from re-populate itself
            self.ref_doc.ref_doc = self
            return self.ref_doc
        raise ValueError(_("ERR_INVALID_DATA_STATE: %(reason)s") % {
            'reason': 'store_aux_task is ref_doc not clerk_aux_task'
        })

    def set_delivered(self, user):
        if self.status < self.STATUS_CONFIRMED:
            raise ValidationError(_("ERROR_STORE_TASK_MUST_BE_CONFIRMED: %(status)s") % {'status': self.status})

        if self.status >= self.STATUS_DELIVERED:
            raise ValidationError(_("ERROR_TASK_STATUS_CANT_DELIVERED: %(status)s") % {'status': self.status})

        self.status = self.STATUS_DELIVERED
        self.touched(user)

    def revert(self, user):
        """
        Revert StoreAuxTask while cancelling all the existing Confirmations.

        :param IntraUser user:
        :return:
        """
        if self.status == self.STATUS_CONFIRMED:
            # Cancel all existing confirmations
            for conf in filter(lambda c: not c.is_cancelled(), self.confirmations):
                conf.cancel(cancelled_by=user)

            # Revert the values to original state.
            self.actual_duration = 0
            self.actual_start = None
            self.actual_end = None
            self.status = self.STATUS_OPEN

            # Save it.
            self.touched(user)
            signals.task_reverted.send(self.__class__,
                                       instance=self,
                                       reverted_cotnent=[])
            return True

        raise ValidationError(_("ERR_CANNOT_REVERT_DELIVERED_TASK: %(task_doc_no)s") % {
            'task_doc_no': self.doc_no
        })

    class Meta:
        collection_name = ':store'


# Listening to events
@receiver(signals.task_released)
def on_task_released(sender, **kwargs):
    # Initialize tasks
    clerk = ClerkAuxTask.factory(sender)
    if clerk is None:
        return
    store = StoreAuxTask.factory(sender)
    if store is None:
        return
    # Assign friend relation
    clerk.ref_doc = store
    store.ref_doc = clerk
    # Save them
    clerk.touched(IntraUser.robot())
    store.touched(IntraUser.robot())


@receiver(signals.task_repeat)
def on_task_repeat(sender, parent, components, **kwargs):
    # Initialize tasks
    clerk = ClerkAuxTask.factory(parent, components=components)
    if clerk is None:
        return
    store = StoreAuxTask.factory(parent, components=components)
    if store is None:
        return
    # Assign friend relation
    clerk.ref_doc = store
    store.ref_doc = clerk
    # Save them
    clerk.touched(IntraUser.robot())
    store.touched(IntraUser.robot())


@receiver(signals.task_confirmed, sender=ClerkAuxTask)
def create_movement_upon_task_confirmation(sender, instance, code, confirmation, **kwargs):
    instance.populate('parent_task')

    # derive InventoryMovementEntry
    contents = []

    def populate_content(m):
        entries = InventoryMovementEntry.transfer_pair_factory(material=m.material,
                                                               quantity=m.quantity,
                                                               from_location=Location.factory('STORE').code,
                                                               to_location=Location.factory('STAGING').code,
                                                               to_ref_doc=instance.parent_task)
        contents.extend(list(entries))

    map(populate_content, confirmation.materials)

    # Create InventoryMovement
    if len(contents) > 0:
        gr = InventoryMovement.factory(InventoryMovement.ST_LP, contents, ref_doc=instance.parent_task.ref_doc)
        gr.touched(confirmation.created_by)
