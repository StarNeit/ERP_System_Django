__author__ = 'peat'
from django.core.management.base import BaseCommand
from intramanee.common.models import IntraUser
from intramanee.common.documents import _objectid
from intramanee.task.documents import TaskDoc
from optparse import make_option
import re


class Command(BaseCommand):
    help = "Task Operation Toolbox\n" \
           "Option:\n" \
           "--op [task_operation_doc_id] - load task document.\n" \
           "--do [release] - execute.\n"

    option_list = BaseCommand.option_list + (
        make_option('--op',
                    action='store',
                    dest='task_operation_doc_id',
                    default=None,
                    help='Load task document with object_id'),
        make_option('--do',
                    action='store',
                    dest='action',
                    default=None,
                    help='Perform specific action to loaded task (release)')
    )

    def handle(self, **options):
        op_id = options.get('task_operation_doc_id', None)
        action = options.get('action', None)
        if not op_id:
            raise ValueError('--op is required.')

        tasks = TaskDoc.manager.find(cond={
            '_id': _objectid(op_id)
        })
        if len(tasks) < 1:
            raise ValueError('Failed to load task=%s' % op_id)
        task = tasks[0]

        if action == "release":
            print "Releasing %s" % op_id
            task.release(user=IntraUser.robot())
        else:
            raise ValueError('Unknown action: %s' % action)
