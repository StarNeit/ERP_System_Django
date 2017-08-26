__author__ = 'peat'
from django.utils.translation import ugettext as _
from intramanee.common import codes, documents as doc, task
from intramanee.common.uoms import UOM
from intramanee.common.location import Location
from intramanee.common.errors import ValidationError, ProhibitedError, BadParameterError
from intramanee.common.models import IntraUser
import re
from intramanee.common.utils import NOW
from bson import ObjectId

MOVEMENT_LOV_KEY = "INV_MV_REASON"
MOVEMENT_NUMBER_KEY = "INV_MV_NUMBER"
MOVEMENT_NUMBER_PREFIX = "MV"


class InventoryMovementEntry(doc.FieldSpecAware):
    material = doc.FieldTypedCode(codes.StockCode, none=False)      # can intercept string
    """:type: codes.StockCode"""
    quantity = doc.FieldNumeric(default=1, none=False)
    batch = doc.FieldString()           # Assigned from InventoryMovementInstance
    """:type: basestring"""
    value = doc.FieldNumeric()
    weight = doc.FieldNumeric(none=True)
    location = doc.FieldString(default=Location.factory('STORE').code, none=False)
    """:type : Location|basestring"""
    ref_doc = doc.FieldAnyDoc(none=True)     # For production order only
    """:type : doc.Doc"""
    reason = doc.FieldString(lov=MOVEMENT_LOV_KEY, none=True)
    """:type: basestring"""

    @classmethod
    def factory(cls, material, quantity, location=None, ref_doc=None, reason=None, batch=None, value=None, weight=None):
        i = cls()
        i.material = material
        i.quantity = quantity
        i.ref_doc = ref_doc
        i.reason = reason
        i.batch = batch
        i.value = value
        i.weight = weight

        if location:
            i.location = location

        return i

    @classmethod
    def transfer_pair_factory(cls, material, quantity, from_location, to_location, from_ref_doc=None, to_ref_doc=None):
        """

        :param material:
        :param quantity:
        :param from_location:
        :param to_location:
        :param from_ref_doc:
        :param to_ref_doc:
        :return: cursor of InventoryMovementEntry
        """
        # Query inventory content, FIFO
        batch_candidate = InventoryContent.manager.project(cond={
            'material': str(material),
            'location': from_location,
            'quantity': {'$gt': 0}
        }, project=['_id', 'batch', 'quantity', 'value', 'weight'], sort=[("batch", 1)])

        leftover = quantity
        usage_tuples = []   # batch, quantity, value, weight
        for a in batch_candidate:
            batch_quantity = float(a['quantity'])
            used = min(batch_quantity, leftover)
            consumption_ratio = used / batch_quantity
            delta_value = float(a['value']) * consumption_ratio
            delta_weight = float(a['weight']) * consumption_ratio
            leftover -= used
            usage_tuples.append((a['batch'], used, delta_value, delta_weight))
            if leftover <= 0:
                break
        if leftover > 0:
            raise ValidationError(_('ERR_FAILED_TO_ALLOCATE_MATERIAL_TRANSFER_PAIR: %(material)s %(from_location)s %(to_location)s') % {
                'material': material,
                'from_location': from_location,
                'to_location': to_location
            })

        def create():
            for p in usage_tuples:
                o = cls()
                o.material = material
                o.quantity = -p[1]
                o.batch = p[0]
                o.value = -p[2]
                o.weight = -p[3]
                o.ref_doc = from_ref_doc
                o.location = from_location
                yield o
                i = cls()
                i.material = material
                i.quantity = p[1]
                i.batch = p[0]
                i.value = p[2]
                i.weight = p[3]
                i.ref_doc = to_ref_doc
                i.location = to_location
                yield i

        return create()


