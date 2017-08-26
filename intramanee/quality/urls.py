__author__ = 'haloowing'

from django.conf.urls import patterns, url
from intramanee.quality.views import *

urlpatterns = patterns('',
                       url(r'^dashboard/$', dashboard, name="dashboard"),
                       )
