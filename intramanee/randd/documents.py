from intramanee.common import codes, decorators
from intramanee.common.documents import ApprovableDoc, Doc, \
    FieldNumeric, FieldList as listed, \
    FieldDateTime, FieldString, FieldTypedCode, \
    FieldNested as nested, FieldSpecAware, FieldUserFile, \
    Revisioned, Validatable, FieldIntraUser, \
    FieldDoc, _objectid
from intramanee.common.codes.models import LOV
from intramanee.stock.documents import SchematicEntry, MaterialMaster, Schematic
from django.utils.translation import ugettext as _
from intramanee.common.errors import ValidationError, ProhibitedError, BadParameterError
from intramanee.common.uoms import UOM
from itertools import chain
from django.dispatch import receiver
import copy
import signals
import re

__author__ = 'peat'

# Hardcoded configurations
_SPRUE = str(codes.Task.factory('4143'))
_MAKE_RUBBER_MOLD = str(codes.Task.factory('5261'))
_MAKE_STAMPING_DIE = str(codes.Task.factory('4161'))
_TASK_STOPPER_PAIRS = dict([
    (_SPRUE, '###021'),
    (_MAKE_RUBBER_MOLD, '###022'),
    (_MAKE_STAMPING_DIE, '###023')
])


def is_task_stopper(p):
    return str(p.process) in _TASK_STOPPER_PAIRS


class DesignProcess(FieldSpecAware):
    master_modeling = listed(nested(SchematicEntry))
    sample_creation = listed(nested(SchematicEntry))

    def new_process(self, id, task, materials, source, configurable, duration, labor_cost, markup, **kwargs):
        s = SchematicEntry()
        s.id = id
        s.process = task
        s.materials = materials
        s.source = source
        s.is_configurable = configurable
        s.duration = duration
        s.labor_cost = labor_cost
        s.markup = markup
        target = kwargs.pop('target', None)
        if target == 'master_modeling':
            self.master_modeling.append(s)
        elif target == 'sample_creation':
            self.sample_creation.append(s)
        return s

    def extract_master_models(self, verbose=False):
        """
        Extract all task stoppers and its first make that matched: stock-###021 (mold)

        :return: list of tuple(StockCode, uom, [SchematicEntry])
        """
        output = []
        if len(self.master_modeling) <= 0:
            return output

        if verbose:
            print("Extraction Begun")
            for p in self.master_modeling:
                print "\t I: ", p

        indices = dict((p.id, p) for p in self.master_modeling)
        last_process = self.master_modeling[-1]

        ValidationError.raise_if(not is_task_stopper(last_process), _("ERROR_TASK_STOPPER_MUST_BE_LAST_PROCESS"))
        for final_process in reversed(filter(is_task_stopper, self.master_modeling)):
            if verbose:
                print("\t=> For %s" % final_process)
            # populate it
            buffer = [final_process]
            processes = []
            # populate until buffer depleted
            while len(buffer) > 0:
                p = buffer.pop()
                processes.append(copy.deepcopy(p))
                for proc_id in p.source:
                    buffer.append(indices[proc_id])

            # Clean up result
            # 1. Identify the final material_code (make of sprue)
            # 2. Place the schematic with correct placement of process.
            _pttrn = _TASK_STOPPER_PAIRS[str(final_process.process)]

            def is_target_make(m):
                return codes.TypedCode.compare(_pttrn, m.code) and m.quantity[0] < 0

            # List all makes
            makes = dict(map(lambda m: (m.code, m), filter(is_target_make, processes[0].materials)))
            if verbose:
                print "\t=> output!", makes
            if len(makes) > 1:
                # if we have more than 1 make, then get only the one without pair
                borrows = dict(map(lambda m: (m.code, m), filter(lambda m: m.code in makes and m.quantity[0] > 0, processes[0].materials)))
                diff_key = set(makes) - set(borrows)
                map(makes.__delitem__, diff_key)        # Delete all borrows items from make list

            # Sanity check
            ValidationError.raise_if(len(makes) != 1, _("ERROR_UNABLE_TO_IDENTIFY_MASTER_MODEL"))

            # material to create from the final process
            material_to_create = makes.popitem()[1]

            # Remove the material from the process
            del processes[0].materials[processes[0].materials.index(material_to_create)]

            # Make sure the order of process is correct
            processes.reverse()

            # TODO: Normalize existing ID/Source binding

            # Append to output array
            output.append((material_to_create.code, material_to_create.counter, processes))

        if verbose:
            print("Done")
        return output