class InventoryMovement(doc.Authored):
    GR_PD = 103
    GR_BP = 531
    GR_PR = 101
    GR_LT = 107
    GI_PD = 261
    GI_SO = 601
    GI_SC = 231
    GI_CC = 201
    ST_LL = 311
    ST_LP = 312
    ST_PL = 313
    ST_LT = 314
    ST_MM = 309
    SA = 711
    TYPES = (
        (GR_PD, _("GOOD_RECEIVED_PRODUCTION_ORDER")),
        (GR_BP, _("GOOD_RECEIVED_BY_PRODUCT")),
        (GR_PR, _("GOOD_RECEIVED_PURCHASE_ORDER")),
        (GR_LT, _("GOOD_RECEIVED_LOST_AND_FOUND")),
        (GI_PD, _("GOOD_ISSUED_PRODUCTION_ORDER")),
        (GI_SO, _("GOOD_ISSUED_SALES_ORDER")),
        (GI_SC, _("GOOD_ISSUED_SCRAP")),
        (GI_CC, _("GOOD_ISSUED_COST_CENTER")),
        (ST_LL, _("STOCK_TRANSFER_LOCATION_TO_LOCATION")),
        (ST_LP, _("STOCK_TRANSFER_LOCATION_TO_PRODUCTION")),
        (ST_LT, _("STOCK_TRANSFER_LOST_AND_FOUND")),
        (ST_PL, _("STOCK_TRANSFER_PRODUCTION_TO_LOCATION")),
        (ST_MM, _("STOCK_TRANSFER_MATERIAL_TO_MATERIAL")),
        (SA, _("STOCK_ADJUSTMENT"))
    )
    doc_no = doc.FieldString(none=True)     # Running Number
    type = doc.FieldNumeric(choices=TYPES)
    cancel = doc.FieldDoc('inv_movement', none=True, unique=True, omit_if_none=True)
    """:type : InventoryMovement"""
    ref_ext = doc.FieldString(none=True)
    ref_doc = doc.FieldAnyDoc(none=True)
    posting_date = doc.FieldDateTime(none=True)
    """:type : datetime"""
    items = doc.FieldList(doc.FieldNested(InventoryMovementEntry))
    """:type : list[InventoryMovementEntry]"""

    def is_good_received(self):
        return self.type in [InventoryMovement.GR_PD, InventoryMovement.GR_PR, InventoryMovement.GR_BP, InventoryMovement.GR_LT]

    def is_good_issued(self):
        return self.type in [InventoryMovement.GI_CC, InventoryMovement.GI_PD, InventoryMovement.GI_SC, InventoryMovement.GI_SO]

    def is_transfer(self):
        return self.type in [InventoryMovement.ST_LL, InventoryMovement.ST_MM, InventoryMovement.ST_LP, InventoryMovement.ST_PL,
                             InventoryMovement.ST_LT]

    def is_adjust(self):
        return self.type in [InventoryMovement.SA]

    @classmethod
    def factory(cls, type, items, ref_doc=None):
        """
        Create InventoryMovement

        :param type:
        :param items: array of tuple or list of (material_code, quantity)
        :param ref_doc:
        :return:
        """
        # Sanitize 'items' based on 'type'
        if type in [cls.GI_CC, cls.GI_PD, cls.GI_SC, cls.GI_SO]:
            # Convert incoming tuple to InventoryMovementEntry
            pass
        elif type in [cls.GR_PD, cls.GR_PR, cls.GR_BP, cls.GR_LT]:
            # Convert incoming tuple to InventoryMovementEntry
            pass
        elif type in [cls.ST_LL, cls.ST_LP, cls.ST_PL, cls.ST_MM, cls.ST_LT]:
            # Let it go ~~
            pass
        else:
            raise ValidationError('Factory method cannot handle document type of %s.' % type)
        o = cls()
        o.type = type
        o.items = items
        o.ref_doc = ref_doc
        return o
    
    def validate(self, user=None):
        if user:
            self.created_by = user
        super(InventoryMovement, self).validate()
        # make sure all children has batch number if our doc_type is NOT IN GR
        if not self.is_good_received() or self.cancel is not None:
            if any(i.batch is None for i in self.items):
                raise ValidationError(_("ERROR_BATCH_IS_REQUIRED"))

        if self.is_good_issued():
            if any(i.quantity > 0 for i in self.items) and self.cancel is None:
                raise ValidationError(_("ERROR_GOOD_ISSUE_QUANTITY_MUST_BE_NEGATIVE"))
            if any(i.quantity < 0 for i in self.items) and self.cancel is not None:
                raise ValidationError(_("ERROR_CANCELLED_GOOD_ISSUE_QUANTITY_MUST_BE_POSITIVE"))

        if self.is_transfer():
            if len(self.items) % 2 != 0:
                raise ValidationError(_("ERROR_TRANSFER_MUST_HAVE_EVEN_NUMBER_OF_ITEMS"))

        # Validate based on Good Received, Good Issued, SA, etc. logic
        InventoryContent.apply(self, True)

    def do_cancel(self, user, reason, **kwargs):
        """
        Create Cancel Movement from Original InventoryMovement.

        :param user:
        :param reason:
        :param kwargs:
        :return:
        """

        src = self.serialized()
        cancellation = InventoryMovement()
        # cancellation = deepcopy(self)
        src['_id'] = cancellation.object_id
        src['doc_no'] = None
        del src['created_by']
        del src['edited_by']

        cancellation.deserialized(src)
        cancellation.cancel = self
        cancellation.posting_date = NOW()

        for item in cancellation.items:
            item.quantity *= -1
            item.weight *= -1
            item.value *= -1
            item.reason = reason

        cancellation.touched(user, **kwargs)
        return cancellation

    def touched(self, user, **kwargs):
        """

        :param IntraUser user:
        :param kwargs:
        :return:
        """
        # Check permission
        if not kwargs.pop("automated", False):
            self.assert_permission(user, self.PERM_W, self.type)

        # initialisation of conditional default value
        if self.doc_no is not None or not self.is_new():
            raise ValidationError(_("MATERIAL_MOVEMENT_IS_NOT_EDITABLE"))
        super(InventoryMovement, self).touched(user, **kwargs)

        # Post the changes to InventoryContent
        InventoryContent.apply(self)

    def save(self):
        self.doc_no = doc.RunningNumberCenter.new_number(MOVEMENT_NUMBER_KEY)
        # Apply doc_no if is GR && not cancelling
        if self.is_good_received() and (self.cancel is False or self.cancel is None):
            for item in self.items:
                item.batch = self.doc_no

        # Perform Save Operation
        super(InventoryMovement, self).save()

    class Meta:
        collection_name = 'inv_movement'
        indices = [
            ([("cancel", 1)], {"unique": True, "sparse": True})
        ]
        require_permission = True
        permission_write = [103, 101, 107, 531, 261, 601, 231, 201, 311, 312, 313, 314, 309, 711]
        doc_no_prefix = MOVEMENT_NUMBER_PREFIX

