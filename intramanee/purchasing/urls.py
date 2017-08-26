from django.conf.urls import patterns, url
from intramanee.purchasing.views import *

urlpatterns = patterns('',
                       url(r'^pr/$', pr_list, name="pr_list"),
                       url(r'^pr/(?P<pk>[a-zA-Z\d]+)/$', pr_view, name="pr_view"),
                       )