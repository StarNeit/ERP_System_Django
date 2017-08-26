from django.conf.urls import patterns, include, url
from django.conf.urls.static import static
from .user.views import login
from .views import dashboard
from django.contrib import admin
from django.shortcuts import render_to_response
from django.template import RequestContext
import settings

from django.contrib.auth.decorators import login_required


def required(wrapping_functions, patterns_rslt):
    if not hasattr(wrapping_functions, '__iter__'):
        wrapping_functions = (wrapping_functions,)

    return [
        _wrap_instance__resolve(wrapping_functions, instance)
        for instance in patterns_rslt
    ]


def _wrap_instance__resolve(wrapping_functions, instance):
    if not hasattr(instance, 'resolve'):
        return instance
    resolve = getattr(instance, 'resolve')

    def _wrap_func_in_returned_resolver_match(*args, **kwargs):
        rslt = resolve(*args, **kwargs)

        if not hasattr(rslt, 'func'):
            return rslt
        f = getattr(rslt, 'func')

        for _f in reversed(wrapping_functions):
            # @decorate the function from inner to outter
            f = _f(f)

        setattr(rslt, 'func', f)

        return rslt

    setattr(instance, 'resolve', _wrap_func_in_returned_resolver_match)

    return instance

admin.autodiscover()

js_info_dict = {
    'domain': 'djangojs',
    'packages': ('intramanee',),
}

urlpatterns = patterns('',
                       url(r'^$', login_required(dashboard), name="dashboard"),
                       url(r'^login/', login, name="login"),
                       url(r'^admin/', include(admin.site.urls)),
                       url(r'^ajax/production/', include('intramanee.production.ajax', namespace="ajax.production")),
                       url(r'^ajax/common/', include('intramanee.common.ajax', namespace="ajax.common")),
                       url(r'^ajax/bot/', include('intramanee.bot.ajax', namespace="ajax.bot")),
                       url(r'^ajax/stock/', include('intramanee.stock.ajax', namespace="ajax.stock")),
                       url(r'^ajax/task/', include('intramanee.task.ajax', namespace="ajax.task")),
                       url(r'^jsi18n/$', 'django.views.i18n.javascript_catalog', js_info_dict),
                       ) + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += required(
    login_required,
    patterns('',
             url(r'^purchasing/', include('intramanee.purchasing.urls', namespace="purchasing")),
             url(r'^production/', include('intramanee.production.urls', namespace="production")),
             url(r'^qc/', include('intramanee.quality.urls', namespace="qc")),
             url(r'^sales/', include('intramanee.sales.urls', namespace="sales")),
             url(r'^rd/', include('intramanee.randd.urls', namespace="randd")),
             url(r'^stock/', include('intramanee.stock.urls', namespace="stock")),
             url(r'^user/', include('intramanee.user.urls', namespace="user")),
             )
)


def handler404(request):
    response = render_to_response('404.html', {},
                                  context_instance=RequestContext(request))
    response.status_code = 404
    return response


def handler500(request):
    response = render_to_response('500.html', {},
                                  context_instance=RequestContext(request))
    response.status_code = 500
    return response

