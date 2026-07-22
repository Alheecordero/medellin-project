"""
Áreas geográficas y tipos de búsqueda para ViveMedellín.

Usado por scan_place_ids_gratis y generar_grilla_vive_medellin.
"""

from __future__ import annotations

# Bounding boxes: Medellín (16 comunas) + Envigado + zonas prioritarias
VIVE_AREAS = {
    # Medellín municipal completo
    "Medellín": {
        "lat_min": 6.195,
        "lat_max": 6.295,
        "lng_min": -75.620,
        "lng_max": -75.545,
        "separacion_km": 0.65,
    },
    # Envigado (municipio)
    "Envigado": {
        "lat_min": 6.145,
        "lat_max": 6.210,
        "lng_min": -75.610,
        "lng_max": -75.555,
        "separacion_km": 0.75,
    },
    # El Poblado + Manila + Parque Lleras
    "El Poblado": {
        "lat_min": 6.200,
        "lat_max": 6.245,
        "lng_min": -75.585,
        "lng_max": -75.555,
        "separacion_km": 0.45,
    },
    # Laureles + Estadio + La 70
    "Laureles / La 70": {
        "lat_min": 6.235,
        "lat_max": 6.265,
        "lng_min": -75.605,
        "lng_max": -75.575,
        "separacion_km": 0.45,
    },
    # Centro + La Candelaria + Boston
    "Centro / Candelaria": {
        "lat_min": 6.245,
        "lat_max": 6.265,
        "lng_min": -75.575,
        "lng_max": -75.555,
        "separacion_km": 0.45,
    },
    # Envigado centro + Zona Rosa
    "Envigado Centro": {
        "lat_min": 6.160,
        "lat_max": 6.195,
        "lng_min": -75.595,
        "lng_max": -75.565,
        "separacion_km": 0.40,
    },
}

# Solo Medellín + Envigado (sin oriente ni sur del valle)
VIVE_MEDELLIN_ENVIGADO = ("Medellín", "Envigado", "El Poblado", "Laureles / La 70", "Centro / Candelaria", "Envigado Centro")

# Text Search: (textQuery, includedType) — FieldMask places.id only (gratis)
VIVE_SEARCH_TYPES: list[tuple[str, str]] = [
    ("restaurante", "restaurant"),
    ("bar", "bar"),
    ("pub", "pub"),
    ("vinoteca", "wine_bar"),
    ("discoteca", "night_club"),
    ("cocktail bar", "cocktail_bar"),
    ("karaoke", "karaoke"),
    ("música en vivo", "live_music_venue"),
    ("café", "cafe"),
    ("cafetería", "coffee_shop"),
    ("panadería", "bakery"),
    ("heladería", "ice_cream_shop"),
    ("pizzería", "pizza_restaurant"),
    ("sushi", "sushi_restaurant"),
    ("comida rápida", "fast_food_restaurant"),
    ("museo", "museum"),
    ("galería de arte", "art_gallery"),
    ("atracción turística", "tourist_attraction"),
    ("parque", "park"),
    ("rooftop", "bar"),
    ("evento", "event_venue"),
    ("food court", "food_court"),
]


def point_in_bbox(lat: float, lng: float, bbox: dict) -> bool:
    return (
        bbox["lat_min"] <= lat <= bbox["lat_max"]
        and bbox["lng_min"] <= lng <= bbox["lng_max"]
    )


def point_in_vive_areas(lat: float, lng: float, area_names: tuple[str, ...] | None = None) -> bool:
    names = area_names or VIVE_MEDELLIN_ENVIGADO
    for name in names:
        bbox = VIVE_AREAS.get(name)
        if bbox and point_in_bbox(lat, lng, bbox):
            return True
    return False