class SalesManifest(FieldSpecAware):
    due_date = FieldDateTime()
    quantity = FieldNumeric(default=0)
    # sales_order_id            # TBC


class DesignUID(Doc):
    code = FieldString(max_length=21)
    commit_by = FieldIntraUser()

    class Meta:
        collection_name = 'design_uid'
        indices = [
            ([("code", 1)], {"unique": True, "sparse": True})
        ]

    @staticmethod
    def lookup(code):
        """

        :param code:
        :return: (DesignUID object)
        """
        if code is None:
            return None
        candidates = DesignUID.manager.find(1, 0, {'code': code})
        if len(candidates) == 0:
            return None
        return candidates[0]

    @staticmethod
    def get(code):
        candidates = DesignUID.manager.find(1, 0, _id=_objectid(code))
        if len(candidates) == 0:
            return None
        return candidates[0]

    @staticmethod
    def validate_pair(design_uid, code):
        """
        Validate design_uid + code

        - Validate design_uid is not obligated to something else but "code"
        - then Validate "code" is not yet taken

        :param design_uid:
        :param code:
        :return: true, is already paired, false if not yet paired, throw if error
        """
        try:
            o = DesignUID(design_uid)
            if o.code is None:
                # design_uid is NEW
                # your design_uid is not yet bind, meaning your status is not Approved yet.
                pass

            # design_uid already exists, validate if value is correct
            if o.code != code:
                raise ValidationError("%s: check_code=%s, uid_based_code=%s" % (_("ERROR_DESIGN_UID_MISMATCHED"), code, o.code))
            return True
        except ValueError:
            # design_uid not exist, let's check if code is already taken or not?
            if DesignUID.lookup(code) is not None:
                raise ValidationError("%s: %s" % (_("ERROR_DESIGN_UID_ALREADY_IN_USED"), code))
            return False

    @staticmethod
    def commit(design_uid, code, user):
        o = DesignUID()
        o.object_id = design_uid
        o.code = code
        o.commit_by = user
        o.save()


