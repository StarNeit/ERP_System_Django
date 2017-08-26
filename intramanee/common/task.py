__author__ = 'wasansae-ngow'

from intramanee.settings import CONF_ROOT
from intramanee.models import IntraUser
from intramanee.common.errors import ProhibitedError
import ConfigParser
import re
import operator


class SchematicDummy(object):

    # Action patterns
    _extend_pattern = re.compile(r'^([+-])(\d+)')

    def __init__(self, id, task_code, source=[], processed=False, ref=False):
        self.id = id
        self.task_code = task_code
        self.source = source
        self.destination = []          # Will be updated by ExtendExpander.expand()
        self.processed = processed
        self.ref = ref

    def __repr__(self):
        return "%s: %s stat=%s %s" % (self.id, self.task_code, "done" if self.processed else "need_work", self.source)

    def __eq__(self, other):
        return other.id == self.id if isinstance(other, SchematicDummy) else False

    @classmethod
    def is_forward_action(cls, action):
        """

        :param action:
        :return: (tuple of boolean, integer) boolean indicate if action is forward, integer represent the task to take.
        """
        m = cls._extend_pattern.match(action)
        if not m:
            raise ProhibitedError('SchematicDummy unable to extend %s' % action)

        return m.groups()[0] == '+', int(m.groups()[1])

    def extend(self, action):
        is_forward, int_task_code = self.is_forward_action(action)

        if is_forward:
            return self.extend_forward(int_task_code)
        else:
            return self.extend_backward(int_task_code)

    def extend_forward(self, new_task_code):
        """
        Create a new dummy, place it between (this) and its destination.

        Update all destinations with new source (new_dummy)
        Update (this) with new destination (new_dummy)

        :param new_task_code:
        :return: (SchematicDummy?)
        """
        # Check before expand if there is destination that already match requested new_task_code
        if any(a.task_code == new_task_code for a in self.destination):
            return None
        # generate new_id
        if len(self.destination) > 0:
            new_id = (float(self.destination[0].id) + float(self.id)) / 2.0
        else:
            new_id = float(self.id) + 1.0
        # set up output buffer
        o = SchematicDummy(new_id, new_task_code, source=[self])
        # calculate destination
        o.destination = self.destination
        # For each destination, update sources
        for dest in self.destination:
            dest.source = map(lambda s: s if s != self else o, dest.source)
        self.destination = [o]
        return o

    def extend_backward(self, new_task_code):
        """
        Create a new dummy, place it between (this) and its source

        Update all sources with new destination (new_dummy)
        Update (this) with new source (new_dummy)

        :param new_task_code:
        :return: (SchematicDummy?)
        """
        # Check before expand if there is source that already match requested new_task_code
        if any(a.task_code == new_task_code for a in self.source):
            return None
        # generate new_id
        if len(self.source) > 0:
            new_id = (float(self.source[0].id) + float(self.id)) / 2.0
        else:
            new_id = float(self.id) - 1.0
        # setup output buffer
        o = SchematicDummy(new_id, new_task_code, source=self.source)
        o.destination = [self]
        for src in self.source:
            src.destination = map(lambda s: s if s != self else o, src.destination)
        self.source = [o]
        return o


class TaskExpander(object):
    """
    Base Class for all expander
    """

    def __init__(self, actions=None):  # action string
        self.actions = actions or []

    @staticmethod
    def populate(context):
        # - Update destination for all dummy in context
        indices = dict((d.id, d) for d in context)
        for dummy in context:
            for src in dummy.source:
                indices[src].destination.append(dummy)
            dummy.source = map(lambda s: indices[s], dummy.source)
        return context

    @staticmethod
    def normalise(context):
        # - reduce the value to simple integers
        for i, dummy in enumerate(context):
            dummy.id = str(i+1)

        # - normalise it back
        for dummy in context:
            dummy.source = map(lambda s: s.id, dummy.source)
            dummy.destination = map(lambda s: s.id, dummy.destination)
        return context


