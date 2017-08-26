from intramanee.production.documents import ProductionOrder, ProductionOrderOperation
from intramanee.purchasing.documents import PurchaseRequisition
from intramanee.stock.documents import MaterialMaster, InventoryContent, Schematic
from intramanee.sales.documents import SalesOrder
from intramanee.common import errors as err, codes, documents as doc
from intramanee.common.utils import LOG
from datetime import datetime, timedelta
from bson import ObjectId
import multiprocessing
import traceback


class MRPSessionExecutionRecordEntry(doc.FieldSpecAware):
    marker = doc.FieldDateTime(none=False)
    quantity = doc.FieldNumeric()
    ref_docs = doc.FieldAnyDoc()
    original = doc.FieldBoolean(default=False)
    remark = doc.FieldString(none=True)

    @classmethod
    def create(cls, marker, quantity, ref_docs, original, remark=None):
        o = MRPSessionExecutionRecordEntry()
        o.marker = marker
        o.quantity = quantity
        o.ref_docs = ref_docs
        o.original = original
        o.remark = remark
        return o

    @staticmethod
    def initial_balance_marker():
        return datetime.fromtimestamp(0)

    @staticmethod
    def safety_stock_marker():
        return datetime.fromtimestamp(1)

    def __repr__(self):
        name = self.marker.strftime('%Y-%m-%d %H:%M')
        if self.marker == MRPSessionExecutionRecordEntry.initial_balance_marker():
            name = "Initial Balance"
        elif self.marker == MRPSessionExecutionRecordEntry.safety_stock_marker():
            name = "Safety Stock"
        return "[%16s] %s%4s" % (name, '-' if self.quantity < 0 else '+', abs(self.quantity))

    def __cmp__(self, other):
        if self.marker == other.marker:
            return cmp(self.quantity, other.quantity)
        return cmp(self.marker, other.marker)


