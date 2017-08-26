__author__ = 'peat'

from django import forms
from django.utils.translation import ugettext as _

from intramanee.models import IntraUser
from intramanee.common.forms import ArrayField, ArrayFieldWidget


class LoginForm(forms.Form):
    username = forms.CharField(label=_('USER_FIELD_USERNAME'), max_length=255,
                               widget=forms.TextInput(attrs={
                                   'placeholder': _('USER_FIELD_USERNAME'),
                                   'class': 'form-control',
                                   'autocomplete': 'off'
                               }))
    password = forms.CharField(label=_('USER_FIELD_PASSWORD'), max_length=27,
                               widget=forms.TextInput(attrs={
                                   'placeholder': _('USER_FIELD_PASSWORD'),
                                   'class': 'form-control',
                                   'autocomplete': 'off',
                                   'type': 'password'
                               }))


class EditUserForm(forms.ModelForm):
    class Meta:
        model = IntraUser
        fields = ['first_name', 'last_name']

    first_name = forms.CharField(label=_('USER_FIELD_FIRST_NAME'), max_length=100, required=False,
                                 widget=forms.TextInput(attrs={
                                     'placeholder': _('USER_FIELD_FIRST_NAME'),
                                     'class': 'form-control req'
                                 }))
    last_name = forms.CharField(label=_('USER_FIELD_LAST_NAME'), max_length=100, required=False,
                                widget=forms.TextInput(attrs={
                                    'placeholder': _('USER_FIELD_LAST_NAME'),
                                    'class': 'form-control req'
                                }))
    password = forms.CharField(label=_('USER_FIELD_PASSWORD'), max_length=100, required=False,
                               widget=forms.PasswordInput(attrs={
                                   'placeholder': _('USER_FIELD_PASSWORD'),
                                   'class': 'form-control',
                                   'autocomplete': 'off'
                               }))
    new_password = forms.CharField(label=_('FIELD_NEW_PASSWORD'), max_length=100, required=False,
                                   widget=forms.PasswordInput(attrs={
                                       'placeholder': _('FIELD_NEW_PASSWORD'),
                                       'class': 'form-control',
                                       'autocomplete': 'off'
                                   }))
    confirm_password = forms.CharField(label=_('FIELD_CONFIRM_PASSWORD'), max_length=100, required=False,
                                       widget=forms.PasswordInput(attrs={
                                           'placeholder': _('FIELD_CONFIRM_PASSWORD'),
                                           'class': 'form-control',
                                           'autocomplete': 'off'
                                       }))
    permissions = ArrayField(widget=ArrayFieldWidget)

    def clean(self):
        # update permissions
        self.instance.permissions = self.cleaned_data.get('permissions')
        return self.cleaned_data

    def save(self, commit=True):
        r = super(EditUserForm, self).save()
        return r


class CreateUserForm(forms.ModelForm):
    class Meta:
        model = IntraUser
        fields = ['code', 'first_name', 'last_name', 'password']

    code = forms.CharField(label=_('USER_FIELD_CODE'), max_length=50,
                           widget=forms.TextInput(attrs={
                               'placeholder': _('USER_FIELD_CODE'),
                               'class': 'form-control req',
                               'autocomplete': 'off'
                           }))
    first_name = forms.CharField(label=_('USER_FIELD_FIRST_NAME'), max_length=100,
                                 widget=forms.TextInput(attrs={
                                     'placeholder': _('USER_FIELD_FIRST_NAME'),
                                     'class': 'form-control req'
                                 }))
    last_name = forms.CharField(label=_('USER_FIELD_LAST_NAME'), max_length=100,
                                widget=forms.TextInput(attrs={
                                    'placeholder': _('USER_FIELD_LAST_NAME'),
                                    'class': 'form-control req'
                                }))
    password = forms.CharField(label=_('USER_FIELD_PASSWORD'), max_length=100,
                               widget=forms.PasswordInput(attrs={
                                   'placeholder': _('USER_FIELD_PASSWORD'),
                                   'class': 'form-control req',
                                   'autocomplete': 'off'
                               }))
    confirm_password = forms.CharField(label=_('FIELD_CONFIRM_PASSWORD'), max_length=100,
                                       widget=forms.PasswordInput(attrs={
                                           'placeholder': _('FIELD_CONFIRM_PASSWORD'),
                                           'class': 'form-control req',
                                           'autocomplete': 'off'
                                       }))
    permissions = ArrayField(widget=ArrayFieldWidget)

    def clean(self):
        # Check for permission?
        self.instance.code = self.cleaned_data.get('code')

        # update permissions
        self.instance.permissions = self.cleaned_data.get('permissions')

        return self.cleaned_data

    def save(self, commit=True):
        return super(CreateUserForm, self).save(commit)