# Register the running number policy.
doc.RunningNumberCenter.register_policy(MOVEMENT_NUMBER_KEY, doc.DailyRunningNumberPolicy(MOVEMENT_NUMBER_PREFIX))


class InventoryContent(doc.Doc):
    # Primary Key:
    material = doc.FieldTypedCode(codes.StockCode, none=False)
    """:type : codes.StockCode"""
    location = doc.FieldString(default=Location.locations['STORE'].code, none=False)
    """:type : Location"""
    batch = doc.FieldString()
    ref_doc = doc.FieldAnyDoc(none=True)
    # Content Values
    quantity = doc.FieldNumeric(default=0)
    value = doc.FieldNumeric(default=0)
    weight = doc.FieldNumeric(default=None, none=True)

    def add(self, quantity, value, weight):
        new_quantity = self.quantity + quantity
        new_value = self.value + value
        if new_quantity < 0:
            raise ValidationError(_("ERROR_INSUFFICIENT_QUANTITY: %(content_signature)s %(content_quantity)s + %(additional_quantity)s < 0") % {
                'content_quantity': self.quantity,
                'additional_quantity': quantity,
                'content_signature': str(self)
            })

        new_weight = None
        if weight is not None or self.weight is not None:
            new_weight = (self.weight or 0) + (weight or 0)
            if new_weight < 0:
                raise ValidationError("%s: %s + %s < 0" % (_("ERROR_UNBALANCE_WEIGHT"), self.weight, weight))

        self.quantity = new_quantity
        self.value = new_value
        self.weight = new_weight

    def should_delete(self):
        return self.quantity == 0 and self.weight < 0.01 and self.value < 0.01

    @classmethod
    def get_value(cls, material, **kwargs):
        location = kwargs.pop('location', None)
        batch = kwargs.pop('batch', None)
        cond = {
            'material': material if isinstance(material, basestring) else str(material)
        }
        if batch is not None:
            cond['batch'] = batch
        if location is not None:
            cond['location'] = location
        r = cls.manager.o.aggregate([
            {'$match': cond},
            {'$group': {
                '_id': None,
                'total': {'$sum': '$quantity'}
            }}
        ])
        return 0 if len(r['result']) == 0 else r['result'][0]['total']

    def __str__(self):
        return "INV_CNT %s %s %s (ref: %s)" % (self.material, self.location, self.batch, str(self.ref_doc))

    @staticmethod
    def apply(movement, dry_run=False):
        """
        Apply Inventory Movement to the Content

        :param InventoryMovement movement:
        :param bool dry_run:
        """
        for item in movement.items:
            content = InventoryContent.factory(item.material, item.location, item.batch, item.ref_doc)
            content.add(item.quantity, item.value, item.weight)
            if not dry_run:
                if content.should_delete():
                    content.delete()
                else:
                    content.save()

    @staticmethod
    def factory(material_code, location, batch, ref_doc):
        """

        :param codes.StockCode material_code:
        :param Location|basestring location:
        :param basestring batch:
        :param doc.Doc ref_doc:
        :return:
        """
        cond = {
            'material': unicode(material_code),
            'location': location,
            'batch': batch
        }
        if ref_doc:
            key1, key2 = doc.FieldAnyDoc.as_value_for_query(ref_doc)
            cond['ref_doc.0'] = key1
            cond['ref_doc.1'] = key2
        else:
            cond['ref_doc'] = None
        r = InventoryContent.manager.find(1, 0, cond)

        # if no record found.
        if len(r) == 0:
            # Create unsaved new item
            o = InventoryContent()
            o.material = material_code
            o.location = location
            o.batch = None if batch == "" else batch
            o.ref_doc = ref_doc
            return o
        return r[0]

    @classmethod
    def query_content(cls, material=None, location=None, batch=None, ref_doc=None, **kwargs):
        """
        A thin wrapper to make a inventory content query easier

        :param material:
        :param location:
        :param batch:
        :param ref_doc:
        :param kwargs:
        :return:
        """
        cond = {
            'material': material,
            'location': location,
            'batch': batch,
            'ref_doc': ref_doc
        }
        # sanitize
        # (1) remove all none attributes
        del_keys = []
        for k in cond:
            if cond[k] is None:
                del_keys.append(k)
        for k in del_keys:
            del cond[k]

        # (2) String attributes
        for k in ['material', 'location', 'batch']:
            if k in cond:
                cond[k] = str(cond[k])
        # (3) take care of ref_doc field
        if 'ref_doc' in cond:
            if isinstance(cond['ref_doc'], doc.Doc):
                cond['ref_doc.0'] = cond['ref_doc'].object_id
                cond['ref_doc.1'] = cond['ref_doc'].manager.collection_name
                del cond['ref_doc']
            elif isinstance(cond['ref_doc'], ObjectId):
                cond['ref_doc.0'] = cond['ref_doc']
                del cond['ref_doc']
            else:
                raise ValidationError(_("ERR_QUERY_CONTENT_CANNOT_INTERPRET_PARAMETER: %(parameter)s %(type)s") % {
                    'parameter': 'ref_doc',
                    'type': type(cond['ref_doc'])
                })
        # query
        return cls.manager.find(cond=cond)

    class Meta:
        collection_name = 'inv_content'
        require_permission = True


