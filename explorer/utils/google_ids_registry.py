"""Registro independiente de Google Place IDs descubiertos por barrido de grilla."""

from __future__ import annotations

from django.utils import timezone

from explorer.models import GooglePlaceId

# Tope de consultas distintas guardadas por place_id: evita filas gigantes en
# lugares que aparecen en decenas de búsquedas.
MAX_SEARCH_QUERIES = 25

_OPTIONAL_FIELDS = ("first_query", "search_queries")
_AVAILABLE_FIELDS: set[str] | None = None


def _available_fields() -> set[str]:
    """
    Campos de GooglePlaceId presentes en la BD.

    El proyecto aplica migraciones a mano, así que el registro sigue funcionando
    si `first_query`/`search_queries` todavía no existen en la tabla.
    """
    global _AVAILABLE_FIELDS
    if _AVAILABLE_FIELDS is not None:
        return _AVAILABLE_FIELDS

    from django.db import connection

    try:
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(
                cursor, GooglePlaceId._meta.db_table
            )
        _AVAILABLE_FIELDS = {column.name for column in description}
    except Exception:
        _AVAILABLE_FIELDS = set()
    return _AVAILABLE_FIELDS


def register_google_place_ids(
    place_ids: set[str] | list[str],
    *,
    grid_point_id: int | None = None,
    scan_lat: float | None = None,
    scan_lng: float | None = None,
    included_type: str = "",
    area_names: list[str] | None = None,
    source: str = "text_search_ids",
    query: str = "",
) -> tuple[int, int]:
    """
    Inserta o actualiza IDs en el catálogo independiente.

    Trabaja por lotes (una consulta de lectura, un INSERT y un UPDATE) para que
    un barrido que devuelve miles de IDs no haga miles de round-trips.

    Returns:
        (nuevos, actualizados)
    """
    pids = {pid for pid in place_ids if pid}
    if not pids:
        return 0, 0

    areas = sorted({name for name in (area_names or []) if name})
    types = [included_type] if included_type else []
    now = timezone.now()
    columns = _available_fields()
    has_queries = "search_queries" in columns or not columns
    normalized_query = (query or "").strip()[:200]

    existing = list(GooglePlaceId.objects.filter(place_id__in=pids))
    existing_by_id = {obj.place_id: obj for obj in existing}

    nuevos_ids = [pid for pid in pids if pid not in existing_by_id]
    if nuevos_ids:
        nuevos_objs = []
        for pid in nuevos_ids:
            obj = GooglePlaceId(
                place_id=pid,
                source=source,
                first_grid_point_id=grid_point_id,
                scan_lat=scan_lat,
                scan_lng=scan_lng,
                scan_types=list(types),
                area_names=list(areas),
            )
            if has_queries and normalized_query:
                obj.first_query = normalized_query
                obj.search_queries = [normalized_query]
            nuevos_objs.append(obj)
        GooglePlaceId.objects.bulk_create(
            nuevos_objs, batch_size=500, ignore_conflicts=True
        )

    actualizados = 0
    if existing:
        update_fields = ["last_seen_at", "discovery_count", "scan_types", "area_names"]
        if has_queries:
            update_fields += list(_OPTIONAL_FIELDS)

        for obj in existing:
            obj.last_seen_at = now
            obj.discovery_count = (obj.discovery_count or 0) + 1
            obj.scan_types = sorted(set(obj.scan_types or []) | set(types))
            obj.area_names = sorted(set(obj.area_names or []) | set(areas))
            if has_queries and normalized_query:
                queries = list(obj.search_queries or [])
                if normalized_query not in queries and len(queries) < MAX_SEARCH_QUERIES:
                    queries.append(normalized_query)
                obj.search_queries = queries
                if not obj.first_query:
                    obj.first_query = normalized_query

        GooglePlaceId.objects.bulk_update(existing, update_fields, batch_size=500)
        actualizados = len(existing)

    return len(nuevos_ids), actualizados