class MRPSessionExecutionRecord(doc.FieldSpecAware):
    # Sorting
    affinity = doc.FieldNumeric(default=0, none=False)                  # type: int
    # ID
    material = doc.FieldTypedCode(codes.StockCode, none=False)          # type: codes.StockCode
    revision = doc.FieldNumeric(default=None)                           # type: int
    size = doc.FieldString(default=None)                                # type: basestring
    # Context
    material_master = doc.FieldSpec(MaterialMaster, transient=True)     # type: MaterialMaster
    mrp_session_id = doc.FieldObjectId(transient=True)                  # type: ObjectId
    # Calculation Buffer
    entries = doc.FieldList(doc.FieldNested(MRPSessionExecutionRecordEntry))
    created_supplies = doc.FieldList(doc.FieldNested(MRPSessionExecutionRecordEntry))
    # Snapshot meta from material_master
    reorder_point = doc.FieldNumeric(default=0, none=False)
    lead_time = doc.FieldNumeric(default=0, none=False)
    procurement_type = doc.FieldString(none=False)
    mrp_type = doc.FieldString(max_length=1)

    def create_demand_groups(self):
        lot_size = self.material_master.lot_size
        if lot_size in [MaterialMaster.LZ_LOT_FOR_LOT, MaterialMaster.LZ_MAX_STOCK_LEVEL]:

            def lot_for_lot():
                r = []
                for a in self.entries:
                    if a.marker.date() in [MRPSessionExecutionRecordEntry.initial_balance_marker(), MRPSessionExecutionRecordEntry.safety_stock_marker()]:
                        r.append(a)
                    else:
                        if len(r) > 0:
                            yield None, r
                            r = []
                        yield a.marker, [a]
            return lot_for_lot()
        elif lot_size in [MaterialMaster.LZ_DAILY, MaterialMaster.LZ_MONTHLY, MaterialMaster.LZ_WEEKLY]:

            def create_timed_lot_size(lz):

                def _group_id(dt):
                    if lz == MaterialMaster.LZ_DAILY:
                        return dt.date()
                    elif lz == MaterialMaster.LZ_MONTHLY:
                        return "%04d%02d" % (dt.year, dt.month)
                    elif lz == MaterialMaster.LZ_WEEKLY:
                        return "%04d%02d" % (dt.year, dt.date().isocalendar()[1])
                    else:
                        raise err.ProhibitedError('Invalid lot_size value=%s' % lot_size)

                def timed_lot_size():
                    group_point = None
                    r = []
                    for e in self.entries:
                        if group_point is None:
                            # do not yield the automatic ones
                            group_point = _group_id(e.marker)
                            r.append(e)
                        elif group_point != _group_id(e.marker):
                            yield group_point, r
                            # renew
                            group_point = _group_id(e.marker)
                            r = [e]
                        else:
                            r.append(e)
                    if len(r) > 0:
                        yield group_point, r
                return timed_lot_size
            return create_timed_lot_size(lot_size)()
        raise err.ProhibitedError('Unknown lot_size %s' % lot_size)

    def populate(self, path):
        if path == 'material_master' and self.material_master is None and self.material is not None:
            key = str(self.material)
            mms = MaterialMaster.manager.find(cond={
                'code': key
            }, pagesize=1)
            if len(mms) == 0:
                raise err.ProhibitedError('Material Master %s is missing' % key)
            self.material_master = mms[0]       # type: MaterialMaster
            self.mrp_type = self.material_master.mrp_type
            self.reorder_point = 0 if self.material_master == MaterialMaster.MRP else self.material_master.reorder_point
            self.lead_time = self.material_master.gr_processing_time
            self.procurement_type = self.material_master.procurement_type
        else:
            super(MRPSessionExecutionRecord, self).populate(path)
        return self

    def delete_weak_supplies(self, verbose=None):
        """
        Logic
        =====
        Disregard all unwanted supply (Previously generated ProductionOrder/PurchaseRequisition)

            - ProductionOrder
                * mrp_session != None
                * mrp_session != self.mrp_session
                * status = OPEN
                * material = focal_material

            - PurchaseRequisition
                * status = OPEN
                * mrp_session != None
                * mrp_session != self.mrp_session
                * PR generated by MRP has only 1 children, lookup focal_material within PurchaseRequisition items

        :param verbose: (sub routine to print verbose message)
        :return:
        """
        ProductionOrder.manager.delete(verbose=False if verbose is None else verbose, cond={
            'status': ProductionOrder.STATUS_OPEN,
            'mrp_session': {'$nin': [None, self.mrp_session_id]},
            'material': str(self.material),
            'revision': self.revision,
            'size': self.size
        })
        PurchaseRequisition.manager.delete(verbose=False if verbose is None else verbose, cond={
            'status': PurchaseRequisition.STATUS_OPEN,
            'mrp_session': {'$nin': [None, self.mrp_session_id]},
            'items': {
                '$elemMatch': {
                    'material': str(self.material),
                    'revision': self.revision,
                    'size': self.size
                }
            }
        })

    def gather(self, verbose=None):
        self.entries = []
        self._gather_demands()
        demand_count = len(self.entries)
        if verbose:
            verbose("demand_collected=%s" % len(self.entries), "i", level=1)
        self._gather_supplies()
        if verbose:
            verbose("supply_collected=%s" % (len(self.entries) - demand_count), "i", level=1)
        self.entries = sorted(self.entries)
        self.created_supplies = []

    def create_supply(self, shortage, due, session, ref_doc=None, remark=None, verbose=None):
        """
        Modify add supply to sequence, and return replenished amount

        Replenished amount is ...
            shortage + lot_size_arg if lot_size = MaterialMaster.LZ_MAX_STOCK_LEVEL
            shortage if otherwise

        Supply Sequence can be broken into lots using lot_size_max

        Each sub_lot_size must be greater or equals to lot_size_min

        lead_time is taken into consideration as a due

        due is given as exact moment when it will be used, therefore it will be offset by 1 hours before
        such exact hours. (Please, Consider exclude OffHours as optional feature)

        :param int shortage:
        :param due:
        :param MRPSession session:
        :param ref_doc:
        :param basestring remark:
        :param verbose:
        :return: (amount replenished)
        """
        if shortage == 0:
            return 0

        if self.lead_time is None or self.reorder_point is None:
            raise err.ProhibitedError('Cannot create supply without lead_time')
        offset_due = due - timedelta(hours=1, days=self.lead_time)

        # Compute optimal lot_size
        procurement_type = self.material_master.procurement_type
        lots = []
        lot_size_max = self.material_master.lot_size_max
        lot_size_min = self.material_master.lot_size_min
        # lot_size_arg = self.material_master.lot_size_arg
        # Capped with lot_size_max
        if lot_size_max is not None and lot_size_max > 0:
            lot_count = int(shortage) / int(lot_size_max)
            supplied = 0
            for i in xrange(0, lot_count-1):
                lots.append(lot_size_max)
                supplied += lot_size_max
            lots.append(shortage-supplied)
        else:
            lots = [shortage]

        # Push to lot_size_min
        if lot_size_min is not None and lot_size_min > 0:
            lots = map(lambda a: max(lot_size_min, a), lots)

        # Actually create supply
        references = []
        if procurement_type == MaterialMaster.INTERNAL:
            # ProductionOrder

            # Need to honour scrap percentage here
            scrap_percentage = self.material_master.scrap_percentage
            references.extend(map(lambda a: ProductionOrder.factory(self.material,
                                                                    self.revision,
                                                                    self.size,
                                                                    offset_due,
                                                                    a,
                                                                    session.issued_by,
                                                                    ref_doc=ref_doc,
                                                                    remark=remark,
                                                                    scrap_percentage=scrap_percentage,
                                                                    mrp_session_id=session.object_id), lots))
        elif procurement_type == MaterialMaster.EXTERNAL:
            # PurchaseRequisition
            # FIXME: Consider adding remark/ref_doc to the output document.
            references.extend(map(lambda a: PurchaseRequisition.factory(self.material,
                                                                        self.revision,
                                                                        self.size,
                                                                        offset_due,
                                                                        a,
                                                                        session.issued_by,
                                                                        mrp_session_id=session.object_id), lots))

        verbose("due=%s lots=%s remark=%s" % (due, lots, remark), "S", 1)
        return reduce(lambda o, a: o + a, lots, 0)

    def _gather_demands(self):
        demands = []
        based_material = str(self.material)
        # (0) 'SafetyStock' - create as Demand of Session's Sequence
        demands.append(MRPSessionExecutionRecordEntry.create(
            marker=MRPSessionExecutionRecordEntry.safety_stock_marker(),
            quantity=-self.material_master.safety_stock,
            ref_docs=None,
            original=True,
            remark="Safety Stock"
        ))

        def is_focal_material(o):
            return o.material == based_material and o.revision == self.revision and o.size == self.size

        # (1) SalesOrder, (status = OPEN, material=seq.material)
        sales_orders = SalesOrder.manager.find(cond={
            'status': SalesOrder.STATUS_OPEN,
            'items': {
                '$elemMatch': {
                    'material': based_material,
                    'revision': self.revision,
                    'size': self.size
                }
            }
        })

        for sales_order in sales_orders:
            for item in filter(is_focal_material, sales_order.items):
                o = MRPSessionExecutionRecordEntry.create(
                    marker=sales_order.delivery_date,
                    quantity=item.uom.convert(self.material_master.uom, -item.quantity),
                    ref_docs=sales_order,
                    original=True,
                    remark="/".join(filter(lambda a: a is not None and len(a) > 0, [sales_order.remark, item.remark]))
                )
                demands.append(o)

        # (2) ProductionOrderOperations
        # BoM of Tasks
        tasks = ProductionOrderOperation.manager.find(cond={
            'materials': {
                '$elemMatch': {
                    'material': based_material,
                    'revision': self.revision,
                    'size': self.size
                }
            }
        })
        for task in tasks:
            for item in filter(is_focal_material, task.materials):
                o = MRPSessionExecutionRecordEntry.create(
                    marker=task.planned_start,
                    quantity=item.uom.convert(self.material_master.uom, -item.quantity),
                    ref_docs=task,
                    original=True
                )
                demands.append(o)

        self.entries.extend(demands)

    def _gather_supplies(self):
        """
        Get supplies from non-OPEN production orders, purchase orders, stock_content

        exclude [OPEN production order, purchase requisition, purchase order ...]
        :return:
        """
        supplies = []
        based_material = str(self.material)
        # (0) Stock Content
        amount = InventoryContent.get_value(self.material)
        supplies.append(MRPSessionExecutionRecordEntry.create(
            marker=MRPSessionExecutionRecordEntry.initial_balance_marker(),
            quantity=amount,
            ref_docs=None,
            original=True,
            remark="Current Stock Level"
        ))
        # (1) Production Order, unconfirmed production order ...
        production_orders = ProductionOrder.manager.find(cond={
            'status': {'$lt': ProductionOrder.STATUS_CONFIRMED},
            'material': based_material,
            'revision': self.revision,
            'size': self.size
        })
        for po in production_orders:
            o = MRPSessionExecutionRecordEntry.create(
                marker=po.planned_end,
                quantity=po.uom.convert(self.material_master.uom, po.supply_quantity()),
                ref_docs=po,
                original=True
            )
            supplies.append(o)

        def is_focal_material(o):
            return o.material == based_material and o.revision == self.revision and o.size == self.size

        # (2) Purchase Requisition (partially converted - consider as supply)
        purchase_requisitions = PurchaseRequisition.manager.find(cond={
            'status': {'$lte': PurchaseRequisition.STATUS_PARTIAL_CONVERTED},
            'items': {
                '$elemMatch': {
                    'material': based_material,
                    'revision': self.revision,
                    'size': self.size
                }
            }
        })
        # Translate purchase_requisitions => Supply
        for pr in purchase_requisitions:
            for item in filter(is_focal_material, pr.items):
                o = MRPSessionExecutionRecordEntry.create(
                    marker=item.delivery_date,
                    quantity=item.open_quantity if item.uom is None else item.uom.convert(self.material_master.uom, item.open_quantity),
                    ref_docs=pr,
                    original=True
                )
                supplies.append(o)

        # (3) Purchase Orders ...
        # TODO: Query Purchase Order = PurchaseOrder already exist, but not finished. (Wait for complete of Document)

        self.entries.extend(supplies)

    def records(self):
        """
        Merged generators

        :return:
        """
        def next_demands():
            for d in self.demands:
                yield d

        def next_supplies():
            for s in self.supplies:
                yield s

        def next_or_none(generator):
            try:
                return next(generator)
            except StopIteration:
                return None

        demands = next_demands()
        supplies = next_supplies()
        next_d = None
        next_s = None
        while True:
            next_d = next_or_none(demands) if next_d is None else next_d
            next_s = next_or_none(supplies) if next_s is None else next_s
            # compare for next one
            # -> Escape case
            if next_d is None and next_s is None:
                break
            # compare case
            if next_d is not None and next_s is not None:
                # compare which one is lesser
                if next_d > next_s:
                    current = next_s
                    next_s = None
                else:
                    current = next_d
                    next_d = None
            elif next_d is None:
                current = next_s
                next_s = None
            else:
                current = next_d
                next_d = None
            yield current

        for o in (self.demands + self.supplies):
            yield o

    def __cmp__(self, other):
        return other.affinity - self.affinity

    def __repr__(self):
        return "SEQ %6s ~> %s revision=%s size=%s" % (self.affinity, self.material, self.revision, self.size)