class SchematicMaterial(doc.FieldSpecAware):
    """
    SchematicMaterial = Schematic's component

    An entry that represent as a material to be used within SchematicEntry
    """
    code = doc.FieldTypedCode(codes.StockCode, allow_incomplete=True)  # TypedCode
    quantity = doc.FieldList(doc.FieldNumeric(default=1, none=False))
    is_configurable = doc.FieldBoolean(default=False)
    counter = doc.FieldUom(none=True)  # default from material object resolved from code
    cost = doc.FieldNumeric(default=0, none=False)  # default from material object resolved from code

    def normalized(self, for_size_index):
        o = self.__class__()
        # easy stuff
        o.code = self.code
        o.is_configurable = False
        o.counter = self.counter
        o.cost = self.cost
        # size sensitive stuff
        if not self.is_configurable:
            o.quantity = self.quantity[:]
        else:
            if len(self.quantity) <= for_size_index or for_size_index < 0:
                raise ValidationError(_("ERR_NORMALIZE_SCHEMATIC_ENTRY_FAILED_MATERIAL_QUANTITY_SIZE_INDEX_OUT_OF_RANGE"))
            o.quantity = [self.quantity[for_size_index]]
        return o

    def __repr__(self):
        return "%s x %s %s %s@%s" % (
            self.code,
            self.quantity,
            str(self.counter),
            "(conf) " if self.is_configurable else "",
            self.cost)


