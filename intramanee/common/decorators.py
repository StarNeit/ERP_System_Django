__author__ = 'peat'

from functools import wraps
from datetime import datetime
import time

from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.utils.decorators import available_attrs

from django_ajax.shortcuts import render_to_json
from django_ajax.encoder import LazyJSONEncoder

from errors import IntraError, ProhibitedError
from bson import objectid
from uoms import UOM
from task import TaskGroup


class JsonSerializable():

    def as_json(self):
        raise ProhibitedError('as_json must be implemented')


def simplified_error(e):
    return e


class SimpleJSONEncoder(LazyJSONEncoder):

    """
    A JSONEncoder subclass that handle querysets and models objects.
    Add how handle your type of object here to use when dump json

    """
    def default(self, obj):
        if isinstance(obj, IntraError):
            return obj.content()
        elif isinstance(obj, objectid.ObjectId):
            return str(obj)
        elif isinstance(obj, UOM):
            return str(obj)
        elif isinstance(obj, datetime):
            return time.mktime(obj.timetuple())
        elif isinstance(obj, TaskGroup):
            return obj.serialize()
        elif isinstance(obj, JsonSerializable):
            return obj.as_json()
        return super(SimpleJSONEncoder, self).default(obj)


def ajaxian(function=None, mandatory=True, good_operations=None):
    """
    Decorator who guesses the user response type and translates to a serialized
    JSON response. Usage::

        @ajax
        def my_view(request):
            do_something()
            # will send {'status': 200, 'statusText': 'OK', 'content': null}

        @ajax
        def my_view(request):
            return {'key': 'value'}
            # will send {'status': 200, 'statusText': 'OK',
                         'content': {'key': 'value'}}

        @ajax
        def my_view(request):
            return HttpResponse('<h1>Hi!</h1>')
            # will send {'status': 200, 'statusText': 'OK',
                         'content': '<h1>Hi!</h1>'}

        @ajax
        def my_view(request):
            return redirect('home')
            # will send {'status': 302, 'statusText': 'FOUND', 'content': '/'}

        # combination with others decorators:

        @ajax
        @login_required
        @require_POST
        def my_view(request):
            pass
            # if request user is not authenticated then the @login_required
            # decorator redirect to login page.
            # will send {'status': 302, 'statusText': 'FOUND',
                         'content': '/login'}

            # if request method is 'GET' then the @require_POST decorator return
            # a HttpResponseNotAllowed response.
            # will send {'status': 405, 'statusText': 'METHOD NOT ALLOWED',
                         'content': null}

    """
    def decorator(func):
        @wraps(func, assigned=available_attrs(func))
        def inner(request, *args, **kwargs):
            if mandatory and not request.is_ajax():
                return HttpResponseBadRequest()

            if request.is_ajax():
                # return json response
                try:
                    # Validate operation and return them gracefully (405)
                    if good_operations is not None and (isinstance(good_operations, tuple) and request.method not in good_operations or isinstance(good_operations, basestring) and request.method != good_operations):
                        raise HttpResponseNotAllowed(permitted_methods=good_operations)

                    out = func(request, *args, **kwargs)
                    return render_to_json(out, cls=SimpleJSONEncoder)
                except Exception as exception:
                    return render_to_json(simplified_error(exception), cls=SimpleJSONEncoder)
            else:
                # return standard response
                return func(request, *args, **kwargs)

        return inner

    if function:
        return decorator(function)

    return decorator
