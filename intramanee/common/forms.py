__author__ = 'peat'

from django.forms.widgets import SelectMultiple
from django import forms
from models import UserFile
from intramanee.models import IntraUser


class ArrayFieldWidget(SelectMultiple):
    def value_from_datadict(self, data, files, name):
        return data.getlist(name+'[]')


class ArrayField(forms.MultipleChoiceField):
    widget = ArrayFieldWidget

    def to_python(self, value):
        return value

    def valid_value(self, value):
        return True


class ObjectField(forms.Field):
    model = None

    def __init__(self, model_):
        super(ObjectField, self).__init__()
        self.model = model_

    def to_python(self, value):
        if isinstance(value, basestring):
            return self.model.objects.get(pk=value)
        else:
            return value

    def prepare_value(self, value):
        return value and value.id or None

    def validate(self, value):
        return True


class GenericFileUploadForm(forms.ModelForm):
    class Meta:
        model = UserFile
        fields = ['domain', 'sub_domain', 'author', 'file']

    author = ObjectField(IntraUser)
    file = forms.FileField()
