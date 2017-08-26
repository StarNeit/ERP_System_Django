from intramanee.common import documents as doc
from intramanee.common.models import IntraUser
from intramanee.common.errors import ValidationError
from intramanee.common.utils import NOW
from django.utils.translation import ugettext as _
from datetime import timedelta
from bson import ObjectId


class Authentication(doc.Doc):
    """
    Authentication token

    Parameter meanings

        User (requester) requested action (action) override authentication by (authorizer) on date (doc)

        Token = object_id

    """
    requester = doc.FieldIntraUser(none=False)
    authorizer = doc.FieldIntraUser(none=False)
    target_permissions = doc.FieldList(doc.FieldString(), none=False)
    created = doc.FieldDateTime(none=False)

    @classmethod
    def create(cls, requester, authenticated_by, authentication_challenge, target_permissions):
        """

        :param IntraUser requester:
        :param IntraUser authenticated_by:
        :param basestring authentication_challenge:
        :param basestring|list target_permissions:
        :raise ValidationError:
        :return Authentication:
        """
        # sanitize input
        if isinstance(target_permissions, basestring):
            target_permissions = [target_permissions]

        # Validate if target user has enough permission allow such task to happen?
        if any(not authenticated_by.can(p) for p in target_permissions):
            raise ValidationError(_("ERR_AUTHENTICATE_USER_DOES_NOT_HAVE_TARGET_PERMISSION: %(target_permissions)s") % {
                'target_permissions': ",".join(target_permissions)
            })

        # Validate password challenge
        if not authenticated_by.check_password(authentication_challenge):
            raise ValidationError(_("ERR_AUTHENTICATION_FAILED"))

        # Validated, success create the token
        o = cls()
        o.target_permissions = target_permissions
        o.requester = requester
        o.authorizer = authenticated_by
        o.created = NOW()
        o.save()
        return o

    class Meta:
        collection_name = 'authentication'
