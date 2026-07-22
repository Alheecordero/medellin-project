"""JSON API v1 for the Next.js frontend."""

from django.http import JsonResponse, Http404
from django.utils.translation import get_language, activate
from django.views.decorators.http import require_GET

from .views import HomeView, PlaceDetailView, get_optimized_image_urls, adsense_allowed_for_place
from .models import Places
from explorer.utils.types import get_localized_place_type


def _activate_lang(request):
    lang = (request.GET.get("lang") or request.headers.get("Accept-Language", "es"))[:2]
    if lang not in ("es", "en"):
        lang = "es"
    activate(lang)
    return lang


def _serialize_place_card(lugar, *, include_url=True):
    primera_foto = lugar.fotos.first() if hasattr(lugar, "fotos") else None
    if hasattr(lugar, "cached_fotos") and lugar.cached_fotos:
        primera_foto = lugar.cached_fotos[0]
    data = {
        "nombre": lugar.nombre,
        "slug": lugar.slug,
        "rating": float(lugar.rating or 0),
        "total_reviews": lugar.total_reviews or 0,
        "tipo": get_localized_place_type(lugar),
        **get_optimized_image_urls(primera_foto, "thumb"),
        "es_destacado": bool(lugar.es_destacado),
        "es_exclusivo": bool(lugar.es_exclusivo),
        "precio": lugar.precio,
        "direccion": lugar.direccion,
        "comuna": getattr(getattr(lugar, "comuna", None), "name", None),
    }
    if include_url and lugar.slug:
        lang = (get_language() or "es").lower()
        prefix = "/en" if lang.startswith("en") else ""
        segment = "place" if lang.startswith("en") else "lugar"
        data["url"] = f"{prefix}/{segment}/{lugar.slug}/"
    return data


@require_GET
def home_api(request):
    """Bootstrap data for the Next.js home page."""
    _activate_lang(request)
    view = HomeView()
    view.setup(request)
    ctx = view.get_context_data()

    comunas = []
    for block in ctx.get("comuna_con_lugares", []):
        comunas.append(
            {
                "nombre": block["nombre"],
                "slug": block["slug"],
                "es_municipio": block.get("es_municipio", False),
                "lugares": block.get("lugares", []),
            }
        )

    filtros_keys = (
        "regiones_areas",
        "comunas_medellin_chips",
        "otras_regiones_chips",
        "categorias_reales",
        "etiquetas_especiales",
    )
    filtros = {k: ctx.get(k) for k in filtros_keys if k in ctx}

    areas = []
    for region in filtros.get("regiones_areas", []):
        areas.append(
            {
                "osm_id": region.osm_id,
                "name": region.name,
                "slug": region.slug,
                "admin_level": region.admin_level,
            }
        )

    return JsonResponse(
        {
            "success": True,
            "lang": get_language(),
            "lugares_imperdibles": ctx.get("lugares_imperdibles", []),
            "comuna_con_lugares": comunas,
            "filtros": {
                "areas": areas,
                "comunas_medellin_chips": [
                    {"osm_id": r.osm_id, "name": r.name, "slug": r.slug}
                    for r in filtros.get("comunas_medellin_chips", [])
                ],
                "otras_regiones_chips": [
                    {"osm_id": r.osm_id, "name": r.name, "slug": r.slug}
                    for r in filtros.get("otras_regiones_chips", [])
                ],
                "categorias": filtros.get("categorias_reales", []),
                "etiquetas": filtros.get("etiquetas_especiales", []),
            },
        }
    )


@require_GET
def place_detail_api(request, slug):
    """Full place detail for Next.js."""
    _activate_lang(request)
    try:
        lugar = (
            Places.objects.filter(tiene_fotos=True, slug=slug)
            .prefetch_related("fotos", "tags")
            .select_related("comuna")
            .get()
        )
    except Places.DoesNotExist as exc:
        raise Http404 from exc

    detail_view = PlaceDetailView()
    detail_view.object = lugar
    detail_view.kwargs = {"slug": slug}

    fotos = []
    for foto in lugar.fotos.all()[:8]:
        fotos.append(
            {
                **get_optimized_image_urls(foto, "medium"),
                "alt": lugar.nombre,
            }
        )

    tags = [t.name for t in lugar.tags.all()] if hasattr(lugar, "tags") else []

    return JsonResponse(
        {
            "success": True,
            "lang": get_language(),
            "lugar": {
                **_serialize_place_card(lugar, include_url=False),
                "descripcion": lugar.descripcion,
                "telefono": lugar.telefono,
                "sitio_web": lugar.sitio_web,
                "horario_json": lugar.horario_json,
                "horarios": detail_view._format_horarios(lugar),
                "caracteristicas": detail_view._get_caracteristicas(lugar),
                "lat": lugar.ubicacion.y if lugar.ubicacion else None,
                "lng": lugar.ubicacion.x if lugar.ubicacion else None,
                "tags": tags,
                "fotos": fotos,
                "reviews": (lugar.reviews or [])[:5],
                "adsense_allowed": adsense_allowed_for_place(lugar),
            },
            "endpoints": {
                "cercanos": f"/api/lugares/{slug}/cercanos/",
                "similares": f"/api/lugares/{slug}/similares/",
                "comuna": f"/api/lugares/{slug}/comuna/",
            },
        }
    )