class SchematicEntry(doc.FieldSpecAware):
    """
    A Schematic's Line
    """
    id = doc.FieldString()
    process = doc.FieldTask()
    materials = doc.FieldList(doc.FieldNested(SchematicMaterial))
    source = doc.FieldList(doc.FieldString())
    is_configurable = doc.FieldBoolean(default=False)
    duration = doc.FieldList(doc.FieldNumeric(none=False, default=0.0))
    staging_duration = doc.FieldList(doc.FieldNumeric(none=False, default=0.0))
    labor_cost = doc.FieldNumeric(none=False, default=0.0)
    markup = doc.FieldNumeric(none=False, default=0.0)
    remark = doc.FieldString(default="")

    def __repr__(self):
        return "%s: %s w/%s materials conf=%s from=%s" % \
               (self.id, self.process, len(self.materials), self.is_configurable, self.source)

    def add_material(self, code, quantities, is_configurable, counter, cost, add=True):
        m = SchematicMaterial()
        m.code = code
        m.quantity = quantities
        m.is_configurable = is_configurable
        m.counter = counter
        m.cost = cost
        if add:
            self.materials.append(m)
        return m

    def to_dummy(self):
        return task.SchematicDummy(self.id, self.process.code, self.source, ref=self)

    def try_propagate(self, target_material, replacement_array):
        """
        Replace target_material (take/borrow only) with replacement_array (array of sized materials)

        :param target_material:
        :param replacement_array:
        :return:
        """
        # Sanity Check
        if not isinstance(target_material, codes.StockCode):
            raise BadParameterError.std(require_type=codes.StockCode)

        if not self.materials:
            return

        # all these materials can be ...
        #   - Borrow case
        #   - Take case <-- TODO: Should filter this case out.
        #   - Make case
        append_list = []        # to keep the loop safe, we will extend this self.materials once we complete the removal
        process_list = list(reversed(list(enumerate(self.materials))))
        print 'Process_list', process_list
        print '\tlooking for', target_material
        print '\tReplacement_array', replacement_array
        for sch_mat_index, sch_mat in process_list:
            if sch_mat.code == target_material:
                # Sanity check
                if sch_mat.is_configurable and len(sch_mat.quantity) != len(replacement_array):
                    raise BadParameterError(_("ERR_CANNOT_PROPAGATE_MATERIAL_SIZES: %(material)s") % {
                        'material': str(sch_mat.code)
                    })
                # update append_list
                for size_index, replace_mat in enumerate(replacement_array):
                    quantities = [0] * len(replacement_array)
                    quantities[size_index] = sch_mat.quantity[size_index] if sch_mat.is_configurable else sch_mat.quantity[0]
                    append_list.append(self.add_material(code=replace_mat,
                                                         quantities=quantities,
                                                         is_configurable=True,
                                                         counter=sch_mat.counter,
                                                         cost=sch_mat.cost,
                                                         add=False))

                # delete original one
                del self.materials[sch_mat_index]
        print '\toutput append_list', append_list
        print '\tbefore', self.materials
        self.materials.extend(append_list)
        print '\tafter\n', self.materials

        # If appended, this task must be converted to configurable
        if len(append_list) > 0 and not self.is_configurable:
            self.is_configurable = True
            self.duration = map(lambda _: self.duration[0], range(0, len(replacement_array)))
            self.staging_duration = map(lambda _: self.staging_duration[0], range(0, len(replacement_array)))

    def normalize(self, for_size_index):
        o = self.__class__()
        # simple stuff
        o.id = self.id
        o.process = self.process
        o.source = self.source[:]
        o.is_configurable = False
        o.labor_cost = self.labor_cost
        o.markup = self.markup
        o.remark = self.remark
        # nested stuff
        o.materials = map(lambda a: a.normalized(for_size_index), self.materials)
        # size sensitive stuff
        if not self.is_configurable:
            o.duration = self.duration[:]
            o.staging_duration = self.staging_duration[:]
        else:
            if not (0 <= for_size_index < len(self.duration)):
                raise ValidationError(_("ERR_NORMALIZE_SCHEMATIC_ENTRY_FAILED_DURATION_SIZE_INDEX_OUT_OF_RANGE"))
            if not (0 <= for_size_index < len(self.staging_duration)):
                raise ValidationError(_("ERR_NORMALIZE_SCHEMATIC_ENTRY_FAILED_STAGING_DURATION_SIZE_INDEX_OUT_OF_RANGE"))
            o.duration = [self.duration[for_size_index]]
            o.staging_duration = [self.staging_duration[for_size_index]]
        return o

    @classmethod
    def from_dummy(cls, dummy):
        if isinstance(dummy.ref, SchematicEntry):
            entry = dummy.ref
        else:
            entry = SchematicEntry()
            entry.labor_cost = 0
            entry.markup = 0
            entry.remark = "Expanded"
            entry.duration = [task.Task.factory(dummy.task_code).standard_time]
            entry.staging_duration = [task.Task.factory(dummy.task_code).staging_duration]
            entry.is_configurable = False
        entry.id = dummy.id
        entry.process = dummy.task_code
        entry.source = dummy.source
        return entry


