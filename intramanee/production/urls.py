__author__ = 'haloowing'

from django.conf.urls import patterns, url
from intramanee.production.views import *

urlpatterns = patterns('',
                       url(r'^$', production_order_list, name="production_order_list"),
                       url(r'^dashboard/(?P<pk>[0-9]+)/$', production_dashboard, name="production_dashboard"),
                       url(r'^planning/$', planning_tool, name="planning_tool"),
                       url(r'^stock-requirement/$', stock_requirement, name="stock_requirement"),
                       url(r'^mrp/$', mrp, name="mrp"),
                       url(r'^new/$', production_order_new, name="production_order_new"),
                       url(r'^job-tags/$', job_tags, name="job_tags"),
                       url(r'^staging-form-print/(?P<pk>[a-zA-Z\d]+)/$', staging_form_print, name="staging_form_print"),
                       url(r'^staging-form/(?P<pk>[a-zA-Z\d]+)/$', staging_form, name="staging_form"),
                       url(r'^operation-group-manager/$', operation_group_manager, name="operation_group_manager"),
                       url(r'^(?P<pk>[a-zA-Z\d]+)/$', production_order_edit, name="production_order_edit"),
                       url(r'^(?P<pk>[a-zA-Z\d]+)/(?P<sk>[a-zA-Z\d]+)/$', production_order_operation, name="production_order_operation"),
                       )
