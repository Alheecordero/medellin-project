"""
Áreas geográficas y tipos de búsqueda para el barrido de Google Place IDs.

Usado por generar_grilla_cobertura, scan_place_ids_gratis y scan_place_ids_gratis.
Independiente de Places / PendingPlace: alimenta el catálogo GooglePlaceId.
"""

from __future__ import annotations

# Bounding boxes: Valle de Aburrá + oriente turístico (Rionegro, Guatapé, etc.)
# separacion_km: distancia entre puntos de grilla (menor = más cobertura, más llamadas API)
SCAN_AREAS: dict[str, dict] = {
    # ── Medellín municipal ──────────────────────────────────────────────
    "Medellín": {
        "lat_min": 6.195,
        "lat_max": 6.295,
        "lng_min": -75.620,
        "lng_max": -75.545,
        "separacion_km": 0.65,
    },
    "El Poblado": {
        "lat_min": 6.200,
        "lat_max": 6.245,
        "lng_min": -75.585,
        "lng_max": -75.555,
        "separacion_km": 0.45,
    },
    "Laureles / La 70": {
        "lat_min": 6.235,
        "lat_max": 6.265,
        "lng_min": -75.605,
        "lng_max": -75.575,
        "separacion_km": 0.45,
    },
    "Centro / Candelaria": {
        "lat_min": 6.245,
        "lat_max": 6.265,
        "lng_min": -75.575,
        "lng_max": -75.555,
        "separacion_km": 0.45,
    },
    "Belén / Sur": {
        "lat_min": 6.195,
        "lat_max": 6.235,
        "lng_min": -75.620,
        "lng_max": -75.585,
        "separacion_km": 0.55,
    },
    "Norte (Bello límite / Castilla)": {
        "lat_min": 6.265,
        "lat_max": 6.310,
        "lng_min": -75.610,
        "lng_max": -75.545,
        "separacion_km": 0.75,
    },
    # ── Valle de Aburrá sur ─────────────────────────────────────────────
    "Envigado": {
        "lat_min": 6.145,
        "lat_max": 6.210,
        "lng_min": -75.610,
        "lng_max": -75.555,
        "separacion_km": 0.75,
    },
    "Envigado Centro": {
        "lat_min": 6.160,
        "lat_max": 6.195,
        "lng_min": -75.595,
        "lng_max": -75.565,
        "separacion_km": 0.40,
    },
    "Sabaneta": {
        "lat_min": 6.145,
        "lat_max": 6.175,
        "lng_min": -75.625,
        "lng_max": -75.595,
        "separacion_km": 0.75,
    },
    "Itagüí": {
        "lat_min": 6.155,
        "lat_max": 6.195,
        "lng_min": -75.635,
        "lng_max": -75.595,
        "separacion_km": 0.75,
    },
    "La Estrella": {
        "lat_min": 6.135,
        "lat_max": 6.170,
        "lng_min": -75.660,
        "lng_max": -75.620,
        "separacion_km": 1.0,
    },
    "Caldas": {
        "lat_min": 6.080,
        "lat_max": 6.145,
        "lng_min": -75.650,
        "lng_max": -75.600,
        "separacion_km": 1.5,
    },
    # ── Corredor campestre / aeropuerto ───────────────────────────────
    "Las Palmas / Santa Elena": {
        "lat_min": 6.175,
        "lat_max": 6.240,
        "lng_min": -75.535,
        "lng_max": -75.425,
        "separacion_km": 1.5,
    },
    "Rionegro": {
        "lat_min": 6.120,
        "lat_max": 6.180,
        "lng_min": -75.420,
        "lng_max": -75.350,
        "separacion_km": 1.0,
    },
    "Rionegro Zona Rosa / Llanogrande": {
        "lat_min": 6.095,
        "lat_max": 6.135,
        "lng_min": -75.410,
        "lng_max": -75.360,
        "separacion_km": 0.75,
    },
    # ── Oriente turístico ───────────────────────────────────────────────
    "Guatapé": {
        "lat_min": 6.210,
        "lat_max": 6.275,
        "lng_min": -75.190,
        "lng_max": -75.130,
        "separacion_km": 0.75,
    },
    "El Peñol (embalse)": {
        "lat_min": 6.195,
        "lat_max": 6.240,
        "lng_min": -75.260,
        "lng_max": -75.190,
        "separacion_km": 1.0,
    },
    "El Retiro": {
        "lat_min": 6.040,
        "lat_max": 6.080,
        "lng_min": -75.520,
        "lng_max": -75.470,
        "separacion_km": 1.5,
    },
    "La Ceja": {
        "lat_min": 5.950,
        "lat_max": 5.990,
        "lng_min": -75.450,
        "lng_max": -75.410,
        "separacion_km": 1.5,
    },
    "Marinilla": {
        "lat_min": 6.160,
        "lat_max": 6.195,
        "lng_min": -75.360,
        "lng_max": -75.320,
        "separacion_km": 1.5,
    },
    # ── Norte / occidente turístico ─────────────────────────────────────
    "Bello Norte / Copacabana": {
        "lat_min": 6.325,
        "lat_max": 6.400,
        "lng_min": -75.590,
        "lng_max": -75.540,
        "separacion_km": 1.5,
    },
    "San Jerónimo": {
        "lat_min": 6.430,
        "lat_max": 6.460,
        "lng_min": -75.750,
        "lng_max": -75.720,
        "separacion_km": 2.0,
    },
    "Santa Fe de Antioquia": {
        "lat_min": 6.545,
        "lat_max": 6.575,
        "lng_min": -75.840,
        "lng_max": -75.810,
        "separacion_km": 1.5,
    },
}

