from django import template
from explorer.utils.types import get_localized_place_type

register = template.Library()


@register.filter
def place_type_label(place):
    return get_localized_place_type(place)


