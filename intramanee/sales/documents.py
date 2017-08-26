__author__ = 'wasansae-ngow'
from intramanee.common.errors import ValidationError
from intramanee.common import codes, documents as doc
from django.utils.translation import ugettext as _
from intramanee.common.location import Location
from intramanee.stock.documents import MaterialMaster


SALES_ORDER_NUMBER_KEY = 'SALES_ORDER_NUMBER'
SALES_ORDER_NUMBER_PREFIX = 'SO'


class SalesOrderEntry(doc.Doc):
    material = doc.FieldTypedCode(codes.StockCode, none=False)
    revision = doc.FieldNumeric(none=True)
    quantity = doc.FieldNumeric(default=1, none=False)
    uom = doc.FieldUom(none=False)
    location = doc.FieldString(default=Location.locations['STORE'].code, none=False)
    size = doc.FieldString(none=True)
    # TODO: weight?
    net_price = doc.FieldNumeric(none=False, default=0)
    remark = doc.FieldString(none=True)


class SalesOrder(doc.Authored):
    CURRENCY_THB = 'THB'
    CURRENCY_USD = 'USD'

    CURRENCY = (
        (CURRENCY_THB, _('THB_LABEL')),
        (CURRENCY_USD, _('US_LABEL')),
    )

    STATUS_OPEN = 'OPEN'
    STATUS_CLOSED = 'CLOSED'
    SALES_ORDER_STATUSES = (
        (STATUS_OPEN, _('SALES_ORDER_STATUS_OPEN')),
        (STATUS_CLOSED, _('SALES_ORDER_STATUS_CLOSED')),
    )

    doc_no = doc.FieldString(none=True)     # Running Number
    customer = doc.FieldTypedCode(codes.CustomerCode, none=False)
    delivery_date = doc.FieldDateTime(none=False)
    status = doc.FieldString(none=False, choices=SALES_ORDER_STATUSES, default=STATUS_OPEN)
    sales_rep = doc.FieldIntraUser(none=True)
    customer_po = doc.FieldString(none=True)
    customer_po_date = doc.FieldDateTime(none=True)
    customer_currency = doc.FieldString(none=False, choices=CURRENCY, default=CURRENCY_THB)
    items = doc.FieldList(doc.FieldNested(SalesOrderEntry))
    remark = doc.FieldString(none=True)

    def __init__(self, object_id=None):
        super(SalesOrder, self).__init__(object_id)
        if object_id is None:
            self.items = []

    def validate(self):
        # FIXME: Check UOM
        for index, item in enumerate(self.items):
            material = MaterialMaster.factory(item.material)
            revisions = material.revisions()
            if revisions:
                revision_list = [rev.rev_id for rev in revisions]
                if item.revision not in revision_list:
                    raise ValidationError(_("ERROR_REVISION_DOES_NOT_EXIST: %(material)s in item %(itemnumber)s only has revision %(revisionlist)s") % {'material': item.material.code, 'itemnumber': index+1, 'revisionlist': revision_list})

                schematic = filter(lambda r: item.revision is r.rev_id, revisions)[0]
                if item.size and item.size not in schematic.conf_size:
                    raise ValidationError(_("ERROR_SIZE_DOES_NOT_EXIST: %(material)s revision %(materialrevision)s in item %(itemnumber)s only has size %(sizelist)s") % {'material': item.material.code, 'materialrevision': schematic.rev_id, 'itemnumber': index+1, 'sizelist': schematic.conf_size})

    def touched(self, user, **kwargs):
        # Check permission
        if not kwargs.pop("automated", False):
            self.assert_permission(user, self.PERM_W)
        super(SalesOrder, self).touched(user, **kwargs)

    def save(self):
        if not self.doc_no:
            self.doc_no = doc.RunningNumberCenter.new_number(SALES_ORDER_NUMBER_KEY)
        super(SalesOrder, self).save()

    def add_entry(self, material, revision, net_price, quantity, **kwargs):
        entry = SalesOrderEntry()
        entry.material = material
        entry.revision = revision
        entry.size = kwargs.pop('size', None)
        entry.quantity = quantity
        entry.uom = kwargs.pop('uom', 'pc')     # FIXME: populate from MaterialMaster instead.
        entry.remark = kwargs.pop('remark', None)
        entry.net_price = net_price
        self.items.append(entry)

    class Meta:
        collection_name = 'sales_order'
        require_permission = True
        doc_no_prefix = SALES_ORDER_NUMBER_PREFIX

# Register the running number policy.
doc.RunningNumberCenter.register_policy(SALES_ORDER_NUMBER_KEY, doc.DailyRunningNumberPolicy(SALES_ORDER_NUMBER_PREFIX))