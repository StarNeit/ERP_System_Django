__author__ = 'haloowing'

from django import template
from django.utils.safestring import mark_safe
from intramanee.common.decorators import SimpleJSONEncoder
from intramanee.common.service import choices as choices_api
import json

register = template.Library()


@register.filter
def split(value, arg):
    return value.split(arg)


@register.filter
def hasvisiblechildren(value):
    if 'children' not in value:
        return False
    count = 0
    for i, item in enumerate(value['children']):
        if 'hidden' not in item or item['hidden'] is False:
            count += 1
    return count > 0


@register.filter
def jsonify(object):
    return mark_safe(json.dumps(object))


@register.filter
def jsonEncoder(object):
    return mark_safe(json.dumps(object, cls=SimpleJSONEncoder))


@register.simple_tag
def choices(*args):
    r = choices_api(args)
    return mark_safe(json.dumps(r, cls=SimpleJSONEncoder))
