__author__ = 'peat'

from django.db import models
from intramanee.common.utils import int2base


class LOV(models.Model):
    RANDD_SIZE = 'randd.size'
    RANDD_STAMPING = 'randd.stamping'
    GROUPS = (
        (RANDD_SIZE, 'R&D Size'),
        (RANDD_STAMPING, 'R&D Stamping'),
    )
    RANDD_SIZE_DIGIT_COUNT = 5
    RANDD_SIZE_DIGIT_PAD = '0'
    RANDD_SIZE_NONE = 'NONE'
    """
    Repository of arbitrary text.
    """
    group = models.CharField(max_length=30)
    code = models.CharField(max_length=27)
    label = models.CharField(max_length=450, null=True)
    parent = models.ForeignKey('self', null=True, related_name="children")

    @classmethod
    def ensure_exist(cls, group, label):
        """

        :param group:
        :param label:
        :return: (string) LOV.code
        """
        cursor = cls.objects.filter(group=group, label=label)
        if cursor.count() > 0:
            return cursor[0].code
        else:
            return cls.create(group, label=label, code=label).code

    @classmethod
    def create(cls, group, code, label, parent=None):
        # automate number if group is RANDD_SIZE
        if group == cls.RANDD_SIZE:
            code = cls.next_code(group, cls.RANDD_SIZE_DIGIT_COUNT, cls.RANDD_SIZE_DIGIT_PAD)

        r = cls.objects.create(group=group,
                               label=label,
                               code=code,
                               parent=parent)
        r.save()
        return r

    @classmethod
    def next_code(cls, group, character_count, pad_character):
        """
        Return next code, next_code is calculated from exists number of items found.
        accumulated as a running number therefore we simply use 'query_set.count()'

        :param group:
        :param character_count: number of character in the code set
        :return:
        """
        def integer_val():
            query_set = LOV.objects.filter(group=group)
            return query_set.count()
        return int2base(integer_val() + 1, 36).rjust(character_count, pad_character)

    def values(self):
        return LOV.objects.values_list()

    class Meta:
        app_label = 'intramanee'
        unique_together = (('group', 'code'), )