class MRPSession(doc.Doc):
    """
    Contains report of MRP session ran
    """
    start = doc.FieldDateTime(none=False)
    end = doc.FieldDateTime(none=True)
    issued_by = doc.IntraUser()
    sequence = doc.FieldList(doc.FieldNested(MRPSessionExecutionRecord))
    target_materials = doc.FieldList(doc.FieldTuple(doc.FieldTypedCode(codes.StockCode), doc.FieldNumeric(none=True), doc.FieldString(none=True)), none=True)
    errors = doc.FieldList(doc.FieldString())

    processes = {}
    skip_indices = {}

    def __init__(self, object_id=None):
        super(MRPSession, self).__init__(object_id)
        if object_id is None:
            self.sequence_cache = {}
            self.sequence = []
            self.target_materials = None

    def load(self):
        super(MRPSession, self).load()
        # update sequence cache
        self.sequence_cache = dict(map(lambda v: (str(v.material), v), self.sequence))

    def run(self):
        self._begin()
        try:
            def report(message, group=None, level=0):
                if group is None:
                    LOG.debug("%s%s" % ("\t" * level, message))
                else:
                    LOG.debug("%s%s: %s" % ("\t" * level, group, message))

            report("\nBuilding Run Sequences")
            self._build_run_sequences()
            report("\nInitial sequence" % self.sequence)
            if len(self.sequence) == 0:
                report("(No sequence initialized)")
            else:
                for s in self.sequence:
                    report(s, "i", 1)
                report("")

            # Run sequence; Execute mrp
            for seq in self.sequence:

                # Read Material
                # => update reorder_point, lead_time, lot_size -> making 'create_supply()'
                seq.populate('material_master')

                # Extract attributes
                reorder_point = seq.reorder_point
                procurement_type = seq.material_master.procurement_type
                lot_size = seq.material_master.lot_size
                mrp_type = seq.material_master.mrp_type

                report("Started %s" % seq)
                report("reorder_point=%s" % reorder_point, "i", 1)
                report("lot_size=%s" % lot_size, "i", 1)
                report("supply_type=%s" % ('PurchaseRequisition' if procurement_type == MaterialMaster.EXTERNAL else 'ProductionOrder'), 'i', 1)

                # Type = 'MRP' or 'Reorder', if 'No MRP' = Skip
                if mrp_type not in [MaterialMaster.MRP, MaterialMaster.REORDER]:
                    raise err.ProhibitedError('Unable to process MRP Sequence %s - incorrect MRP type' % seq.material)

                # Delete weak supply
                seq.delete_weak_supplies(verbose=report)

                # Gathering Demand/Supply
                seq.gather(verbose=report)
                report("-", "i", 1)

                # Go through Demand/Supply in chronological order
                # Try to resolve negative balance situation.
                current = 0
                for group_id, a in seq.create_demand_groups():
                    first_marker = a[0].marker
                    # print demand
                    report("marker=%s group_id=%s" % (first_marker, group_id), "O", 1)
                    # e = MRPSessionExecutionRecordEntry
                    for e in a:
                        current += e.quantity
                        report("%s\t= %s" % (e, current), level=2)
                    # For Every demand group, we need to produce a supply for it.
                    # TODO: Each demand group might have a supply within that will in turn misled the calculation.
                    if current <= seq.reorder_point:
                        reorder_amount = current - seq.reorder_point

                        # MAX_STOCK_LEVEL
                        if lot_size == MaterialMaster.LZ_MAX_STOCK_LEVEL:
                            max_stock_level = seq.material_master.lot_size_arg
                            if max_stock_level <= 0 or max_stock_level is None:
                                raise err.BadParameterError('Invalid lot_size_arg for material %s' % seq.material)
                            reorder_amount = current - max_stock_level

                        # IF supply is needed
                        if reorder_amount < 0:
                            replenished = seq.create_supply(-reorder_amount, first_marker, self,
                                                            ref_doc=e.ref_docs,
                                                            remark=e.remark,
                                                            verbose=report)
                            current += replenished
                            # create sequence handle this replenishing
                            # just for printing sake
                            rec = MRPSessionExecutionRecordEntry.create(
                                marker=first_marker,
                                quantity=replenished,
                                ref_docs=e.ref_docs,
                                remark=e.remark,
                                original=False
                            )
                            seq.created_supplies.append(rec)
                            report("%s\t= %s %s" % (rec, current, rec.remark), level=2)
                    else:
                        report("no shortage found", "i", 1)
                report("DONE\n", "i", level=1)

            self._enclose()
        except Exception as e:
            LOG.error(traceback.format_exc())
            self._enclose(False, [str(e)])

    def _build_run_sequences(self):
        """
        Populate sequence variables

        :return:
        """
        initial_affinity = 200000
        # Add manually inserted material first
        if self.target_materials is not None and len(self.target_materials) > 0:
            map(lambda t: self._add_sequence(t[0], t[1], t[2], initial_affinity), self.target_materials)

        # Query production order
        # Walk down each production order schematic, extract required materials
        # - any materials that is referenced pull these from material master instead.
        cond = {
            'status': {'$lt': ProductionOrder.STATUS_CONFIRMED}
        }
        if self.target_materials is not None and len(self.target_materials) > 0:
            cond['$or'] = map(lambda t: {'material': str(t[0]), 'revision': t[1], 'size': t[2]}, self.target_materials)
        orders = ProductionOrder.manager.find(cond=cond)

        # Extract schematic
        # populate/update affinity values
        for order in orders:
            seq = self._add_sequence(order.material, order.revision, order.size, initial_affinity)
            if seq is None:
                continue
            new_affinity = seq.affinity - 1
            order.populate('operation')
            for op in order.operation:
                for po_comp in filter(lambda m: m.quantity > 0, op.materials):
                    self._add_sequence(po_comp.material, po_comp.revision, po_comp.size, new_affinity)

        self.sequence = sorted(self.sequence)

    def _add_sequence(self, stock_code, revision, size, affinity):
        """
        Nested building running sequences.

        :param stock_code:
        :param affinity:
        :return:
        """
        key = "%sr%s-%s" % (str(stock_code), str(revision), str(size))
        mm = MaterialMaster.get(stock_code)

        # Verify if order.material has type != 'No MRP'
        if key not in self.skip_indices:
            # Cache
            self.skip_indices[key] = (mm.mrp_type == MaterialMaster.NO_MRP)

        if self.skip_indices[key]:   # Skip due to NO_MRP
            return None

        if key not in self.sequence_cache:
            LOG.debug("[+]\tSequence key=%s" % key)
            o = MRPSessionExecutionRecord()
            o.affinity = affinity
            o.revision = revision
            o.size = size
            o.material = stock_code
            o.mrp_session_id = self.object_id
            self.sequence_cache[key] = o
            self.sequence.append(o)

            # discover its own schematic from its default revision
            if mm.procurement_type == MaterialMaster.INTERNAL:
                sch = Schematic.of(mm.object_id, revision)
                if sch is None:
                    raise ValueError('No schematic found for %s rev%s (material=%s)' % (stock_code, revision, mm.object_id))
                for sch_entry in sch.schematic:
                    for mat in sch_entry.materials:
                        if any(q > 0 for q in mat.quantity):
                            stock_code = mat.code
                            bom_mm = MaterialMaster.factory(mat.code)
                            if bom_mm.procurement_type is MaterialMaster.EXTERNAL or bom_mm.schematic is None:
                                self._add_sequence(stock_code, None, None, affinity-1)
                            else:
                                bom_mm.populate('schematic')
                                self._add_sequence(stock_code, bom_mm.schematic.rev_id, size, affinity-1)
        else:
            self.sequence_cache[key].affinity = min(self.sequence_cache[key].affinity, affinity)
        r = self.sequence_cache[key]

        return r

    def _begin(self):
        self.start = datetime.now()
        self.end = None
        self.errors = []
        self.save()
        self._log(doc.Event.CREATED)

    def _enclose(self, ok=True, errors=None):
        self.start = self.start
        self.end = datetime.now()
        if errors is not None:
            self.errors.extend(errors)
        self.save()
        self._log(doc.Event.FINISHED if ok else doc.Event.CANCELLED)

    def _log(self, what, **kwargs):
        kwargs.update({
            'against': self
        })
        doc.Event.create(what, self.issued_by, **kwargs)

    @classmethod
    def kickoff(cls, user, materials=None):
        """
        Create new MRP session, extracting existing data

        :param materials - list of tuple [(stock_code, revision, size)]
        :return: MRPSession Object
        """
        # Check is_running
        if cls.running_session() is not None:
            raise err.ProhibitedError('There is MRP Session running.')

        if not isinstance(materials, (type(None), list)):
            raise err.ProhibitedError('Bad value - materials must be list of tuple size of 3')

        session = MRPSession()
        session.target_materials = materials
        session.issued_by = user

        key = str(session.object_id)
        LOG.debug("Running MRP Session=%s" % key)
        t = multiprocessing.Process(target=MRPSession.run, args=(session,))
        cls.processes[key] = t
        t.start()
        return session

    @classmethod
    def running_session(cls):
        found = cls.manager.find(pagesize=1, cond={
            'end': None
        })
        return found[0] if len(found) > 0 else None

    @classmethod
    def wait(cls):
        for t in cls.processes.values():
            t.join()

    class Meta:
        collection_name = 'mrp-session'
        require_permission = True
