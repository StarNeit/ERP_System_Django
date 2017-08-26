__author__ = 'peat'

from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import HttpResponseRedirect
from django.views.generic import ListView, UpdateView, CreateView
from django.contrib.auth import logout, authenticate, login as auth_login
from django.template.response import TemplateResponse

from intramanee.models import IntraUser
from intramanee.decorator import menu_item
from intramanee import settings
from intramanee.common import codes, permissions as perm

from .forms import LoginForm
from .forms import EditUserForm
from .forms import CreateUserForm


def login(request):
    logout(request)
    print "Hello %s" % request.session.session_key
    form = LoginForm()
    # If POST is given
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(username=username, password=password)
            if user is not None:
                if not user.is_active:
                    form.errors['__all__'] = form.error_class([_('ERROR_USER_DISABLED')])
                else:
                    auth_login(request, user)
                    request.session['foo'] = 'bar'
                    # time to redirect
                    url = request.GET.get('next')
                    if url is None:
                        url = reverse('dashboard')
                    print "Leaving %s" % request.session.session_key
                    return HttpResponseRedirect(url)
            else:
                form.errors['__all__'] = form.error_class([_('ERROR_USERNAME_PASSWORD_INCORRECT')])

    return TemplateResponse(request, 'common/lock_screen.html', {'form': form, 'page_title': _('PAGE_TITLE_LOGIN')})


class UserListView(ListView):
    model = IntraUser
    paginate_by = 20
    template_name = 'user/list.html'

    def get_context_data(self, **kwargs):
        context = super(UserListView, self).get_context_data(**kwargs)
        context['page_title'] = _('PAGE_TITLE_USER_LIST')
        return context

    @method_decorator(menu_item('user-list'))
    def dispatch(self, request, *args, **kwargs):
        return super(UserListView, self).dispatch(request, *args, **kwargs)


class UserEditView(UpdateView):
    model = IntraUser
    template_name = 'user/edit.html'
    form_class = EditUserForm

    def get_context_data(self, **kwargs):
        context = super(UserEditView, self).get_context_data(**kwargs)
        context['page_title'] = _('PAGE_TITLE_EDIT_USER')
        context['permissions'] = perm.permission_center
        return context

    def get_success_url(self):
        return reverse('user:edit', kwargs={'pk': self.kwargs['pk']})

    @method_decorator(menu_item('user-edit'))
    def dispatch(self, request, *args, **kwargs):
        return super(UserEditView, self).dispatch(request, *args, **kwargs)


class UserCreateView(CreateView):
    model = IntraUser
    template_name = 'user/new.html'
    form_class = CreateUserForm
    success_url = reverse_lazy('user:list')

    def get_context_data(self, **kwargs):
        context = super(UserCreateView, self).get_context_data(**kwargs)
        context['page_title'] = _('PAGE_TITLE_CREATE_USER')
        context['permissions'] = perm.permission_center
        return context

    def form_valid(self, form):
        r = super(UserCreateView, self).form_valid(form)
        form.instance.save()
        return r

    @method_decorator(menu_item('user-new'))
    def dispatch(self, request, *args, **kwargs):
        return super(UserCreateView, self).dispatch(request, *args, **kwargs)
