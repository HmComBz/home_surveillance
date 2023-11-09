from django import template
register = template.Library()
from django.template.defaultfilters import floatformat

@register.filter
def currency(value):
    if value is None:
        return None
    return "{;,}".format(value) + " kr"

@register.filter
def percent(value):
    if value is None:
        return None
    return floatformat(value * 100, 0) + "%"

