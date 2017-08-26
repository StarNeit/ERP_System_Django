__author__ = 'haloowing'

from django.http.request import HttpRequest
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _
from intramanee.common.errors import ProhibitedError, IntraError
from intramanee.common.models import IntraUser
from bson import ObjectId
import re


def _resolve_path(active_item, choices):
    for i, choice in enumerate(choices):
        if active_item == choice['slug']:
            return [choice]
        elif choice.get('children', None) is not None and len(choice['children']) > 0:
            r = _resolve_path(active_item, choice['children'])
            if r is not None:
                ret = [choice]
                ret.extend(r)
                return ret
    return None


class IntraMiddleWare:
    menu = [
        {
            'label': _('MENU_TASKS'),
            'url': reverse('dashboard'),
            'slug': 'home',
            'children': [
                {
                    'label': _('MENU_SALES'),
                    'slug': 'sales',
                    'icon': 'dollar',
                    'required': re.compile('^sales_order'),
                    'children': [
                        {
                            'label': _('MENU_SALES_ORDERS'),
                            'slug': 'sales-order-list',
                            'required': 'sales_order+read',
                            'url': reverse('sales:sales_order_list'),
                            'children': [
                                {
                                    'label': _('MENU_SALES_ORDER_EDIT'),
                                    'slug': 'sales-order-edit',
                                    'required': 'sales_order+read',
                                    'url': 'javascript:;',
                                    'hidden': True
                                }
                            ]
                        },
                        {
                            'label': _('MENU_SALES_ORDER_CREATE'),
                            'slug': 'sales-order-new',
                            'required': 'sales_order+write',
                            'url': reverse('sales:sales_order_new')
                        },
                    ]
                },
                {
                    'label': _('MENU_RANDD'),
                    'slug': 'randd',
                    'icon': 'sitemap',
                    'required': re.compile('^design'),
                    'children': [
                        # {
                        #     'label': _('MENU_RANDD_TASK'),
                        #     'slug': 'randd-task',
                        #     'url': reverse('randd:task')
                        # },
                        {
                            'label': _('MENU_RANDD_DESIGNS'),
                            'slug': 'randd-design-list',
                            'required': 'design+read',
                            'url': reverse('randd:design_list'),
                            'children': [
                                {
                                    'label': _('MENU_RANDD_DESIGN_EDIT'),
                                    'slug': 'randd-design-edit',
                                    'required': 'design+read',
                                    'url': 'javascript:;',
                                    'hidden': True
                                }
                            ]
                        },
                        {
                            'label': _('MENU_RANDD_DESIGN_CREATE'),
                            'slug': 'randd-design-new',
                            'required': 'design+write',
                            'url': reverse('randd:design_new')
                        }
                    ]
                },
                {
                    'label': _('MENU_MATERIAL'),
                    'slug': 'material',
                    'icon': 'codepen',
                    'required': re.compile('^material_master'),
                    'children': [
                        {
                            'label': _('MENU_MATERIALS'),
                            'slug': 'material-list',
                            'required': 'material_master+read',
                            'url': reverse('stock:material_list'),
                            'children': [
                                {
                                    'label': _('MENU_MATERIAL_EDIT'),
                                    'slug': 'material-edit',
                                    'required': 'material_master+read',
                                    'url': 'javascript:;',
                                    'hidden': True
                                }
                            ]
                        },
                        {
                            'label': _('MENU_MATERIAL_CREATE'),
                            'slug': 'material-new',
                            'required': 'material_master+write',
                            'url': reverse('stock:material_new')
                        }
                    ]
                },
                {
                    'label': _('MENU_PRODUCTION'),
                    'slug': 'production',
                    'icon': 'industry',
                    'required': re.compile('^production_order'),
                    'children': [
                        {
                            'label': _('MENU_DASHBOARD_5340'),
                            'slug': 'production-dashboard-5340',
                            'required': 'task+write@5340',
                            'url': reverse('production:production_dashboard', kwargs={'pk': 5340})
                        },
                        {
                            'label': _('MENU_DASHBOARD_5390'),
                            'slug': 'production-dashboard-5390',
                            'required': 'task+write@5390',
                            'url': reverse('production:production_dashboard', kwargs={'pk': 5390})
                        },
                        {
                            'label': _('MENU_DASHBOARD_5400'),
                            'slug': 'production-dashboard-5400',
                            'required': 'task+write@5400',
                            'url': reverse('production:production_dashboard', kwargs={'pk': 5400})
                        },
                        {
                            'label': _('MENU_DASHBOARD_5430'),
                            'slug': 'production-dashboard-5430',
                            'required': 'task+write@5430',
                            'url': reverse('production:production_dashboard', kwargs={'pk': 5430})
                        },
                        {
                            'label': _('MENU_PRODUCTION_ORDERS'),
                            'slug': 'production-order-list',
                            'required': 'production_order+read',
                            'url': reverse('production:production_order_list'),
                            'children': [
                                {
                                    'label': _('MENU_PRODUCTION_ORDER_EDIT'),
                                    'slug': 'production-order-edit',
                                    'required': 'production_order+read',
                                    'url': 'javascript:;',
                                    'hidden': True
                                },
                                {
                                    'label': _('MENU_PRODUCTION_ORDER_OPERATION'),
                                    'slug': 'production-order-operation',
                                    'required': 'production_order+read',
                                    'url': 'javascript:;',
                                    'hidden': True
                                }
                            ]
                        },
                        {
                            'label': _('MENU_PRODUCTION_ORDER_CREATE'),
                            'slug': 'production-order-new',
                            'required': 'production_order+write',
                            'url': reverse('production:production_order_new')
                        },
                        {
                            'label': _('MENU_PLANNING_TOOL'),
                            'slug': 'planning-tool',
                            'required': 'proposal+write',
                            'url': reverse('production:planning_tool')
                        },
                        {
                            'label': _('MENU_STOCK_REQUIREMENT'),
                            'slug': 'stock-requirement',
                            'required': 'production_order+read',
                            'url': reverse('production:stock_requirement')
                        },
                        {
                            'label': _('MENU_MRP'),
                            'slug': 'mrp',
                            'required': 'mrp-session+write',
                            'url': reverse('production:mrp')
                        },
                        {
                            'label': _('MENU_OPERATION_GROUP_MANAGER'),
                            'slug': 'operation-group-manager',
                            'url': reverse('production:operation_group_manager')
                        }
                    ]
                },
                {
                    'label': _('MENU_QUALITY_CONTROL'),
                    'slug': 'qc',
                    'icon': 'braille',
                    'required': 'task+write@5450,task+write@5451,task+write@5461,task+write@5462,task+write@5463,task+write@5464,task+write@5466,task+write@5467,task+write@5468,task+write@5469,task+write@5471',
                    'children': [
                        {
                            'label': _('MENU_DASHBOARD'),
                            'slug': 'qc-dashboard',
                            'required': 'task+write@5450,task+write@5451,task+write@5461,task+write@5462,task+write@5463,task+write@5464,task+write@5466,task+write@5467,task+write@5468,task+write@5469,task+write@5471',
                            'url': reverse('qc:dashboard')
                        }
                    ]
                },
                {
                    'label': _('MENU_INVENTORY'),
                    'slug': 'stock',
                    'icon': 'cubes',
                    'children': [
                        {
                            'label': _('MENU_DASHBOARD'),
                            'slug': 'inventory-dashboard',
                            'required': re.compile('^inv_'),
                            'url': reverse('stock:inventory_dashboard')
                        },
                        {
                            'label': _('MENU_MOVEMENT'),
                            'slug': 'movement-detail',
                            'required': re.compile('^inv_'),
                            'url': 'javascript:;',
                            'hidden': True
                        },
                        {
                            'label': _('MENU_MOVEMENT_CREATE'),
                            'slug': 'movement-new',
                            'required': re.compile(r'^inv_movement\+write'),
                            'url': reverse('stock:movement_new')
                        },
                        {
                            'label': _('MENU_MATERIAL_REQUISITION_FORM'),
                            'slug': 'requisition',
                            'url': reverse('stock:requisition')
                        },
                        {
                            'label': _('MENU_STAGING_FORM'),
                            'slug': 'staging-form',
                            'url': 'javascript:;',
                            'hidden': True
                        }
                    ]
                },
                {
                    'label': _('MENU_PURCHASING'),
                    'slug': 'purchasing',
                    'icon': 'truck',
                    'required': re.compile('^purchase'),
                    'children': [
                        {
                            'label': _('MENU_PURCHASE_REQUISITIONS'),
                            'slug': 'pr-list',
                            'url': reverse('purchasing:pr_list'),
                            'children': [
                                {
                                    'label': _('MENU_PURCHASE_REQUISITION'),
                                    'slug': 'pr-view',
                                    'url': 'javascript:;',
                                    'hidden': True
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        {
            'label': _('MENU_TRACKING'),
            'url': '', # reverse('organiszation:list'),
            'slug': 'tracking',

        },
        {
            'label': _('MENU_KPI'),
            'url': '', # reverse('organiszation:list'),
            'slug': 'kpi',

        },
        {
            'label': _('MENU_ORGANIZATION'),
            'url': '', # reverse('organiszation:list'),
            'slug': 'orgs',

        },
        {
            'label': _('MENU_USERS'),
            'url': reverse('user:list'),
            'slug': 'users',
            'children': [
                {
                    'label': _('MENU_USERS_LIST'),
                    'url': reverse('user:list'),
                    'slug': 'user-list',
                    'children': [
                        {
                            'label': _('MENU_USERS_EDIT'),
                            'slug': 'user-edit',
                            'url': 'javascript:;',
                            'hidden': True
                        }
                    ]
                }
            ],
        }
    ]

    def filter_menu(self, user, menu):
        o = []
        for _m in menu:
            m = _m.copy()
            if user.is_authenticated() and 'required' in m and m['required'] is not None and not user.can(m['required']):
                continue

            has_children = False
            if 'children' in m:
                m['children'] = self.filter_menu(user, m['children'])
                has_children = len(m['children']) > 0

            if 'url' in m or has_children:
                o.append(m)
        return o

    def process_template_response(self, request, response):
        """

        :param request:
        :param response:
        :return:
        """
        # inject context data
        if response.context_data is None:
            response.context_data = {}
        # inject filtered menu
        m = self.filter_menu(request.user, self.menu)
        # inject active_menu, and breadcrumb
        if response.context_data.get('active_menu') is not None:
            active_item = response.context_data['active_menu']
            path = _resolve_path(active_item, m)
            response.context_data['breadcrumb'] = path
        response.context_data['menu'] = m
        return response

    def process_request(self, request):
        """
        @see https://docs.djangoproject.com/en/1.9/topics/http/middleware/#process-request

        :param HttpRequest request:
        :return:
        """
        # inject override header
        if 'HTTP_X_PERMISSION_OVERRIDE' in request.META:
            """
            auth_token can be
            (1) ObjectId string (Authentication Object's ObjectId)
            (2) Request Authentication String
                pattern: <usercode>;$;<action>;$;<password>
            """
            auth_token = request.META['HTTP_X_PERMISSION_OVERRIDE']
            from intramanee.common.authentication import Authentication
            try:
                if ObjectId.is_valid(auth_token):
                    auth = Authentication(auth_token)
                    if request.user != auth.requester:
                        raise ProhibitedError(_("OVERRIDE PERMISSION IS NOT REQUESTED FOR THIS USER"))
                    request.user.add_override_permission(auth)
                else:
                    """
                    Request Authentication Pattern
                    """
                    (usercode, permissions, password) = auth_token.split(';$;', 2)
                    permissions = filter(lambda a: a, permissions.split(','))
                    # Built authentication here
                    o = Authentication.create(request.user,
                                              target_permissions=permissions,
                                              authenticated_by=IntraUser.objects.get(code=usercode),
                                              authentication_challenge=password)
                    request.user.add_override_permission(o)
            except ValueError:
                print "WARNING: INVALID OVERRIDE PERMISSION"
            except IntraError:
                print "WARNING: INVALID OVERRIDE PERMISSION"
        return None
