__author__ = 'peat'
from django.core.management.base import BaseCommand
from intramanee.common.task import Task
from intramanee.common.models import IntraUser


class Command(BaseCommand):
    help = "Automatically generate test users based on Tasks"

    def handle(self, **options):
        for k, v in Task.tasks.iteritems():
            u = IntraUser.objects.create_user(str(v.code)+'999XYZ', 'Mr.'+v.label, 'nope')
            u.permissions = ['task+write@'+str(v.code)]
            u.save()
            print "Created user %s with permission=%s" % (u, u.permissions)
        print "DONE %s users created" % len(Task.task)
