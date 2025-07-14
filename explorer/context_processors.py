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
    comunas = RegionOSM.objects.filter(
        osm_id__in=OSM_IDS_MEDELLIN,
        name__isnull=False
    ).order_by('name')
    return {'comunas': comunas}

# Versión optimizada con caché
def comunas_context_optimized(request):
    """Context processor optimizado con caché de 24 horas"""
    comunas = cache.get_or_set(
        'comunas_medellin_context',
        lambda: [
            {
                'osm_id': c.osm_id,
                'name': c.name,
                'slug': slugify(c.name) if c.name else ''
            }
            for c in RegionOSM.objects.filter(
                osm_id__in=OSM_IDS_MEDELLIN,
                name__isnull=False
            ).order_by('name')
        ],
        86400  # Cache por 24 horas
    )
    return {'comunas': comunas}
