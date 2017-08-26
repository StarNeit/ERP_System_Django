__author__ = 'peat'

from django.conf.urls import patterns, url
from intramanee.stock.views import *

urlpatterns = patterns('',
                       url(r'^material/$', material_list, name="material_list"),
                       url(r'^material/new/$', material_new, name="material_new"),
                       url(r'^material/(?P<pk>[a-zA-Z\d]+)/$', material_edit, name="material_edit"),
                       url(r'^$', inventory_dashboard, name="inventory_dashboard"),
                       url(r'^movement/new/$', movement_new, name="movement_new"),
                       url(r'^movement/(?P<pk>[a-zA-Z\d]+)/$', movement_detail, name="movement_detail"),
                       url(r'^material-tags/$', material_tags, name="material_tags"),
                       url(r'^requisition/$', requisition_new, name="requisition"),
)