class ForkExpander(TaskExpander):
    """
    Fork Expander
    """
    BACKWARD_PATTERN = re.compile(r'^:\((\d+)-(\d+)\)')
    FORWARD_PATTERN = re.compile(r'^\((\d+)-(\d+)\):')

    # Static rules
    registries = {}

    def __init__(self, task_start, task_end, **kwargs):
        super(ForkExpander, self).__init__(**kwargs)
        self.task_start = int(task_start)
        self.task_end = int(task_end)

        if self.task_end <= self.task_start:
            raise ProhibitedError("ForkExpander expected task_end > task_start, task_end=%s, task_start=%s" % (task_end, task_start))

    @classmethod
    def register(cls, task_start, task_end, actions):
        key = "%s-%s" % (task_start, task_end)
        if key in cls.registries:
            cls.registries[key].actions.extend(actions)
        else:
            o = cls(task_start, task_end, actions=actions)
            cls.registries[key] = o

    def is_between(self, task_code):
        return self.task_start <= int(task_code) <= self.task_end

    def walk(self, dummy):
        """

        :param dummy:
        :return: terminal dummy (actions should be taken after these dummies)
        """
        dummy.processed = True
        valid_children = filter(lambda du: self.is_between(du.task_code), dummy.destination)
        if len(valid_children) > 0:
            r = map(lambda c: self.walk(c), valid_children)
            return reduce((lambda o, v: o + v), r, [])
        # streak terminate here
        return [dummy]

    @classmethod
    def expand(cls, context):
        # - do fork
        for rule in cls.registries.values():
            # For Fork, all dummy must be processed through every rules
            for dummy in context:
                dummy.processed = False

            # Filter to find first dummy to start with
            for dummy in context:
                if dummy.processed or not rule.is_between(dummy.task_code):
                    continue
                # need to walk through first, so that they are all marked as processed.
                dummy.processed = True
                terminal_dummies = rule.walk(dummy)
                # Apply terminal dummy
                for action in rule.actions:
                    is_forward, _ = SchematicDummy.is_forward_action(action)
                    if is_forward:
                        for td in terminal_dummies:
                            new_dummy = td.extend(action)
                            if new_dummy is None:
                                print "Action = %s" % action
                                print "Td = %s" % terminal_dummies
                                for a in context:
                                    print a
                                raise ProhibitedError("Failed to backward extend action=%s on dummy=%s" % (action, td))
                            new_dummy.processed = True
                            idx = context.index(td)
                            context.insert(idx+1, new_dummy)
                    else:
                        new_dummy = dummy.extend(action)
                        if new_dummy is None:
                            raise ProhibitedError("Failed to forward extend action=%s on dummy=%s" % (action, dummy))
                        new_dummy.processed = True
                        idx = context.index(dummy)
                        context.insert(idx, new_dummy)
        return context

    def __repr__(self):
        return "ForkExpander [%s - %s] = %s" % (self.task_start, self.task_end, self.actions)


class ExtendExpander(TaskExpander):
    """
    Extend Expander
    """
    rules = {}

    def __init__(self, watching_task_code, **kwargs):
        super(ExtendExpander, self).__init__(**kwargs)
        self.cond = watching_task_code

        # self register
        ExtendExpander.rules[watching_task_code] = self

    @classmethod
    def factory(cls, watching_task_code):
        if watching_task_code not in cls.rules:
            return cls(watching_task_code)
        return cls.rules[watching_task_code]

    @classmethod
    def expand(cls, context, **kwargs):       # [ SchematicDummy ]
        # - get all task unprocessed tasks
        for dummy in context:
            dummy.processed = False

        action_queue = []
        if kwargs.pop('is_production', False) and cls.rules['L'] and len(context) > 0:
            # Find 'L' location ...
            # Suppose to be last operation
            action_queue = [('L', cls.rules['L'].actions)]

        w = 0
        while True:
            # Build action queue first
            for i, dummy in filter(lambda p: not p[1].processed, enumerate(context)):
                w += 1
                # apply action
                if dummy.task_code in cls.rules:
                    action_queue.append((i, cls.rules[dummy.task_code].actions))
                dummy.processed = True

            # backwardly apply sorted action queue
            for idx, actions in reversed(sorted(action_queue, lambda a, b: b < a)):
                if idx == 'L':
                    idx = len(context)-1
                dummy = context[idx]
                for action in actions:
                    new_dummy = dummy.extend(action)
                    if new_dummy is not None:
                        if float(new_dummy.id) < float(dummy.id):
                            context.insert(idx, new_dummy)
                            idx += 1
                        else:
                            context.insert(idx+1, new_dummy)

            # reset action_queue
            action_queue = []

            if len(context) == w:
                break

        return context


