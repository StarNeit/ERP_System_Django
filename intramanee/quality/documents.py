from intramanee.common import documents as doc, task
from intramanee.common.errors import BadParameterError, ValidationError
from django.utils.translation import ugettext as _
from intramanee.common.task import TaskGroup, Task
from intramanee.common import utils, codes, room, decorators
from intramanee.common.models import IntraUser
from intramanee.common.location import Location
from intramanee.stock.documents import MaterialMaster, InventoryMovement, InventoryMovementEntry, MOVEMENT_LOV_KEY

QUALITY_DOC_KEY = 'QUALITY'
QUALITY_DOC_PREFIX = 'Q'


class DefectItem(doc.FieldSpecAware):
    defect = doc.FieldString()
    quantity = doc.FieldNumeric()


class QualityItem(doc.FieldSpecAware):
    # inspection quantity
    quantity = doc.FieldNumeric(default=0)
    weight = doc.FieldNumeric(default=0)
    defects = doc.FieldList(doc.FieldNested(DefectItem))


class QualityDocument(doc.Authored):
    ref_doc = doc.FieldAnyDoc()
    cancelled = doc.FieldDoc('event')
    doc_no = doc.FieldString(none=True)
    items = doc.FieldList(doc.FieldNested(QualityItem))

    class Meta:
        collection_name = 'quality_document'
        require_permission = True
        doc_no_prefix = QUALITY_DOC_PREFIX

# Register the running number policy.
doc.RunningNumberCenter.register_policy(QUALITY_DOC_KEY, doc.DailyRunningNumberPolicy(prefix=QUALITY_DOC_PREFIX, digits=5))
