from datetime import datetime
import logging

LOG = logging.getLogger('intraman_app')


def NOW():
    """
    :return datetime:
    """
    return datetime.now()


def get_or_none(model, *args, **kwargs):
    try:
        return model.objects.get(*args, **kwargs)
    except model.DoesNotExist:
        return None


def print_verbose(verbose, message):
    if verbose:
        print message


def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    reverse = dict((value, key) for key, value in enums.iteritems())
    enums['reverse_mapping'] = reverse
    return type('Enum', (), enums)


def int2base(x, b=36, alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    'convert an integer to its string representation in a given base'
    if b < 2 or b > len(alphabet):
        if b == 64:  # assume base64 rather than raise error
            alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        else:
            raise AssertionError("int2base base out of range")
    if isinstance(x, complex):  # return a tuple
        return int2base(x.real, b, alphabet), int2base(x.imag, b, alphabet)
    if x <= 0:
        if x == 0:
            return alphabet[0]
        else:
            return '-' + int2base(-x, b, alphabet)
    # else x is non-negative real
    rets = ''
    while x > 0:
        x, idx = divmod(x, b)
        rets = alphabet[idx] + rets
    return rets


class DictDiffer(object):
    """
    Calculate the difference between two dictionaries as:
    (1) items added
    (2) items removed
    (3) keys same in both but changed values
    (4) keys same in both and unchanged values
    """
    def __init__(self, current_dict, past_dict):
        self.current_dict, self.past_dict = current_dict, past_dict
        self.set_current, self.set_past = set(current_dict.keys()), set(past_dict.keys())
        self.intersect = self.set_current.intersection(self.set_past)

    def added(self):
        return self.set_current - self.intersect

    def removed(self):
        return self.set_past - self.intersect

    def changed(self):
        return set(o for o in self.intersect if self.past_dict[o] != self.current_dict[o])

    def unchanged(self):
        return set(o for o in self.intersect if self.past_dict[o] == self.current_dict[o])

    def elaborate(self):
        return {
            'added': {k: self.current_dict[k] for k in self.added()},
            'removed': {k: self.past_dict[k] for k in self.removed()},
            'changed': {k: {'from': self.past_dict[k], 'to': self.current_dict[k]} for k in self.changed()}
            }
