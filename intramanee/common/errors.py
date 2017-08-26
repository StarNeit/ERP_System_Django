__author__ = 'peat'

from django.utils.translation import ugettext as _


class IntraError(StandardError):

    def __init__(self, status_code, *errors):
        super(IntraError, self).__init__(*errors)
        self.status_code = status_code

    def content(self):
        args = self.args[0]
        if len(args) == 1 and isinstance(args[0], basestring):
            return args[0]
        return args


class ResourceNotFoundError(IntraError):
    """
    Database record cannot be found
    """

    def __init__(self, message):
        super(ResourceNotFoundError, self).__init__(404, message)


class InsufficientPermissionError(IntraError):
    """
    Permission is required, which can be amended by override
    """

    def __init__(self, required_permission):
        """

        :param basestring|[basestring] required_permission:
        """
        required_permission = ",".join(required_permission) if isinstance(required_permission, list) else required_permission
        super(InsufficientPermissionError, self).__init__(401, "P/%s" % required_permission)


class ValidationError(IntraError):
    """
    Business Logic Validation Error
    """

    def __init__(self, *errors):
        super(ValidationError, self).__init__(403, *errors)

    @staticmethod
    def raise_if(check, *errors):
        if check:
            raise ValidationError(*errors)


class ProhibitedError(IntraError):
    """
    Rules violation, (Developer or Bad Intention Error)
    """

    def __init__(self, message):
        super(ProhibitedError, self).__init__(404, message)

    @staticmethod
    def raise_if(check, message):
        if check:
            raise ProhibitedError(message)


class BadParameterError(IntraError):
    """
    Developer fault
    """

    def __init__(self, message):
        super(BadParameterError, self).__init__(500, message)

    @classmethod
    def required(cls, parameter_name):
        return cls(_("ERR_PARAMETER_IS_REQUIRED: %(parameter_name)s") % {
            'parameter_name': parameter_name
        })

    @classmethod
    def std(cls, require_type=None):
        """
        Factory method, return template error name and codes

        :param require_type:
        :return:
        """
        if require_type:
            raise cls(_("ERR_REQUIRED_CLASS: %(class_spec)s" % {"class_spec": require_type}))

    @staticmethod
    def raise_if(check, message):
        if check:
            raise BadParameterError(message)
