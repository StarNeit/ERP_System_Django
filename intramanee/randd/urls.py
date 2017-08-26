__author__ = 'peat'

from django.conf.urls import patterns, url
from intramanee.randd.views import *

urlpatterns = patterns('',
                       url(r'^$', rd_task, name="task"),
                       url(r'^design/$', design_list, name="design_list"),
                       url(r'^design/new/$', design_new, name="design_new"),
                       url(r'^design/(?P<pk>[a-zA-Z\d]+)/$', design_edit, name="design_edit")
                       )