class Design(Revisioned, ApprovableDoc, Validatable, decorators.JsonSerializable):
    # Data
    code = FieldString(max_length=21)
    design_number = FieldString(max_length=4)
    design_code = FieldDoc('design_uid', trasient=True, default=None)
    collection_name = FieldString(max_length=25)
    customer = FieldTypedCode(codes.CustomerCode)
    sales_manifest = nested(SalesManifest)
    attachments = listed(FieldUserFile(), remove_none_values=True)
    thumbnail_id = FieldUserFile(store_id=True)
    misc = FieldString(max_length=450)
    process = nested(DesignProcess)
    counter = FieldString(default=UOM.uoms['pc'].code)
    # Spec (Tiles)
    metal = listed(FieldTypedCode(codes.MetalCode))
    finish = listed(FieldTypedCode(codes.FinishCode))
    style = listed(FieldTypedCode(codes.StyleCode))
    plating = listed(FieldTypedCode(codes.PlatingCode))
    stone = listed(FieldTypedCode(codes.StoneTypeCode))
    stamping = listed(FieldString())
    size = listed(FieldString())
    """:type : [basestring]"""

    def __init__(self, object_id=None):
        super(Design, self).__init__(object_id)
        # Transient variables
        self.after_touched = None
        self.is_paired = None

    def as_json(self):
        return {
            '_id': str(self.object_id),
            'code': self.code,
            'customer_code': str(self.customer),
            'thumbnail_id': str(self.thumbnail_id.id) if self.thumbnail_id is not None else None,
            'attachments': map(lambda a: {
                '_id': str(a.id),
                'file': str(a.file)
            }, self.attachments)
        }

    def populate(self, path):
        if path == 'design_code':
            self.design_code = DesignUID.get(self.rev_unique_id)
        return super(Design, self).populate(path)

    @classmethod
    def lookup(cls, design_code_with_revision, single=False):
        """

        :param design_code_with_revision:
        :param single: return only one result or None
        :return: Array of Design object matched design_code
        """
        if design_code_with_revision is None:
            raise BadParameterError("Required non-None design code string")
        # validate input first
        matches = re.compile(r'^([A-Z0-9-]+)(r(\d+))?').match(design_code_with_revision)
        if not matches:
            raise BadParameterError("Invalid design code %s" % design_code_with_revision)

        groups = matches.groups()

        design_uid = groups[0]
        design_rev = groups[2]

        design_uid = DesignUID.lookup(design_uid)

        if design_uid is None:
            raise ValidationError("Design UID %s not found." % design_uid)

        cond = {
            'rev_unique_id': design_uid.object_id
        }

        if design_rev is not None:
            cond['rev_id'] = int(design_rev)

        r = cls.manager.find(cond=cond)
        if single:
            return r[len(r)-1] if len(r) > 0 else None
        else:
            return r

    def validate_for_errors(self, **kwargs):
        """

        :param kwargs:
        :return: design errors tuple: drawing, master_material, production, pricing, general
        """
        # flags
        allow_wildcard = kwargs.pop('allow_wildcard', True)
        validate_product_code_completed = kwargs.pop('validate_product_code_completed', True)
        validate_product_code_comparing = kwargs.pop('validate_product_code_comparing', True)
        validate_4_pillars = kwargs.pop('validate_4_pillars', True)
        validate_drawing = kwargs.pop('validate_drawing', validate_4_pillars)
        validate_master_modeling = kwargs.pop('validate_master_modeling', validate_4_pillars)
        validate_production = kwargs.pop('validate_production', validate_4_pillars)
        validate_pricing = kwargs.pop('validate_pricing', validate_4_pillars)

        # output
        general = []
        pricing = []
        drawing = []
        master_modeling = []
        production = []

        # Buffer
        material_uom_map = {}

        # 1 Consistency Checks
        # Check product code completed.
        is_product_code_completed = self.code is not None and ("#" not in self.code)
        if (validate_product_code_comparing or validate_product_code_completed) and not is_product_code_completed:
            general.append(_("ERROR_REQUIRE_COMPLETE_PRODUCT_CODE"))

        # Check product code comparing.
        if validate_product_code_comparing:
            try:
                self.is_paired = DesignUID.validate_pair(self.rev_unique_id, self.code)
            except ValidationError as e:
                general.append(e.message)

        # Drawing
        if validate_drawing:
            if len(self.attachments) <= 0:
                drawing.append(_("ERROR_REQUIRE_ATTACHMENT"))

        # at least 3 processes,
        # for all process has standard time
        #      for all material must be completed code
        #      for all material have quantity/counter
        def validate_process(process_entries):
            """
            - at least 3 processes
            - each process need standard time
                - all material must be completed code
                - all material have quantity, counter
                - TODO: all material have correct counter
            :param process_entries:
            :return:
            """
            error = []
            # at least 3 processes
            if len(process_entries) < 3:
                error.append(_("ERROR_REQUIRE_THREE_PROCESSES"))

            if not all(all(d > 0 for d in p.duration) for p in process_entries):
                error.append(_("ERROR_REQUIRE_DURATION"))

            if not all(all(d >= 0 for d in p.staging_duration) for p in process_entries):
                error.append(_("ERROR_REQUIRE_STAGING_DURATION"))

            if not all(len(p.staging_duration) == len(p.duration) for p in process_entries):
                error.append(_("ERROR_REQUIRE_EQUAL_SIZE_OF_STAGING_DURATION_AND_DURATION"))

            if not allow_wildcard and any(any(m.code.use_wildcard() for m in p.materials) for p in process_entries):
                error.append(_("ERROR_REQUIRE_NON_WILDCARD_CODE"))

            in_completed_material = map(lambda p: filter(lambda m: not m.code.is_completed(), p.materials), process_entries)
            in_completed_material = list(chain(*in_completed_material))
            if len(in_completed_material) > 0:
                error.append(_("ERROR_REQUIRE_COMPLETED_CODE") + "\n" + "\n".join(map(lambda o: str(o.code), in_completed_material)))

            def validate_each_process(p):
                def validate_each_material(m):
                    # Added exception rule for Plating Solution (#63)
                    return m.counter is not None and (True if m.code.matched('###017') else all(v != 0 for v in m.quantity))
                return all(validate_each_material(m) for m in p.materials)

            if not all(validate_each_process(p) for p in process_entries):
                error.append(_("ERROR_REQUIRE_QTY_UOM"))

            def verify_material_uom(m):
                # Validate, missing counter is not this function concern. So skip it.
                if m.counter is None:
                    return
                key = str(m.code)
                uom = m.counter
                if key not in material_uom_map:
                    # Not Found: Find in Existing material - Add it to uom_map
                    try:
                        existing_material = MaterialMaster.get(key)
                        # Register existing's material counter
                        material_uom_map[key] = existing_material.uom
                    except BadParameterError:
                        # Not Found in Existing Material, add existing pair it to uom_map
                        material_uom_map[key] = uom
                if not material_uom_map[key].convertible(uom):
                    error.append(_("ERROR_BAD_UOM %(material)s") % {'material': key})

            # Perform material uom verification
            for p in process_entries:
                for m in p.materials:
                    verify_material_uom(m)

            # No violation over the materials ordering
            source_indices = dict((int(p.id), idx) for idx, p in enumerate(process_entries))

            def violated(idx, src):
                return src not in source_indices or idx < source_indices[src]   # invalid source or backward

            if any(any(violated(idx, int(s)) for s in p.source) for idx, p in enumerate(process_entries)):
                error.append(_("ERROR_CANNOT_CREATE_BACKWARD_PROCESS"))

            return error

        # Master modeling
        if validate_master_modeling:
            master_modeling = validate_process(self.process.master_modeling)
            # Check last process for master modeling
            try:
                master_models = self.process.extract_master_models()
                if len(master_models) == 0:
                    master_models.append(_("ERROR_NO_MAKE"))
            except ValidationError as e:
                master_modeling.append(str(e))

        # Production
        if validate_production:
            production = validate_process(self.process.sample_creation)

        # Pricing
        if validate_pricing:
            # Costing =
            #   at least 1 has_cost
            #   each process:
            #       either material or process has_cost.
            def has_cost(p):
                return p.labor_cost > 0 or (0 < len(p.materials) and all(m.cost > 0 for m in p.materials))

            if not any(has_cost(p) for p in self.process.sample_creation + self.process.master_modeling):
                pricing.append(_("ERROR_REQUIRE_COST"))

        # Report errors
        return drawing, master_modeling, production, pricing, general

    def invoke_set_status(self, user, status, verbose=False):
        # Update permission checks
        if status in [ApprovableDoc.APPROVED]:
            self.assert_permission(user, "write", "approve")
            user.can("material+write", None, True)
        else:
            self.assert_permission(user, "write")

        # Update status per form validation
        if status in [ApprovableDoc.WAITING_FOR_APPROVAL]:
            self.validate_data(allow_wildcard=True, throw=True, validate_4_pillars=True)

            def after_touched():
                signals.design_submitted.send(self.__class__, instance=self)

            self.after_touched = after_touched
        elif status in [ApprovableDoc.APPROVED]:
            self.validate_data(allow_wildcard=False, throw=True, validate_4_pillars=True)

            # loop through all materials and create the MasterMaterial if necessary
            # Extract all materials to be used, unique them.

            def after_touched():
                # FIXME: Use Signal instead
                self._try_commit_uid(user)
                self._convert_to_material_master(user, verbose)

            self.after_touched = after_touched
        elif status in [ApprovableDoc.NEW]:
            # New,
            self.validate_data(allow_wildcard=True, throw=True,
                               validate_4_pillars=False,
                               validate_product_code_completed=False,
                               validate_product_code_comparing=False)
        else:
            self.validate_data(allow_wildcard=True, throw=True, validate_4_pillars=False)
        self.status = status
        return self

    def _convert_to_material_master(self, author, verbose=False):
        """
        Take current Design object - extract schematics and distribute it to multiple material masters

        1. Expand: go through 'master_modeling' + 'sample_creation', expand all hidden process, inject 'generated' WIP
        2. For 'master_modeling' - capture the output by 'last make of last _TASK_STOPPER process'
        3. For 'sample_creation' - will be attributed to MaterialMaster by given self.code + self.rev_id

        * Prepare 'Schematic' object and call material.update_schematic(schematic_object)

        :param author:
        :return:
        """
        def v(level, message):
            if verbose:
                print "[ ] %s%s" % ("\t"*level, message)
            return

        def _mm_factory(stock_code, uom, has_schematic=False):
            return MaterialMaster.factory(stock_code,
                                          uom,
                                          MaterialMaster.INTERNAL if has_schematic else MaterialMaster.EXTERNAL,
                                          author)

        v(0, "Converting '%s' to material_master - started" % self.code)
        v(1, "Author=%s" % author)
        # Check if master_modeling's schematic exist or not?
        v(1, "Check master_modeling schematic")
        ProhibitedError.raise_if(len(self.process.master_modeling) <= 0, "Failed: Empty master model schematic")

        v(1, "Extracting master_models ...")
        # master_model, class=StockCode
        # uom, class=UOM
        # processes, class=[SchematicEntry]
        for master_model_code, uom, processes in self.process.extract_master_models():
            v(2, "Converting '%s' to Master Model - started" % master_model_code)
            v(3, "Make sure all materials exists")

            # Make sure that we have all processes' materials have been created.
            # call factory on all required material (BoM)
            for p in processes:
                for m in p.materials:
                    _mm_factory(m.code, m.counter)

            def normalize(size_index, size_code):
                # update code
                # sanity check
                if not isinstance(master_model_code, codes.StockCode):
                    raise ValidationError(_("ERR_CANNOT_NORMALIZE_MASTER_MODEL_CODE_SHOULD_BE_STOCK_CODE"))

                # update code
                new_code_str = master_model_code.code + size_code
                new_code = codes.StockCode(new_code_str)

                # map normalize process
                return new_code, map(lambda p: p.normalize(size_index), processes)

            # prepare for loop
            loop_sizes = self.size if len(self.size) > 0 else [LOV.ensure_exist(LOV.RANDD_SIZE, LOV.RANDD_SIZE_NONE)]

            # replacement list
            replacements = []

            # loop through all sizes
            for size_index, size_code in enumerate(loop_sizes):
                # prepare sized_master_model_code, normalized_processes
                if size_code is not None:
                    sized_master_model_code, normalized_processes = normalize(size_index, size_code)
                else:
                    sized_master_model_code = master_model_code
                    normalized_processes = processes

                # Really build the Mold Material Master
                master_model_mm = _mm_factory(sized_master_model_code, uom, True)

                # Update Material Master Schematic
                sch = Schematic.factory(master_model_mm.object_id, self.rev_id, author)
                sch.conf_size = [size_code] if size_code is not None else []
                sch.source = self
                sch.schematic = normalized_processes
                sch.expand()
                sch.touched(author)
                master_model_mm.update_schematic(author, sch, {'message': _("EM_SCHEMATIC_UPDATED_FROM_DESIGN")})
                v(3, "Schematic synced %s rev=%s object_id=%s" % (master_model_code, self.rev_id, master_model_mm.object_id))

                if self.size > 0:
                    replacements.append(sized_master_model_code)

            # Handling size expansion within 'self.process.sample_creation'
            # Replace consumption material in self.process.sample_creation with new material_codes
            if len(replacements) > 0:
                # traverse through sample_creation, and replace if applicable
                map(lambda p: p.try_propagate(master_model_code, replacements), self.process.sample_creation)

        # For production, make sure we have all material master for each material
        v(2, "Converting '%s' to finished product - started" % self.code)

        # Check if sample_creation is not empty.
        v(3, "Check master_modeling schematic")

        # Sanity check
        if len(self.process.sample_creation) <= 0:
            raise ProhibitedError(_("ERR_EMPTY_PRODUCTION_SCHEMATIC"))

        # Make sure all material exists
        for p in self.process.sample_creation:
            list(_mm_factory(m.code, m.counter) for m in p.materials)

        # Factory out the Material Master for Final Product (180)
        mm = MaterialMaster.factory(codes.StockCode(self.code),
                                    self.counter,
                                    MaterialMaster.INTERNAL,
                                    author)

        # Building a schematic
        sch = Schematic.factory(mm.object_id, self.rev_id, author)
        sch.conf_size = self.size
        sch.source = self
        sch.schematic = self.process.sample_creation
        sch.expand(is_production=True)
        sch.touched(author)
        mm.update_schematic(author, sch, {'message': _("EM_SCHEMATIC_UPDATED_FROM_DESIGN")})

        # raise ProhibitedError("ALL DONE")

    def _try_commit_uid(self, user):
        # If not yet paired, let's pair it
        if not self.is_paired:
            DesignUID.commit(self.rev_unique_id, self.code, user)

    def touched(self, user, **kwargs):
        super(Design, self).touched(user, **kwargs)
        if self.after_touched is not None and hasattr(self.after_touched, '__call__'):
            self.after_touched()

    class Meta:
        collection_name = 'design'
        require_permission = True
        permission_write = ["approve", None]


# Signal listener
@receiver(signals.design_submitted, sender=Design)
def create_approve_design_task(sender, instance, **kwargs):
    print("instance=%s" % instance)
    # FIXME
