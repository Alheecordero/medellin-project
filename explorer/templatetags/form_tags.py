from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={'class': css_class})

@register.filter(name='format_price_range')
def format_price_range(value: str | None) -> str:
    if not value:
        return "No especificado"
    val = str(value).strip().upper()
    mapping = {
        '$': 'Económico',
        '$$': 'Moderado',
        '$$$': 'Costoso',
        '$$$$': 'Muy costoso',
        'PRICE_LEVEL_INEXPENSIVE': 'Económico',
        'PRICE_LEVEL_MODERATE': 'Moderado',
        'PRICE_LEVEL_EXPENSIVE': 'Costoso',
        'PRICE_LEVEL_VERY_EXPENSIVE': 'Muy costoso',
        'PRICE_LEVEL_UNSPECIFIED': 'No especificado',
        'NONE': 'No especificado',
        'NULL': 'No especificado',
    }
    # Normalizar símbolos largos como '₱', etc., si aparecieran
    if val in mapping:
        return mapping[val]
    # Intento heurístico: contar signos $
    if all(ch == '$' for ch in val) and 1 <= len(val) <= 4:
        return mapping.get('$' * len(val), 'No especificado')
    return 'No especificado'