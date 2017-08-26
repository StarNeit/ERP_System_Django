__author__ = 'wasansae-ngow'

from intramanee.common.errors import ValidationError, BadParameterError
from intramanee.common import codes, documents as doc
from intramanee.common.uoms import UOM
from django.utils.translation import ugettext as _
from intramanee.common.location import Location

PR_NUMBER_KEY = 'PURCHASE_REQUISITION_NUMBER'
PR_NUMBER_PREFIX = 'PR'

PO_NUMBER_KEY = 'PURCHASE_ORDER_NUMBER'
PO_NUMBER_PREFIX = 'PO'


class PurchaseBaseItem(doc.FieldSpecAware):
    material = doc.FieldTypedCode(codes.StockCode, none=False)
    uom = doc.FieldUom(none=False, default='pc')
    quantity = doc.FieldNumeric(default=1)
    revision = doc.FieldNumeric(none=True)
    size = doc.FieldString(none=True)
    location = doc.FieldString(default=Location.locations['STORE'].code, none=False)
    delivery_date = doc.FieldDateTime()
    net_price = doc.FieldNumeric()


class PurchaseBase(doc.Authored):
    CURRENCY_THB = 'THB'
    CURRENCY_USD = 'USD'

    CURRENCY = (
        (CURRENCY_THB, _('THB_LABEL')),
        (CURRENCY_USD, _('US_LABEL')),
    )

    STATUS_OPEN = 0
    STATUS_APPROVED = 1
    STATUS_CLOSED = 2
    STATUS_CANCELLED = 3

    DOC_STATUSES = (
        (STATUS_OPEN, _('PURCHASING_STATUS_OPEN')),
        (STATUS_APPROVED, _('PURCHASING_STATUS_APPROVED')),
        (STATUS_CLOSED, _('PURCHASING_STATUS_CLOSED')),
        (STATUS_CANCELLED, _('PURCHASING_STATUS_CANCELLED')),
    )

    status = doc.FieldNumeric(choices=DOC_STATUSES, default=STATUS_OPEN, none=False)
    cancelled = doc.FieldDoc('event', none=True)
    doc_no = doc.FieldString()
    vendor = doc.FieldString(none=True)
    currency = doc.FieldString(choices=CURRENCY, default=CURRENCY_THB)
    items = doc.FieldList(doc.FieldNested(PurchaseBaseItem))
    mrp_session = doc.FieldDoc('mrp-session', none=True)

    def cancel(self, user, **kwargs):
        if self.status == self.STATUS_CLOSED:
            raise ValidationError(_("ERROR_CANNOT_CANCEL_CLOSED_PR"))

        if self.status == self.STATUS_CANCELLED:
            raise ValidationError(_("ERROR_PR_ALREADY_CANCELLED"))

        self.status = self.STATUS_CANCELLED
        self.cancelled = doc.Event.create(doc.Event.CANCELLED, user, against=self)
        self.touched(user, **kwargs)

    def touched(self, user, **kwargs):
        # Check permission
        if not kwargs.pop("automated", False):
            self.assert_permission(user, self.PERM_W)

        super(PurchaseBase, self).touched(user, **kwargs)


class PurchaseRequisitionItem(PurchaseBaseItem):
    open_quantity = doc.FieldNumeric(none=False)


class PurchaseRequisition(PurchaseBase):
    PR_TYPE_MRP = 0
    PR_TYPE_MANUAL = 1

    PR_TYPES = (
        (PR_TYPE_MRP, _('PR_TYPE_MRP')),
        (PR_TYPE_MANUAL, _('PR_TYPE_MANUAL')),
    )

    STATUS_OPEN = 0
    STATUS_APPROVED = 1
    STATUS_PARTIAL_CONVERTED = 2
    STATUS_CONVERTED = 3
    STATUS_CANCELLED = 4

    DOC_STATUSES = (
        (STATUS_OPEN, _('PR_STATUS_OPEN')),
        (STATUS_APPROVED, _('PR_STATUS_APPROVED')),
        (STATUS_PARTIAL_CONVERTED, _('PR_STATUS_PARTIAL_CONVERTED')),
        (STATUS_CONVERTED, _('PR_STATUS_CONVERTED')),
        (STATUS_CANCELLED, _('PR_STATUS_CANCELLED')),
    )

    status = doc.FieldNumeric(choices=DOC_STATUSES, default=STATUS_OPEN)
    type = doc.FieldNumeric(choices=PR_TYPES, default=PR_TYPE_MANUAL)
    items = doc.FieldList(doc.FieldNested(PurchaseRequisitionItem))

    def validate(self):
        for item in self.items:
            if not item.open_quantity:
                item.open_quantity = item.quantity
            elif item.open_quantity > item.quantity:
                raise ValidationError(_("ERROR_OPEN_QTY_MORE_THAN_QTY"))

    @classmethod
    def factory(cls, material, revision, size, due_date, quantity, user, pr_type=0, mrp_session_id=None, **kwargs):
        req = cls()
        req.mrp_session = mrp_session_id
        req.type = pr_type
        item = PurchaseRequisitionItem()
        item.material = material
        item.revision = revision
        item.size = size
        item.delivery_date = due_date
        item.quantity = quantity
        req.items = [item]
        req.touched(user, **kwargs)
        return req

    def save(self):
        if not self.doc_no:
            self.doc_no = doc.RunningNumberCenter.new_number(PR_NUMBER_KEY)

        super(PurchaseRequisition, self).save()

    class Meta:
        collection_name = 'purchase_requisition'
        require_permission = True
        doc_no_prefix = PR_NUMBER_PREFIX

doc.RunningNumberCenter.register_policy(PR_NUMBER_KEY, doc.DailyRunningNumberPolicy(PR_NUMBER_PREFIX))


class PurchaseOrderItem(PurchaseBaseItem):
    ref_doc = doc.FieldDoc(PurchaseRequisition)
    ref_doc_item = doc.FieldNumeric()


class PurchaseOrder(PurchaseBase):
    purchasing_group = doc.FieldString()
    payment_term = doc.FieldString()
    items = doc.FieldList(doc.FieldNested(PurchaseOrderItem))

    # TODO: implement factory function to group PR into PO

    def save(self):
        if not self.doc_no:
            self.doc_no = doc.RunningNumberCenter.new_number(PO_NUMBER_KEY)

        super(PurchaseOrder, self).save()

    class Meta:
        collection_name = 'purchase_order'
        require_permission = True
        doc_no_prefix = PO_NUMBER_PREFIX

doc.RunningNumberCenter.register_policy(PO_NUMBER_KEY, doc.DailyRunningNumberPolicy(PO_NUMBER_PREFIX))