class Task(object):

    tasks = {}
    expansion = {
        'fork': []
    }  # Indexed expansion tasks of TaskExpander

    def __init__(self, task_code, task_label, task_standard_time, task_batch, task_batch_setup_time, continue_on_break,
                 fixed_duration, gen_mode, gen_arguments, batch_logic, staging_duration, batch_init):
        self.code = task_code
        self.label = task_label
        self.standard_time = task_standard_time
        self.batch = task_batch
        self.batch_setup_time = task_batch_setup_time
        self.continue_on_break = continue_on_break
        self.fixed_duration = fixed_duration
        self.gen = (gen_mode, gen_arguments)
        self.batch_logic = batch_logic
        self.staging_duration = staging_duration
        self.batch_init = batch_init

        # If expansion, index to Task.expansion
        if gen_mode[0] == 'E':
            backward_fork_match = ForkExpander.BACKWARD_PATTERN.match(gen_arguments)
            forward_fork_match = ForkExpander.FORWARD_PATTERN.match(gen_arguments)
            if backward_fork_match is not None:
                m = backward_fork_match.groups()
                Task.expansion['fork'].append(ForkExpander.register(m[0], m[1], actions=["-%s" % task_code]))
            elif forward_fork_match is not None:
                m = forward_fork_match.groups()
                Task.expansion['fork'].append(ForkExpander.register(m[0], m[1], actions=["+%s" % task_code]))
            else:
                if gen_arguments == 'L':
                    ExtendExpander.factory('L').actions.append("+%s" % task_code)
                else:
                    for key in map(int, gen_arguments.split(",")):
                        action = ("+%s" if key > 0 else "-%s") % task_code
                        ExtendExpander.factory(abs(key)).actions.append(action)

    def __repr__(self):
        return unicode(self.label)

    def __eq__(self, other):
        if isinstance(other, int):
            return self.code == other
        if isinstance(other, basestring):
            return self.code == int(other)
        return self.code == other.code if isinstance(other, Task) else False

    def get_batch_initiator(self):
        """

        :return: None if task is not a batch initiator, otherwise return Tuple of type (i,o) and group_key if exists.
        """
        m = re.compile('^(i|o_(.+))$').match(self.batch_init)
        if m is None:
            return None, None
        return m.group(1)[0], m.group(2)

    def is_batch_closure(self, group_key):
        return ('c_%s' % group_key) == self.batch_init

    def default_assignee(self):
        return TaskGroup.factory(("%s" % self.code)[:3])

    def serialize(self):
        return {
            'code': self.code,
            'label': self.label,
            'standard_time': float(self.standard_time),
            'batch': 1 if self.batch else 0,
            'batch_setup_time': self.batch_setup_time,
            'continue_on_break': 1 if self.continue_on_break else 0,
            'fixed_duration': 1 if self.fixed_duration else 0,
            'gen': list(self.gen),
            'batch_logic': self.batch_logic,
            'staging_duration': self.staging_duration,
            'batch_ini': self.batch_init
        }

    @classmethod
    def expand(cls, context, **kwargs):
        is_verbose = kwargs.pop('verbose', False)

        def verbose(title):
            if is_verbose:
                print title
                for c in context:
                    print("\t%s" % c)
        verbose("Started")
        TaskExpander.populate(context)
        verbose("Populated")
        ForkExpander.expand(context)
        verbose("Forked")
        ExtendExpander.expand(context, **kwargs)
        verbose("Extended")
        TaskExpander.normalise(context)
        verbose("Normalised")
        return context

    @classmethod
    def get_task_list(cls):
        return [v.code for k, v in cls.tasks.iteritems()]

    @staticmethod
    def has(task_code):
        return (int(task_code) if isinstance(task_code, basestring) else task_code) in Task.tasks

    @staticmethod
    def filter(key):
        output = []
        sorted_tasks = sorted(Task.tasks.items(), key=operator.itemgetter(0))
        for k, v in sorted_tasks:
            if bool(re.match(str(key), str(k), re.IGNORECASE)):
                output.append(v)
                continue
            if bool(re.match(str(key), str(v.label), re.IGNORECASE)):
                output.append(v)
                continue

        return output

    @classmethod
    def remove_test_id(cls):
        for k, v in cls.tasks.iteritems():
            IntraUser.objects.get_by_natural_key(str(v.code)+'999XYZ').delete()

    @staticmethod
    def factory(task_code):
        """
        Build and return requested Task object

        :param task_code:
        :return: requested Task Object
        :raise: KeyError if task_code is not found, Exception if
        """
        if not Task.has(task_code):
            raise KeyError('Unknown task_code: "%s"' % task_code)

        return Task.tasks[int(task_code) if isinstance(task_code, basestring) else task_code]


class TaskGroup(object):

    groups = {}

    def __init__(self, code, label):
        self.code = code
        self.label = label

    def __repr__(self):
        return unicode(self.label)

    @classmethod
    def has(cls, group_code):
        return (int(group_code) if isinstance(group_code, basestring) else group_code) in cls.groups

    def get_tasks(self):
        return Task.filter(self.code)

    def serialize(self):
        return {
            'code': self.code,
            'label': self.label,
        }

    @classmethod
    def filter(cls, key):
        output = []
        sorted_groups = sorted(cls.groups.items(), key=operator.itemgetter(0))
        for k, v in sorted_groups:
            if bool(re.match(str(key), str(k), re.IGNORECASE)):
                output.append(v)
                continue
            if bool(re.match(str(key), str(v.label), re.IGNORECASE)):
                output.append(v)
                continue

        return output

    @classmethod
    def factory(cls, group_code):
        """

        :param group_code:
        :return:
        """
        if not cls.has(group_code):
            raise KeyError('Input group "%s" is not defined' % group_code)

        return cls.groups[int(group_code) if isinstance(group_code, basestring) else group_code]

# Read Task from config file
conf = ConfigParser.ConfigParser()
conf.read("%s/task.ini" % CONF_ROOT)

for code in conf.sections():
    item_list = conf.items(code)
    d = dict(item_list)

    u = Task(int(d['code']), d['label'], float(d['stdtime']), int(d['batch']), d['batchsetuptime'],
             d['break'] == "True", d['fixed_duration'] == "True", d['gen'], d['arg'], d['batchlogic'],
             int(d['staging_duration']), d['batch_init'])
    Task.tasks[int(d['code'])] = u

    group_code = d['code'][:3]
    if not TaskGroup.has(group_code):
        r = TaskGroup(int(group_code), group_code)
        TaskGroup.groups[int(group_code)] = r
