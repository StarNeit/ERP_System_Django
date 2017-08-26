__author__ = 'peat'

from django.conf.urls import patterns, url
from intramanee.sales.views import *

urlpatterns = patterns('',
                       url(r'^$', sales_order_list, name="sales_order_list"),
                       url(r'^new/$', sales_order_new, name="sales_order_new"),
                       url(r'^(?P<pk>[a-zA-Z\d]+)/$', sales_order_edit, name="sales_order_edit")
                       )
