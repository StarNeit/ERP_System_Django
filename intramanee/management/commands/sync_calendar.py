__author__ = 'peat'
from django.core.management.base import NoArgsCommand


class Command(NoArgsCommand):
    help = "Automatically sync calendar from sources"

    def handle(self, **options):
        from intramanee.common.calendar import documents as doc
        doc.OffHours.sync(verbose=True)
