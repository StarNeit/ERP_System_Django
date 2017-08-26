__author__ = 'bank'

from django.utils.translation import ugettext as _


class Resource(object):
    STATUS_AVAILABLE = 0
    STATUS_UNAVAILABLE = 1

    RESOURCE_STATUSES = (
        (STATUS_AVAILABLE, _('RESOURCE_STATUS_AVAILABLE')),
        (STATUS_UNAVAILABLE, _('RESOURCE_STATUS_UNAVAILABLE')),
    )

    def set_unavailable(self):
        raise NotImplementedError("Must be implemented")

    def set_available(self):
        raise NotImplementedError("Must be implemented")
