from .models import RegionOSM

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
