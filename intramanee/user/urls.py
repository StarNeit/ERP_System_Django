__author__ = 'peat'

from django.conf.urls import patterns, url
from views import *


urlpatterns = patterns('',
                       url(r'^$',  UserListView.as_view(), name="list"),
                       url(r'^new/$', UserCreateView.as_view(), name="new"),
                       url(r'^(?P<pk>[a-z\d]+)/$',  UserEditView.as_view(), name="edit"),
                       )
