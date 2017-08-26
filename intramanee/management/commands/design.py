__author__ = 'peat'
from django.core.management.base import BaseCommand
from intramanee.common.models import IntraUser
from intramanee.common.codes import StockCode
from intramanee.common.documents import ApprovableDoc
from intramanee.randd.documents import Design
from optparse import make_option


class Command(BaseCommand):
    help = "design --approve=[design_object_id]\n" \
        "design --validate=[design_object_id]"

    option_list = BaseCommand.option_list + (
        make_option('--approve',
                    action='store',
                    dest='approve_design_code',
                    default=None,
                    help='Approve specific [material_code](r[revision_id])'),
        make_option('--validate',
                    action='store',
                    dest='validate_design_code',
                    default=None,
                    help='Validate specific [material_code](r[revision_id])'),
    )

    def handle(self, **options):
        approve_design_code = options.get('approve_design_code', None)
        validate_design_code = options.get('validate_design_code', None)

        if validate_design_code:
            print "Validating ... \"%s\"\n" % validate_design_code
            design = Design.lookup(validate_design_code, True)
            if design is None:
                raise ValueError('Invalid design UID')
            errors = design.validate_for_errors()
            print errors

        if approve_design_code:
            print "Trying to approve ... \"%s\"\n" % approve_design_code
            design = Design.lookup(approve_design_code, True)
            if design is None:
                raise ValueError('Invalid design UID %s' % approve_design_code)

            u = IntraUser.robot()
            design.invoke_set_status(u, status=ApprovableDoc.APPROVED, verbose=True)
            design.touched(u)
            print "DONE"
