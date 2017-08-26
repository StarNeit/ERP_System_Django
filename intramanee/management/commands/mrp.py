__author__ = 'peat'
from django.core.management.base import BaseCommand
from intramanee.bot.service import Robot
from intramanee.common.models import IntraUser
from intramanee.common.codes import StockCode
from optparse import make_option
import re


class Command(BaseCommand):
    help = "Initialize MRP\n" \
           "Option:\n" \
           "--all - run all materials in system.\n" \
           "--mat material_code - run MRP on specific material.\n"

    option_list = BaseCommand.option_list + (
        make_option('--mat',
                    action='store',
                    dest='material',
                    default=None,
                    help='Running MRP on specific [material_code](r[revision_id](-[size]))'),
    )

    def handle(self, **options):
        mat = options.get('material', None)
        if mat:
            pattern = re.compile(r'^([A-Z0-9-]+)(r(\d+))?(-([A-Z]+))?')
            matches = pattern.match(mat)

            if not matches:
                raise ValueError('Invalid material code.')

            groups = matches.groups()
            mat = [(StockCode(groups[0]), int(groups[2]), groups[4])]

        Robot.run_mrp(IntraUser.robot(), mat, wait=True)
