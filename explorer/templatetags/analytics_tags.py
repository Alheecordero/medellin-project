from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.simple_tag
def track_event(event_name, parameters=None):
    """
    Template tag para trackear eventos de Google Analytics
    
    Uso: {% track_event 'click_lugar' '{"lugar_nombre": "bar-x", "categoria": "bar"}' %}
    """
    if not parameters:
        parameters = '{}'
    
    return mark_safe(f"""
    <script>
        gtag('event', '{event_name}', {parameters});
    </script>
    """)

@register.simple_tag
def track_page_view(page_title=None, page_location=None):
    """
    Template tag para trackear page views personalizadas
    
    Uso: {% track_page_view 'Detalle de Lugar' %}
    """
    params = {}
    if page_title:
        params['page_title'] = page_title
    if page_location:
        params['page_location'] = page_location
    
    params_str = ', '.join([f"'{k}': '{v}'" for k, v in params.items()])
    params_js = '{' + params_str + '}' if params_str else '{}'
    
    return mark_safe(f"""
    <script>
        gtag('config', '{{ settings.GOOGLE_ANALYTICS_ID }}', {params_js});
    </script>
    """)

@register.simple_tag 
def track_click(element_id, event_name="click", category="engagement"):
    """
    Template tag para trackear clicks automáticamente
    
    Uso: {% track_click 'btn-ver-lugar' 'view_lugar' 'navigation' %}
    """
    return mark_safe(f"""
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            const element = document.getElementById('{element_id}');
            if (element) {{
                element.addEventListener('click', function() {{
                    gtag('event', '{event_name}', {{
                        'event_category': '{category}',
                        'event_label': this.innerText || this.id
                    }});
                }});
            }}
        }});
    </script>
    """) 