from django import template
from django.utils.translation import gettext as _
import re

register = template.Library()


@register.simple_tag(takes_context=True)
def translate_url_to(context, language_code):
    """
    Traduce la URL actual al idioma especificado.
    Uso: {% translate_url_to 'en' %}
    """
    request = context.get('request')
    if not request:
        return '/'
    
    current_url = request.get_full_path()
    
    # Fallback: manejo manual de URLs con patrones regex
    # Nota: No usamos django_translate_url porque no maneja URLs con segmentos
    # que tienen diferentes nombres en cada idioma (ej: /nosotros/ <-> /about-us/)
    import re as regex
    
    # Separar path y query string
    if '?' in current_url:
        path, query = current_url.split('?', 1)
        query = '?' + query
    else:
        path, query = current_url, ''
    
    if language_code == 'en':
        # ES -> EN
        if path.startswith('/en/'):
            return current_url  # Ya está en inglés
        
        # Patrones de conversión ES -> EN (orden importa: más específico primero)
        patterns = [
            # Páginas especiales
            (r'^/nosotros/$', '/en/about-us/'),
            (r'^/about-us/$', '/en/about-us/'),  # Por si acceden a /about-us/ sin prefijo
            (r'^/busqueda-semantica/', '/en/semantic-search/'),
            # Reviews con slug (con ñ URL-encoded o no)
            (r'^/lugar/([^/]+)/rese[ñ%C3%B1]as/$', r'/en/place/\1/reviews/'),
            # Lugares por comuna
            (r'^/lugares/([^/]+)/$', r'/en/places/\1/'),
            # Detalle de lugar
            (r'^/lugar/([^/]+)/$', r'/en/place/\1/'),
            # Lista general
            (r'^/lugares/$', '/en/places/'),
            # Home
            (r'^/$', '/en/'),
        ]
        
        for pattern, replacement in patterns:
            if regex.match(pattern, path):
                new_path = regex.sub(pattern, replacement, path)
                return new_path + query
        
        # Fallback: agregar /en/
        return '/en' + current_url
    
    else:  # ES
        # EN -> ES
        if not path.startswith('/en/'):
            # Manejar caso especial de /about-us/ sin prefijo
            if path == '/about-us/':
                return '/nosotros/' + query
            return current_url  # Ya está en español
        
        # Quitar /en/ primero para facilitar el matching
        path_sin_en = path[3:]  # Quita '/en'
        
        # Patrones de conversión EN -> ES
        patterns = [
            # Páginas especiales
            (r'^/about-us/$', '/nosotros/'),
            (r'^/nosotros/$', '/nosotros/'),  # Por si hay /en/nosotros/
            (r'^/semantic-search/', '/busqueda-semantica/'),
            # Reviews con slug
            (r'^/place/([^/]+)/reviews/$', r'/lugar/\1/reseñas/'),
            # Lugares por comuna
            (r'^/places/([^/]+)/$', r'/lugares/\1/'),
            # Detalle de lugar
            (r'^/place/([^/]+)/$', r'/lugar/\1/'),
            # Lista general
            (r'^/places/$', '/lugares/'),
            # Home
            (r'^/$', '/'),
        ]
        
        for pattern, replacement in patterns:
            if regex.match(pattern, path_sin_en):
                new_path = regex.sub(pattern, replacement, path_sin_en)
                return new_path + query
        
        # Fallback: quitar /en/
        return (path_sin_en if path_sin_en else '/') + query

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


@register.simple_tag
def img_url(foto, size='thumb'):
    """
    Retorna la URL óptima de imagen según el tamaño requerido.
    
    Uso:
        {% img_url foto 'thumb' %}   -> 220px (cards pequeñas)
        {% img_url foto 'medium' %}  -> 800px (cards medianas, hero)
        {% img_url foto 'full' %}    -> Original (modal galería)
    
    Fallback automático si la variante no existe.
    """
    if not foto:
        return ''
    
    # Obtener URLs de las variantes
    thumb = getattr(foto, 'imagen_miniatura', None) or ''
    medium = getattr(foto, 'imagen_mediana', None) or ''
    full = getattr(foto, 'imagen', None) or ''
    
    if size == 'thumb':
        return thumb or medium or full
    elif size == 'medium':
        return medium or full
    else:  # 'full' o cualquier otro
        return full


@register.inclusion_tag('components/optimized_img.html')
def optimized_img(foto, alt='', css_class='', sizes='100vw', loading='lazy', hero=False):
    """
    Renderiza una imagen optimizada con srcset para responsive.
    
    Uso:
        {% optimized_img foto alt="Nombre" css_class="card-img" %}
        {% optimized_img foto alt="Hero" hero=True loading="eager" %}
    """
    if not foto:
        return {'has_image': False, 'alt': alt, 'css_class': css_class}
    
    thumb = getattr(foto, 'imagen_miniatura', None) or ''
    medium = getattr(foto, 'imagen_mediana', None) or ''
    full = getattr(foto, 'imagen', None) or ''
    
    # Determinar src principal según contexto
    if hero:
        src = medium or full
    else:
        src = thumb or medium or full
    
    # Construir srcset
    srcset_parts = []
    if thumb:
        srcset_parts.append(f"{thumb} 220w")
    if medium:
        srcset_parts.append(f"{medium} 800w")
    if full:
        srcset_parts.append(f"{full} 1600w")
    
    return {
        'has_image': bool(src),
        'src': src,
        'srcset': ', '.join(srcset_parts) if srcset_parts else '',
        'sizes': sizes,
        'alt': alt,
        'css_class': css_class,
        'loading': loading,
        'data_full': full,  # Para modal de galería
    }


@register.filter(name="ensure_absolute_url")
def ensure_absolute_url(url: str | None, request) -> str:
    """
    Devuelve una URL absoluta para usar en meta tags (og:image/twitter:image).

    - Si `url` ya es absoluta (http/https), se devuelve tal cual.
    - Si `url` es relativa (empieza con '/'), se prefija con scheme://host usando `request`.
    - Si `url` es falsy o `request` no existe, devuelve string vacío o el string original.
    """
    if not url:
        return ""
    s = str(url).strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("/") and request:
        return f"{request.scheme}://{request.get_host()}{s}"
    return s