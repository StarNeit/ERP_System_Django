from intramanee.common.documents import Docs, Doc
from intramanee.stock import documents as stock_doc
from intramanee.production import documents as prod_doc
from intramanee.common.location import Location
from intramanee.common.errors import BadParameterError
from intramanee.common.models import IntraUser
from intramanee.task import signals as task_signals

from django.utils.translation import ugettext as _


class ReturningAPI:
    TYPE_STAGED_FROM_CLERK_AUX_TASK = "staged_from_clerk_aux_task"
    TYPE_STAGED_IN_INVENTORY_CONTENT = "staged_inventory_content"
    TYPE_WIP_FROM_PRODUCTION_ORDER = "production_wip"

    def __init__(self):
        pass

    @classmethod
    def create_material_requisition(cls, user, doc_no_or_cost_center, material_list):
        """

        :param basestring doc_no_or_cost_center:
        :param [dict] material_list:
        :return:
        """
        # TODO: Add CostCenter Support
        if isinstance(doc_no_or_cost_center, Doc):
            doc = doc_no_or_cost_center
        else:
            doc = Docs.of_doc_no(doc_no_or_cost_center)

        # Check cases for ProductionOrderOperation
        if isinstance(doc, prod_doc.ProductionOrderOperation):
            # Validate ProductionOrderOperation status
            if not prod_doc.ProductionOrderOperation.STATUS_RELEASED <= doc.status <= prod_doc.ProductionOrderOperation.STATUS_PARTIAL_CONFIRMED:
                raise BadParameterError(_("ERR_INVALID_PRODUCTION_ORDER_OPERATION_STATUS"))

            def patch_weight(a):
                a['weight'] = 0
                return a

            # Call Bank's method
            # prepare material_list
            task_signals.task_repeat.send(cls, parent=doc, components=map(patch_weight, material_list))

    @classmethod
    def return_candidates(cls, doc_no):
        """
        Identify if given doc_no is a supported document type.

        Retrieve the candidate list of materials that will be returned.

        Process:

            Storage fire an API request for ``return_candidates``

            Method interpret the ``doc_no`` and return the list of possible ``revert_content`` along with its
            interpretation types.

                CASE A: StoreAuxTask - with parent_task.status >= confirmed.

                    When to use?: Task has been confirmed and there are materials left after the process.

                    Meaning that the (parent) task has already been processed and confirmed. The returning content
                    should be all whatever in STAGED instance.

                    Upon return, the Complete list of items should be issued, and saved, no additional document reverted
                    in this regard.

                    List of: [
                        - type: "staged_inventory_content"
                        - doc_no: whatever given
                        - System gather items from ``inventory_content`` API.
                    ]

                CASE B: StoreAuxTask - with parent_task.status < confirmed.

                    When to use?: The Task has not yet been completed and is requested to return its materials
                    (pause, or anything)

                    Meaning that the (parent) task has not yet been started. The returning content should be those
                    STAGED recently staged items.

                    Upon return, ClerkAuxTask should be degraded, and so StoreAuxTask respectively.

                    List of: [
                        - type: "staged_from_clerk_aux_task"
                        - doc_no: whatever given
                        - System gather items from ``list_components`` method and returned to Caller.
                    ]

                CASE C: JOB TAG (Production Order)

                    When to use?: Same like case B - task is requested to returns its materials.

                    Meaning that the user wish to return some portion of associated JOB TAG. User should be presented
                    with choices to return all their items based on their selectable tasks.

                        List of: [
                            - type: "production_wip"
                            - doc_no: <task_doc_no>
                            - System examine the Edge Task, asking for WIP that may be created.
                        ]

        :param basestring doc_no:
        :return: [{type, doc_no, return_list: [{TaskComponent.as_json()}]},..]
        """
        # Retrieve documents based on what it is given
        if isinstance(doc_no, Doc):
            doc = doc_no
        else:
            doc = Docs.of_doc_no(doc_no)

        # Case StoreAuxTask
        if isinstance(doc, prod_doc.StoreAuxTask):
            if doc.status <= prod_doc.StoreAuxTask.STATUS_CONFIRMED:
                raise BadParameterError(_("ERR_INVALID_DOCUMENT_STATUS: %(doc_no)s") % {
                    'doc_no': doc_no
                })
            doc.populate('parent_task')
            if doc.parent_task:
                if prod_doc.UserActiveTask.probe(operation=doc.parent_task) is not None:
                    raise BadParameterError(_("ERR_INVALID_STATE_TASK_IN_PROGRESS: %(doc_no)s") % {
                        'doc_no': doc_no
                    })

                if doc.parent_task.status >= prod_doc.ProductionOrderOperation.STATUS_CONFIRMED:
                    staged_components = stock_doc.InventoryContent.query_content(ref_doc=doc.parent_task,
                                                                                 location=Location.factory('STAGING'))
                    return [{
                        "type": cls.TYPE_STAGED_IN_INVENTORY_CONTENT,
                        "object_id": str(doc.object_id),
                        "doc_no": doc.doc_no,
                        "return_list": map(lambda a: {
                            # As TaskComponent.as_json()
                            'material': str(a.material),
                            'quantity': a.quantity,
                            'uom': stock_doc.MaterialMaster.get(a.material).uom.code,
                            'revision': None,
                            'weight': a.weight,
                            'size': None
                        }, staged_components)
                    }]
                else:
                    staged_components = doc.list_components()
                    return [{
                        "type": cls.TYPE_STAGED_FROM_CLERK_AUX_TASK,
                        "object_id": str(doc.object_id),
                        "doc_no": doc.doc_no,
                        "return_list": map(lambda a: {
                            # As TaskComponent.as_json()
                            'material': str(a.material),
                            'quantity': a.quantity,
                            'uom': stock_doc.MaterialMaster.get(a.material).uom.code,
                            'revision': None,
                            'weight': a.weight,
                            'size': None
                        }, staged_components)
                    }]
            raise BadParameterError(_("ERR_UNKNOWN_PARENT_TASK_FOR: %(doc_no)s") % {
                'doc_no': doc_no
            })
        elif isinstance(doc, prod_doc.ProductionOrder):
            return map(lambda a: {
                "type": cls.TYPE_WIP_FROM_PRODUCTION_ORDER,
                "object_id": str(a.object_id),
                "doc_no": a.doc_no,
                "return_list": [{
                    'material': 'WIP-CANDIDATE',  # WIP CANDIDATE ...
                    'quantity': a.get_confirmable_quantity(),
                    'uom': 'pc',
                    'revision': doc.revision,
                    'weight': 0,
                    'size': doc.size
                }]
            }, doc.get_edge_operations())

        raise BadParameterError(_("ERR_UNSUPPORTED_DOCUMENT_TYPE: %(document_type)s" % {
            'document_type': str(type(doc))
        }))

    @classmethod
    def return_materials(cls, user, doc_no, mode, return_list):
        """
        Returning Materials - please see #return_candidates for more information.

        :param IntraUser user:
        :param basestring doc_no:
        :param basestring mode:
        :param list[dict[basestring, basestring]] return_list:
        :return:
        """

        # Retrieve documents based on what it is given
        doc = Docs.of_doc_no(doc_no)

        # Validate input,
        # Extract source to compare
        current_list = []
        ref_doc = None
        from_ref_doc = None
        if mode in [cls.TYPE_STAGED_IN_INVENTORY_CONTENT, cls.TYPE_STAGED_FROM_CLERK_AUX_TASK] and isinstance(doc, prod_doc.StoreAuxTask):
            o = cls.return_candidates(doc_no)
            current_list = list(o[0]['return_list'])
            doc.populate('parent_task')
            doc.parent_task.populate('ref_doc')
            ref_doc = doc.parent_task.ref_doc
            from_ref_doc = doc.parent_task
        elif mode == cls.TYPE_WIP_FROM_PRODUCTION_ORDER and isinstance(doc, prod_doc.ProductionOrderOperation):
            doc.populate('ref_doc')
            current_list = [{
                'material': 'WIP-CANDIDATE',
                'quantity': doc.get_confirmable_quantity(),
                'uom': doc.ref_doc.uom,
                'revision': None,
                'size': None,
                'weight': 0,
            }]
            ref_doc = doc.ref_doc
        else:
            # Unsupported case
            raise BadParameterError(_("ERR_UNSUPPORTED_DOCUMENT_TYPE: %(document_type)s") % {
                'document_type': str(type(doc))
            })

        # prepare movement based on return_list
        # Sanity check
        if len(current_list) != len(return_list):
            raise BadParameterError(_("ERR_UNEQUAL_SIZE_OF_RETURN_LIST: %(expected_size)s != $(actual_size)s") % {
                'expected_size': len(current_list),
                'actual_size': len(return_list)
            })

        # index list for ease of comparison
        current_list = dict(map(lambda a: (str(a['material']), a), current_list))
        return_list = dict(map(lambda a: (str(a['material']), a), return_list))

        movements = []
        entries = []
        lost_entries = []
        movement_type = None
        lost_movement_type = None
        # From STAGED => STORE
        # From STAGED => LOST & FOUND
        for key, value in current_list.iteritems():
            lost = value['quantity'] - return_list[key]['quantity']

            # NOTE: For WIP scenario
            if key == 'WIP-CANDIDATE':
                # init Goods receipt by-product for WIP to STORE
                # TODO: value for WIP to be fixed later with proper logic. now using static 543210.
                movement_type = stock_doc.InventoryMovement.GR_BP
                user.can(stock_doc.InventoryMovement.ACTION_WRITE(), movement_type, throw=True)

                # NOTE: Generate WIP Stock code
                wip_material = doc.ref_doc.material.create_wip(doc.task.code)

                # NOTE: Create material master from stock code
                stock_doc.MaterialMaster.factory(wip_material, uom=doc.ref_doc.uom, procurement_type=stock_doc.MaterialMaster.INTERNAL, author=user)

                current_list[key]['material'] = wip_material
                current_list[key]['uom'] = stock_doc.MaterialMaster.get(doc.ref_doc.material).uom.code
                entries.append(stock_doc.InventoryMovementEntry.factory(material=wip_material,
                                                                        quantity=return_list[key]['quantity'],
                                                                        location=Location.factory('STORE').code,
                                                                        weight=return_list[key]['weight'],
                                                                        value=543210))

                if lost > 0:
                    # if lost is found, init Goods receipt lost and found for WIP to STORE
                    lost_movement_type = stock_doc.InventoryMovement.GR_LT
                    lost_entries.append(stock_doc.InventoryMovementEntry.factory(material=wip_material,
                                                                                 quantity=return_list[key]['quantity'],
                                                                                 location=Location.factory('LOST').code,
                                                                                 weight=return_list[key]['weight'],
                                                                                 value=543210))
            # NOTE: For STAGING scenario
            else:
                # init Stock transfer production to location for STAGING to STORE
                movement_type = stock_doc.InventoryMovement.ST_PL
                user.can(stock_doc.InventoryMovement.ACTION_WRITE(), movement_type, throw=True)
                entries.extend(stock_doc.InventoryMovementEntry.transfer_pair_factory(material=value['material'],
                                                                                      quantity=return_list[key]['quantity'],
                                                                                      from_location=Location.factory('STAGING').code,
                                                                                      to_location=Location.factory('STORE').code,
                                                                                      from_ref_doc=from_ref_doc))

                if lost > 0:
                    # if lost is found, init Stock transfer lost and found for STAGING to STORE retaining ref_doc
                    lost_movement_type = stock_doc.InventoryMovement.ST_LT
                    lost_entries.extend(stock_doc.InventoryMovementEntry.transfer_pair_factory(material=value['material'],
                                                                                               quantity=return_list[key]['quantity'],
                                                                                               from_location=Location.factory('STAGING').code,
                                                                                               to_location=Location.factory('LOST').code,
                                                                                               from_ref_doc=from_ref_doc,
                                                                                               to_ref_doc=from_ref_doc))
        if not entries:
            raise ValueError("Nothing to return")

        movement = stock_doc.InventoryMovement.factory(movement_type, list(entries), ref_doc=ref_doc)
        movements.append(movement)

        if lost > 0:
            user.can(stock_doc.InventoryMovement.ACTION_WRITE(), lost_movement_type, throw='challenge')
            movement = stock_doc.InventoryMovement.factory(lost_movement_type, list(lost_entries), ref_doc=ref_doc)
            movements.append(movement)

        if movements:
            # validate first then touched
            map(lambda x: x.validate(user=user), movements)

            # NOTE: create a new pair of store & clerk with different parent depending on mode
            if mode == cls.TYPE_STAGED_FROM_CLERK_AUX_TASK:
                task_signals.task_repeat.send(cls, parent=doc.parent_task, components=[v for i, v in current_list.iteritems()])
            if mode == cls.TYPE_WIP_FROM_PRODUCTION_ORDER:
                task_signals.task_repeat.send(cls, parent=doc, components=[v for i, v in current_list.iteritems()])
                doc.ready(user)
            
            map(lambda x: x.touched(user), movements)

        return len(movements)
