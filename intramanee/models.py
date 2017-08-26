__author__ = 'peat'

from django.contrib.auth import models as auth_model
from django.db import models
from djangotoolbox.fields import ListField
from intramanee.common.permissions import create_user_permissions as user_perm, permission_center
from intramanee.common.errors import BadParameterError, InsufficientPermissionError, ProhibitedError
from intramanee.common.resource import Resource
from django.utils.translation import ugettext as _
from bson import ObjectId
import re


PATTERN_TYPE = type(re.compile(''))


class IntraUserManager(auth_model.BaseUserManager):

    def create_user(self, code, first_name, password=None, group='officer'):
        user = self.model(code=code, first_name=first_name)
        user.set_password(password)
        user.group = group
        # Apply predefined rules
        if 'stock' == group:
            permissions = user_perm(stock='crud')
        else:
            permissions = []
        user.permissions = permissions
        user.save()
        return user

    def create_superuser(self, code, first_name, password):
        user = self.model(code=code, first_name=first_name, password=password, is_superuser=True, is_staff=True)
        user.set_password(password)
        user.save()
        return user


class IntraUser(auth_model.AbstractBaseUser, Resource):
    code = models.CharField(max_length=80, unique=True)
    first_name = models.CharField(max_length=40)
    last_name = models.CharField(max_length=40, null=True)
    doc = models.DateTimeField(auto_now_add=True)
    doe = models.DateTimeField(auto_now=True)

    permissions = ListField()
    group = models.CharField(max_length=20)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    is_bot = models.BooleanField(default=False)

    USERNAME_FIELD = 'code'
    REQUIRED_FIELDS = ['first_name', 'group']

    availability = models.DecimalField(decimal_places=0, max_digits=1, default=Resource.STATUS_AVAILABLE)

    objects = IntraUserManager()

    override_permission = None
    """:type : Authentication"""

    def is_same_user(self, user_or_object_id):
        if isinstance(user_or_object_id, basestring):
            return user_or_object_id == self.id
        elif isinstance(user_or_object_id, ObjectId):
            return str(user_or_object_id) == self.id
        elif isinstance(user_or_object_id, IntraUser):
            return self.id == user_or_object_id.id
        return self == user_or_object_id

    def set_available(self):
        self.availability = self.STATUS_AVAILABLE

    def set_unavailable(self):
        self.availability = self.STATUS_UNAVAILABLE

    def get_full_name(self):
        return self.first_name + " " + self.last_name

    def get_short_name(self):
        return self.code

    def is_authenticated(self):
        return True

    def can(self, action_or_regex, arg=None, throw=False):
        """
        Module's permission validation

        :param basestring action_or_regex:
        :param basestring arg:
        :param bool|basestring throw: either boolean or 'challenge'
        :return bool:
        :raise InsufficientPermissionError:
        :raise BadParameterError:
        """
        def check():
            if self.is_bot:
                return True
            # Prepare permission available to compare.
            permission_info = self.permissions
            # If we have override_permission, add it in.
            if self.override_permission is not None:
                permission_info.extend(self.override_permission.target_permissions)
            # Start comparing
            # Simple string case
            if isinstance(action_or_regex, basestring):
                action = ("%s@%s" % (action_or_regex, arg)) if arg is not None else action_or_regex
                if action not in permission_center:
                    # Check for non-existed permission will always returns True
                    return True
                return action in permission_info
            # Regex case
            elif isinstance(action_or_regex, PATTERN_TYPE):
                return any(action_or_regex.match(m) for m in permission_info)
            # Failed case
            raise BadParameterError(_("ERR_BAD_USAGE_OF_USER_CAN_API"))

        if not check():
            if throw == "challenge":
                required_permission = ("%s@%s" % (action_or_regex, arg)) if arg is not None else action_or_regex
                raise InsufficientPermissionError(required_permission)
            elif throw:
                raise BadParameterError(_("ERR_INSUFFICIENT_PERMISSION: %(action)s arg=%(arg)s") % {
                    'action': action_or_regex,
                    'arg': arg
                })
            return False
        return True

    def has_perm(self, perm, obj=None):
        """
        Does the user have a specific permission for specific object?
        """
        # Simplest possible answer: Yes, always
        return self.has_module_perms(perm)

    def has_module_perms(self, app_label):
        """
        :param app_label: simple string
        :return: if user has a given permission values or not
        """
        return app_label in self.permission

    def add_override_permission(self, authentication):
        """

        :param authentication:
        """
        self.override_permission = authentication

    @classmethod
    def robot(cls):
        users = cls.objects.filter(is_bot=True)
        if len(users) == 0:
            u = cls.objects.create_user('bot', 'robot', None, group='robotic')
            u.is_bot = True
            u.save()
            return u
        else:
            return users[0]


class IntraAuthentication(object):

    def authenticate(self, username=None, password=None):
        # Check username and password
        try:
            user = IntraUser.objects.get(code=username)
        except IntraUser.DoesNotExist:
            user = None
        if user is not None and user.check_password(password):
            return user
        return None

    def get_user(self, pk):
        try:
            return IntraUser.objects.get(pk=pk)
        except IntraUser.DoesNotExist:
            return None
