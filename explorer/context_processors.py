from .models import RegionOSM
from django.core.cache import cache
from django.utils.text import slugify

OSM_IDS_MEDELLIN = [
    -7680678, -7680807, -7680859, -11937925, 
    -7676068, -7676069, -7680798, -7680904, -7680903,
    -7673972, -7673973, -7680403, -7673971, -7677386,
    -7680799, -7680490
]

def comunas_context(request):
    # Incluir tanto comunas (admin_level='8') como municipios (admin_level='6')
    comunas = RegionOSM.objects.filter(
        admin_level__in=['6', '8'],
        name__isnull=False
    ).order_by('admin_level', 'name')  # Primero municipios (6), luego comunas (8)
    return {'comunas': comunas}

# Versión optimizada con caché - TODAS las regiones
def comunas_context_optimized(request):
    """Context processor optimizado con caché de 24 horas - Incluye todos los municipios y comunas"""
    comunas = cache.get_or_set(
        'todas_regiones_context_v2',
        lambda: [
            {
                'osm_id': c.osm_id,
                'name': c.name,
                'slug': slugify(c.name) if c.name else '',
                'admin_level': c.admin_level,
                'ciudad': c.ciudad
            }
            for c in RegionOSM.objects.filter(
                name__isnull=False
            ).order_by('admin_level', 'name')  # Ordenar por nivel administrativo y nombre
        ],
        86400  # Cache por 24 horas
    )
    return {'comunas': comunas}
