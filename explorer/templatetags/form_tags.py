from django import template
from django.utils.translation import gettext as _

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={'class': css_class})

@register.filter(name='format_price_range')
def format_price_range(value: str | None) -> str:
    if not value:
        return _("No especificado")
    val = str(value).strip().upper()
    mapping = {
        '$': _('Económico'),
        '$$': _('Moderado'),
        '$$$': _('Costoso'),
        '$$$$': _('Muy costoso'),
        'PRICE_LEVEL_INEXPENSIVE': _('Económico'),
        'PRICE_LEVEL_MODERATE': _('Moderado'),
        'PRICE_LEVEL_EXPENSIVE': _('Costoso'),
        'PRICE_LEVEL_VERY_EXPENSIVE': _('Muy costoso'),
        'PRICE_LEVEL_UNSPECIFIED': _('No especificado'),
        'NONE': _('No especificado'),
        'NULL': _('No especificado'),
    }
    # Normalizar símbolos largos como '₱', etc., si aparecieran
    if val in mapping:
        return mapping[val]
    # Intento heurístico: contar signos $
    if all(ch == '$' for ch in val) and 1 <= len(val) <= 4:
        return mapping.get('$' * len(val), _('No especificado'))
    return _('No especificado')