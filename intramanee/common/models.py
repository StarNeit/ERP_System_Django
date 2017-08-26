__author__ = 'peat'

from django.db import models
from django.utils.encoding import force_str, force_text
from datetime import datetime

import os

from intramanee.models import IntraUser


class FileField(models.FileField):

    def generate_filename(self, instance, filename):
        upload_to = "usercontent/%s/%s/%s/" % (instance.domain or '*', instance.sub_domain or '*', '%Y-%m')
        return os.path.join(os.path.normpath(force_text(datetime.now().strftime(force_str(upload_to)))),
                            self.get_filename(filename))


class UserFile(models.Model):
    doc = models.DateTimeField(auto_now_add=True)
    domain = models.CharField(max_length=20)
    sub_domain = models.CharField(max_length=60)
    author = models.ForeignKey(IntraUser)
    file = FileField(upload_to="dont'care")

    class Meta:
        app_label = 'intramanee'


class Stamping(models.Model):
    author = models.ForeignKey(IntraUser)
    text = models.CharField(max_length=450)

    class Meta:
        app_label = 'intramanee'


class Company(models.Model):
    code = models.CharField(max_length=3, unique=True)
    title = models.CharField(max_length=450)
    author = models.ForeignKey(IntraUser)

    class Meta:
        app_label = 'intramanee'
