"""Registro independiente de Google Place IDs descubiertos por barrido de grilla."""

from __future__ import annotations

from django.db.models import F
from django.utils import timezone

from explorer.models import GooglePlaceId


def register_google_place_ids(
    place_ids: set[str] | list[str],
    *,
    grid_point_id: int | None = None,
    scan_lat: float | None = None,
    scan_lng: float | None = None,
    included_type: str = "",
    area_names: list[str] | None = None,
    source: str = "text_search_ids",
) -> tuple[int, int]:
    """
    Inserta o actualiza IDs en el catálogo independiente.

    Returns:
        (nuevos, actualizados)
    """
    if not place_ids:
        return 0, 0

    nuevos = 0
    actualizados = 0
    areas = area_names or []
    now = timezone.now()

    for pid in place_ids:
        if not pid:
            continue

        obj, created = GooglePlaceId.objects.get_or_create(
            place_id=pid,
            defaults={
                "source": source,
                "first_grid_point_id": grid_point_id,
                "scan_lat": scan_lat,
                "scan_lng": scan_lng,
                "scan_types": [included_type] if included_type else [],
                "area_names": areas,
            },
        )
        if created:
            nuevos += 1
            continue

        update_fields: list[str] = ["last_seen_at", "discovery_count"]
        obj.last_seen_at = now
        obj.discovery_count = F("discovery_count") + 1

        merged_types = set(obj.scan_types or [])
        if included_type:
            merged_types.add(included_type)
        if merged_types != set(obj.scan_types or []):
            obj.scan_types = sorted(merged_types)
            update_fields.append("scan_types")

        merged_areas = set(obj.area_names or [])
        merged_areas.update(areas)
        if merged_areas != set(obj.area_names or []):
            obj.area_names = sorted(merged_areas)
            update_fields.append("area_names")

        obj.save(update_fields=update_fields)
        actualizados += 1

    return nuevos, actualizados