# Alias retrocompatible
VIVE_AREAS = SCAN_AREAS

# Subconjuntos útiles
SCAN_AREAS_CORE = (
    "Medellín",
    "El Poblado",
    "Laureles / La 70",
    "Centro / Candelaria",
    "Envigado",
    "Envigado Centro",
)
SCAN_AREAS_VALLE = (
    "Medellín",
    "El Poblado",
    "Laureles / La 70",
    "Centro / Candelaria",
    "Belén / Sur",
    "Norte (Bello límite / Castilla)",
    "Envigado",
    "Envigado Centro",
    "Sabaneta",
    "Itagüí",
    "La Estrella",
    "Caldas",
)
SCAN_AREAS_TURISMO = (
    "Las Palmas / Santa Elena",
    "Rionegro",
    "Rionegro Zona Rosa / Llanogrande",
    "Guatapé",
    "El Peñol (embalse)",
    "El Retiro",
    "La Ceja",
    "Marinilla",
)
VIVE_MEDELLIN_ENVIGADO = SCAN_AREAS_CORE
SCAN_AREAS_ALL = tuple(SCAN_AREAS.keys())

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
    ("hotel", "hotel"),
    ("hostal", "hostel"),
    ("spa", "spa"),
    ("mirador", "observation_deck"),
]

# Pasada genérica (sin includedType) — Fase 2B del plan gratuito
GENERIC_SEARCH_QUERIES: list[str] = [
    "local comercial",
    "establecimiento",
    "negocio",
    "sitio turístico",
    "punto de interés",
    "restaurante bar café",
]

# Umbral para subdividir grilla (Fase 3)
SATURATION_IDS_THRESHOLD = 50

SCAN_PASADAS = ("bias", "restriction", "generico")


def point_in_bbox(lat: float, lng: float, bbox: dict) -> bool:
    return (
        bbox["lat_min"] <= lat <= bbox["lat_max"]
        and bbox["lng_min"] <= lng <= bbox["lng_max"]
    )


def areas_for_point(lat: float, lng: float, area_names: tuple[str, ...] | None = None) -> list[str]:
    names = area_names or SCAN_AREAS_ALL
    matched = []
    for name in names:
        bbox = SCAN_AREAS.get(name)
        if bbox and point_in_bbox(lat, lng, bbox):
            matched.append(name)
    return matched


def point_in_scan_areas(lat: float, lng: float, area_names: tuple[str, ...] | None = None) -> bool:
    return bool(areas_for_point(lat, lng, area_names))


def point_in_vive_areas(lat: float, lng: float, area_names: tuple[str, ...] | None = None) -> bool:
    return point_in_scan_areas(lat, lng, area_names)


def resolve_area_names(solo: str = "", preset: str = "") -> tuple[str, ...]:
    """Resuelve filtro de áreas desde --solo o --preset."""
    if solo:
        if solo not in SCAN_AREAS:
            raise ValueError(f"Área desconocida: {solo}. Opciones: {', '.join(SCAN_AREAS)}")
        return (solo,)
    presets = {
        "core": SCAN_AREAS_CORE,
        "valle": SCAN_AREAS_VALLE,
        "turismo": SCAN_AREAS_TURISMO,
        "all": SCAN_AREAS_ALL,
    }
    if preset:
        key = preset.lower()
        if key not in presets:
            raise ValueError(f"Preset desconocido: {preset}. Opciones: {', '.join(presets)}")
        return presets[key]
    return SCAN_AREAS_ALL