class Schematic(doc.Authored):
    material_id = doc.FieldDoc('material_master')               # link to Material (for redundancy check),
    rev_id = doc.FieldNumeric(default=1)                        # Support Revision (based on Design rev_id)in case schematic is detached
    conf_size = doc.FieldList(doc.FieldString())                # Support Configuration
    source = doc.FieldAnyDoc(none=True)                         # source of schematic, link directly to design object
    schematic = doc.FieldList(doc.FieldNested(SchematicEntry))  # schematic - saved from Design's Process Entry.

    def expand(self, is_production=False):
        """

        :param is_production:
        :return: void
        """
        if self.schematic and len(self.schematic) > 0:
            context = map(lambda s: s.to_dummy(), self.schematic)
            new_context = task.Task.expand(context, is_production=is_production, verbose=False)
            self.schematic = map(lambda a: SchematicEntry.from_dummy(a), new_context)

    @classmethod
    def pair_exists(cls, material_id, rev_id, conf_size):
        """
        validate if material_id + rev_id + conf_size exist.

        :param material_id:
        :param rev_id:
        :param conf_size:
        :return:
        """
        return 0 < Schematic.manager.count(cond={
            'material_id': doc._objectid(material_id),
            'rev_id': rev_id,
            'conf_size': conf_size
        })

    @staticmethod
    def factory(material_id, rev_id, author, **kwargs):
        verbose = kwargs.pop('verbose', False)
        sch = Schematic.manager.find(1, 0, cond={
            'material_id': material_id,
            'rev_id': rev_id
        })
        if len(sch) > 0:
            if verbose:
                print("Schematic.factory() -> Schematic already exists %s, %s" % (material_id, rev_id))
            return sch[0]

        # Create new one
        sch = Schematic()
        sch.material_id = material_id
        sch.rev_id = rev_id
        sch.conf_size = kwargs.pop('conf_size', [])
        sch.touched(author)
        if verbose:
            print("Schematic.factory() -> Creating new schematic %s, %s" % (material_id, rev_id))
        return sch

    @classmethod
    def of(cls, material_id, revision_id, throw=False):
        """

        :param basestring|ObjectId material_id:
        :param int revision_id:
        :param bool throw:
        :return Schematic:
        """
        o = Schematic.manager.find(cond={
            'material_id': doc._objectid(material_id),
            'rev_id': revision_id
        })
        if len(o) == 0:
            if throw:
                raise ValueError('Unknown material+revision=%s+%s' % (material_id, revision_id))
            else:
                return None
        return o[0]

    @classmethod
    def revisions(cls, material_id):
        """

        :param basestring|ObjectId material_id:
        :return [Schematic]:
        """
        return Schematic.manager.find(cond={
            'material_id': doc._objectid(material_id)
        })

    def __repr__(self):
        txt = "Material: %s rev%s (conf=%s) + schematic ...\n" % (self.material_id, self.rev_id, self.conf_size)
        if self.schematic and len(self.schematic) > 0:
            for sch in self.schematic:
                txt += "\t%s\n" % sch
        return txt

    class Meta:
        collection_name = 'material_schematic'
        references = [('material_master', 'material_id')]


