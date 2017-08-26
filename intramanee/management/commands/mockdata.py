__author__ = 'peat'
from django.core.management.base import BaseCommand
from optparse import make_option
from bson import ObjectId


class Command(BaseCommand):
    help = "Automatically generate Mock Data\n" \
           "Option:\n" \
           "--pur : include purchasing\n" \
           "--pro : include production\n" \
           "--des #number : include design\n" \
           "--sal #number : include sales\n" \
           "Leaving all arguments above blank to include all\n" \
           "--delete : delete mock data"

    option_list = BaseCommand.option_list + (
        make_option('--delete',
                    action='store_true',
                    dest='delete',
                    default=False,
                    help='Delete mock data instead of creating it'),
        make_option('--pur',
                    action='store_true',
                    dest='pur',
                    default=False,
                    help='Create purchasing mock data'),
        make_option('--pro',
                    action='store_true',
                    dest='pro',
                    default=False,
                    help='Create production mock data'),
        make_option('--sal',
                    action='store',
                    type='int',
                    dest='sal',
                    default=False,
                    help='Create sales mock data'),
        make_option('--des',
                    action='store',
                    type='int',
                    dest='des',
                    default=False,
                    help='Create design mock data'),
        make_option('--group',
                    action='store_true',
                    dest='group',
                    default=False,
                    help='Group tasks'),
        make_option('--sto',
                    action='store',
                    type='string',
                    dest='sto',
                    default=None,
                    help='Populate stock - "mat,mat,qty"'),
        make_option('--ass',
                    action='store',
                    type='string',
                    dest='ass',
                    default=None,
                    help='Assign testman to all operation - "obj_id, obj_id, ..."'),
        make_option('--rel',
                    action='store',
                    type='string',
                    dest='rel',
                    default=None,
                    help='Release production order - "ord, ord, ..."'),
        )

    def handle(self, **options):
        from intramanee.production.test_documents import ProductionTest
        from intramanee.production import documents as prod
        from intramanee.purchasing.test_documents import PurchasingTest
        from intramanee.randd.test_documents import TestDesign
        from intramanee.sales.test_documents import SalesTest
        from intramanee.production.documents import ProductionGroupedOperation as group

        all_module = False
        if options['pur'] == options['pro'] and options['pro'] == options['sal'] and options['sal'] == options['des'] \
                and options['des'] == options['group'] and options['group'] == options['sto'] \
                and options['ass'] == options['sto'] and options['ass'] == options['rel']:
            all_module = True

        production = ProductionTest()
        purchasing = PurchasingTest()
        design = TestDesign()
        sales = SalesTest()

        if options['delete']:
            if all_module or options['pro']:
                production.tearDownClass()
            if all_module or options['pur']:
                purchasing.tearDownClass()
            if all_module or options['des']:
                design.tearDownClass()
            if all_module or options['sal']:
                sales.tearDownClass()
        else:
            # Setup
            if all_module or options['pro']:
                ProductionTest.setUpClass()
                production.setUp()
                production.test_group_operation(testing=False)
            if all_module or options['pur']:
                PurchasingTest.setUpClass()
                purchasing.setUp()
                purchasing.test_create_purchase_requisition(testing=False)
            if all_module or options['des']:
                design.setUpClass()
                design.setUp()
                design.test_mock_design(number=(options['des'] or 10))
            if all_module or options['sal']:
                sales.setUpClass()
                sales.setUp()
                sales.test_mock_sales_order(number=(options['sal'] or 10))
            if all_module or options['group']:
                ProductionTest.setUpClass()
                production.setUp()
                group.automate_group(production.tester, True)
            if options['sto']:
                args = [x.strip() for x in options['sto'].split(',')]
                quantity = int(args.pop(-1))
                ProductionTest.utils.prepare_raw_mat_stock(production.tester, raw_mat=args, quantity=quantity)
            if options['ass']:
                args = [ObjectId(x.strip()) for x in options['ass'].split(',')]
                print("getting order: %s" % args)
                orders = prod.ProductionOrder.manager.find(0, 0, {'_id': {'$in': args}})
                print("Found order: %s" % orders)

                if orders:
                    def pop_and_assign(o):
                        def assign(op):
                            op.assignee = production.tester
                            op.touched(production.tester)
                            print("saving operation: %s" % op.object_id)

                        o.populate('operation')
                        map(assign, o.operation)

                    map(pop_and_assign, orders)
            if options['rel']:
                args = [ObjectId(x.strip()) for x in options['rel'].split(',')]
                print("getting order: %s" % args)
                orders = prod.ProductionOrder.manager.find(0, 0, {'_id': {'$in': args}})
                print("Found order: %s" % orders)

                if orders:
                    def release_order(o):
                        o.release(production.tester)
                        print("releasing order: %s" % o.object_id)

                    map(release_order, orders)