class MaterialMaster(doc.Authored):
    MRP = 'M'
    NO_MRP = 'N'
    REORDER = 'R'
    MRP_TYPES = (
        (MRP, _("MRP_TYPE_MRP")),
        (NO_MRP, _("MRP_TYPE_NO_MRP")),
        (REORDER, _("MRP_TYPE_REORDER")),
    )

    EXTERNAL = 'E'
    INTERNAL = 'I'
    PROCUREMENT_TYPES = (
        (EXTERNAL, _("PROCUREMENT_TYPE_EXTERNAL")),
        (INTERNAL, _("PROCUREMENT_TYPE_INTERNAL"))
    )

    # Lot Size Policy
    LZ_LOT_FOR_LOT = 'EX'      # One procurement for One demand
    LZ_DAILY = 'TB'            # Accumulate daily demand to one procurement amount
    LZ_WEEKLY = 'WS'             # Accumulate weekly demand to one procurement amount for the whole week based on offset (:lot_size_arg value 0 <= 6)
    LZ_MONTHLY = 'MS'            # Accumulate monthly demand to one procurement amount for the whole month based on offset (:lot_size_arg value 0 <= 28)
    LZ_MAX_STOCK_LEVEL = 'HB'  # maximize amount to the :lot_size_arg, at the multiplication of :lot_size_max, :lot_size_min
    LOT_SIZES = (
        (LZ_LOT_FOR_LOT, _("LOT_SIZE_LOT_FOR_LOT")),
        (LZ_DAILY, _("LOT_SIZE_DAILY")),
        (LZ_WEEKLY, _("LOT_SIZE_WEEKLY")),
        (LZ_MONTHLY, _("LOT_SIZE_MONTHLY")),
        (LZ_MAX_STOCK_LEVEL, _("LOT_SIZE_MAX_STOCK_LEVEL")),
    )

    AI_A = 'A'
    AI_B = 'B'
    AI_C = 'C'
    AI_D = 'D'
    AI_E = 'E'
    AI_INDICATORS = (
        (AI_A, "A"),
        (AI_B, "B"),
        (AI_C, "C"),
        (AI_D, "D"),
        (AI_E, "E"),
    )

    PLANT_AVAILABLE = 'AV'
    PLANT_BLOCKED = 'BL'
    PLANT_STATUSES = (
        (PLANT_AVAILABLE, _("PLANT_STATUS_AVAILABLE")),
        (PLANT_BLOCKED, _("PLANT_STATUS_BLOCKED"))
    )

    code = doc.FieldTypedCode(codes.StockCode, none=False)
    # General Info
    uom = doc.FieldUom(none=False)
    description = doc.FieldString(max_length=500, none=True)
    gross_weight = doc.FieldNumeric(none=True)
    net_weight = doc.FieldNumeric(none=True)
    plant_status = doc.FieldString(choices=PLANT_STATUSES, default=PLANT_AVAILABLE)
    # MRP
    scrap_percentage = doc.FieldNumeric(none=False, default=0)          # type: float
    scale = doc.FieldNumeric(none=False, default=1)                     # type: float
    mrp_type = doc.FieldString(choices=MRP_TYPES, default=MRP, max_length=1)
    location = doc.FieldString(default=Location.locations['STORE'].code)
    reorder_point = doc.FieldNumeric(none=False, default=0)
    planning_time_fence = doc.FieldNumeric(default=0)
    procurement_type = doc.FieldString(choices=PROCUREMENT_TYPES, default=EXTERNAL, none=False)    # Default logic is based on stock code
    gr_processing_time = doc.FieldNumeric(default=0, validators=[(lambda v: v < 0, 'Positive value only')])
    planned_delivery_time = doc.FieldNumeric(default=2)
    lot_size = doc.FieldString(choices=LOT_SIZES, default=LZ_LOT_FOR_LOT)
    lot_size_arg = doc.FieldNumeric(none=True)      # depends on lot_size
    lot_size_min = doc.FieldNumeric(default=0)
    lot_size_max = doc.FieldNumeric(default=0)
    safety_stock = doc.FieldNumeric(default=0, none=True)      # if value is None then calculate it instead.
    deprecated_date = doc.FieldDateTime(none=True, default=None)
    deprecated_replacement = doc.FieldDoc('material_master', none=True, default=None)
    # Purchasing ...
    # Inventory
    enable_cycle_counting = doc.FieldBoolean(none=False, default=True)
    abc_indicator = doc.FieldString(choices=AI_INDICATORS, default=AI_E, max_length=1)

    # MRP calculation, running priorities
    hierarchy_affinity = doc.FieldNumeric(none=True)

    # deactivated
    schematic = doc.FieldDoc('material_schematic', none=True)           # Active schematic

    def get_safety_stock(self):
        if self.safety_stock is None:
            # FIXME: Calculate safety_stock based on consumption rate
            pass
        return self.safety_stock

    def update_schematic(self, user, schematic_object, message="update schematic"):
        if not isinstance(schematic_object, Schematic):
            raise ProhibitedError("update_schematic only accept schematic_object")

        schematic_object.material_id = self
        self.schematic = schematic_object
        self.hierarchy_affinity = None      # required new setup
        self.touched(user, message=message)

    def revisions(self):
        """
        :return: all possible revisions of this material object
        """
        return Schematic.revisions(self.object_id)

    def revision(self, revision_id):
        """
        Return specific revision of given this material.

        :param revision_id:
        :return:
        """
        if revision_id is None:
            return self.schematic
        return Schematic.of(self.object_id, revision_id, throw=False)

    def validate_pair(self, revision_id, size):
        return Schematic.pair_exists(self.object_id, revision_id, size)

    def has_schematic(self):
        if self.schematic is not None:
            self.populate('schematic')
            return len(self.schematic.schematic) > 0
        return False

    @classmethod
    def get(cls, code):
        """
        Lookup material master by code. And raise error if such code is not found.

        :param basestring|codes.StockCode code:
        :return: MaterialMaster
        """
        mm = MaterialMaster.of('code', str(code))
        if mm is None:
            raise BadParameterError(_('ERROR_UNKNOWN_MATERIAL %(material_code)s') % {'material_code': code})
        return mm

    @classmethod
    def factory(cls, code, uom=None, procurement_type=EXTERNAL, author=None, scrap_percentage=0):
        """
        Lookup by Code first,
            - if not exists,
                - if UoM is not supplied
                    - raise Exception
                - create a MaterialMaster
            - if exists,
                - return a fetched MaterialMaster

        :param codes.StockCode code:
        :param basestring|UOM uom:
        :param basestring procurement_type:
        :param IntraUser author:
        :param int scrap_percentage:
        :return MaterialMaster:
        """
        ProhibitedError.raise_if(not isinstance(code, codes.StockCode), "provided code must be StockCode instance")
        materials = cls.manager.find(1, 0, cond={
            'code': str(code)
        })
        # if exists
        if len(materials) > 0:
            return materials[0]

        if uom is None or author is None:
            raise ProhibitedError("UOM and author must be supplied in case of creation")
        if not UOM.has(uom):
            raise BadParameterError("UOM \"%s\" is invalid" % uom)

        # Initialize Scale according to code
        if re.compile('^stock-[A-Z]{3}02[123]').match(str(code)) is not None:
            scale = 10
        else:
            scale = 1
        o = cls()
        o.code = code
        o.uom = uom
        o.procurement_type = procurement_type
        o.scrap_percentage = scrap_percentage
        o.scale = scale
        o.touched(author)
        return o

    class Meta:
        collection_name = 'material_master'
        require_permission = True
