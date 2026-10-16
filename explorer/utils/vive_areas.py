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

# Subconjunto de alto rendimiento (~85% cobertura, ~46% menos llamadas)
VIVE_SEARCH_TYPES_HIGH_YIELD: list[tuple[str, str]] = [
    ("restaurante", "restaurant"),
    ("bar", "bar"),
    ("pub", "pub"),
    ("discoteca", "night_club"),
    ("cocktail bar", "cocktail_bar"),
    ("café", "cafe"),
    ("panadería", "bakery"),
    ("pizzería", "pizza_restaurant"),
    ("comida rápida", "fast_food_restaurant"),
    ("atracción turística", "tourist_attraction"),
    ("museo", "museum"),
    ("hotel", "hotel"),
    ("música en vivo", "live_music_venue"),
    ("karaoke", "karaoke"),
]

# Tipos de cocina y planes concretos: rompen el techo de 60 resultados que
# Google impone por consulta, porque «restaurante» siempre devuelve los mismos.
# Todos verificados contra Text Search (New) como includedType válido.
CUISINE_SEARCH_TYPES: list[tuple[str, str]] = [
    ("restaurante mexicano", "mexican_restaurant"),
    ("restaurante italiano", "italian_restaurant"),
    ("restaurante japonés", "japanese_restaurant"),
    ("restaurante chino", "chinese_restaurant"),
    ("restaurante coreano", "korean_restaurant"),
    ("restaurante tailandés", "thai_restaurant"),
    ("restaurante indio", "indian_restaurant"),
    ("restaurante peruano", "seafood_restaurant"),
    ("restaurante español", "spanish_restaurant"),
    ("restaurante francés", "french_restaurant"),
    ("restaurante griego", "greek_restaurant"),
    ("restaurante mediterráneo", "mediterranean_restaurant"),
    ("restaurante árabe", "middle_eastern_restaurant"),
    ("restaurante brasilero", "brazilian_restaurant"),
    ("restaurante vietnamita", "vietnamese_restaurant"),
    ("restaurante asiático", "asian_restaurant"),
    ("restaurante americano", "american_restaurant"),
    ("ramen", "ramen_restaurant"),
    ("parrilla", "barbecue_restaurant"),
    ("asados", "bar_and_grill"),
    ("carnes", "steak_house"),
    ("hamburguesas", "hamburger_restaurant"),
    ("sándwiches", "sandwich_shop"),
    ("desayunos", "breakfast_restaurant"),
    ("brunch", "brunch_restaurant"),
    ("buffet", "buffet_restaurant"),
    ("comida vegana", "vegan_restaurant"),
    ("comida vegetariana", "vegetarian_restaurant"),
    ("alta cocina", "fine_dining_restaurant"),
    ("postres", "dessert_shop"),
    ("repostería", "dessert_restaurant"),
    ("chocolatería", "chocolate_shop"),
    ("donas", "donut_shop"),
    ("jugos naturales", "juice_shop"),
    ("casa de té", "tea_house"),
    ("cafetería corriente", "cafeteria"),
    ("bar deportivo", "sports_bar"),
    ("salón de eventos", "banquet_hall"),
    ("teatro", "performing_arts_theater"),
    ("sala de conciertos", "concert_hall"),
    ("plaza", "plaza"),
    ("sitio histórico", "historical_place"),
    ("hito cultural", "cultural_landmark"),
    ("monumento", "monument"),
    ("sendero ecológico", "hiking_area"),
]

# Pasada genérica (sin includedType) — Fase 2B del plan gratuito
GENERIC_SEARCH_QUERIES: list[str] = [
    "local comercial",
    "establecimiento",
    "negocio",
    "sitio turístico",
    "punto de interés",
    "restaurante bar café",
    # Amplían cobertura con firmas distintas (sigue siendo IDs Only, $0)
    "lugar para visitar",
    "qué hacer",
    "plan en la ciudad",
    "mirador vista",
    "terraza rooftop",
    "cerveza artesanal",
    "comida típica paisa",
    "arepas",
    "empanadas",
    "helados postres",
]

# Ola W5: tipos extra (hospitality / turismo / ocio) no cubiertos en base/cocina.
# Firmas distintas → IDs únicos nuevos sobre las mismas comunas/municipios.
EXTRA_SEARCH_TYPES: list[tuple[str, str]] = [
    ("comida para llevar", "meal_takeaway"),
    ("domicilios", "meal_delivery"),
    ("bed and breakfast", "bed_and_breakfast"),
    ("resort", "resort_hotel"),
    ("motel", "motel"),
    ("camping", "campground"),
    ("cine", "movie_theater"),
    ("bolera", "bowling_alley"),
    ("centro de diversiones", "amusement_center"),
    ("parque de atracciones", "amusement_park"),
    ("zoológico", "zoo"),
    ("acuario", "aquarium"),
    ("centro de visitantes", "visitor_center"),
    ("anfiteatro", "amphitheatre"),
    ("campo de golf", "golf_course"),
    ("marina", "marina"),
    ("viñedo", "vineyard"),
    ("finca turística", "farm"),
    ("centro cultural", "cultural_center"),
    ("centro comunitario", "community_center"),
    ("iglesia", "church"),
    ("biblioteca", "library"),
    ("universidad", "university"),
    ("estadio", "stadium"),
    ("gimnasio", "gym"),
    # Más firmas gratis (Text Search IDs Only)
    ("tienda de souvenirs", "gift_shop"),
    ("mercado", "market"),
    ("supermercado", "supermarket"),
    ("farmacia", "pharmacy"),
    ("banco", "bank"),
    ("atm", "atm"),
    ("estación de bus", "bus_station"),
    ("estación de metro", "subway_station"),
    ("alquiler de autos", "car_rental"),
    ("lavandería", "laundry"),
    ("peluquería", "hair_salon"),
    ("spa uñas", "beauty_salon"),
    ("masajes", "massage"),
    ("yoga", "yoga_studio"),
    ("coworking", "coworking_space"),
    ("espacio de eventos", "wedding_venue"),
    ("iglesia catedral", "cathedral"),
    ("plaza de mercado", "food_court"),
]

# Ola barrios/corredores: ancla el textQuery a un barrio famoso (no solo la comuna).
# Firma distinta → IDs que la consulta «en El Poblado» no trae.
# Formato: (texto anclado al barrio, includedType)
BARRIO_SEARCH_TYPES: list[tuple[str, str]] = [
    # El Poblado
    ("restaurante en Provenza", "restaurant"),
    ("bar en Provenza", "bar"),
    ("café en Provenza", "cafe"),
    ("restaurante en Manila", "restaurant"),
    ("bar en Manila", "bar"),
    ("restaurante en El Tesoro", "restaurant"),
    ("restaurante en Oviedo", "restaurant"),
    ("restaurante en Parque Lleras", "restaurant"),
    ("bar en Parque Lleras", "bar"),
    ("discoteca en Parque Lleras", "night_club"),
    ("restaurante en Ciudad del Río", "restaurant"),
    ("café en Ciudad del Río", "cafe"),
    ("restaurante en Las Palmas", "restaurant"),
    ("hotel en El Poblado", "hotel"),
    # Laureles / Estadio
    ("restaurante en Laureles", "restaurant"),
    ("bar en Laureles", "bar"),
    ("café en Laureles", "cafe"),
    ("restaurante en La 70", "restaurant"),
    ("bar en La 70", "bar"),
    ("discoteca en La 70", "night_club"),
    ("restaurante en Estadio", "restaurant"),
    ("bar en Estadio", "bar"),
    ("restaurante en Bolivariana", "restaurant"),
    # Centro / Candelaria
    ("restaurante en Prado", "restaurant"),
    ("café en Prado", "cafe"),
    ("restaurante en El Centro Medellín", "restaurant"),
    ("restaurante en Junín", "restaurant"),
    ("café en Junín", "cafe"),
    ("museo en el centro Medellín", "museum"),
    # Belén / Sur
    ("restaurante en Belén", "restaurant"),
    ("café en Belén", "cafe"),
    ("restaurante en La América", "restaurant"),
    ("restaurante en San Javier", "restaurant"),
    # Norte / otros
    ("restaurante en Robledo", "restaurant"),
    ("restaurante en Castilla", "restaurant"),
    ("restaurante en Aranjuez", "restaurant"),
    ("restaurante en Buenos Aires Medellín", "restaurant"),
    ("restaurante en Villa Hermosa", "restaurant"),
    # Municipios / oriente
    ("restaurante en Envigado", "restaurant"),
    ("café en Envigado", "cafe"),
    ("bar en Envigado", "bar"),
    ("restaurante en Sabaneta", "restaurant"),
    ("restaurante en Itagüí", "restaurant"),
    ("restaurante en Rionegro", "restaurant"),
    ("restaurante en Llanogrande", "restaurant"),
    ("hotel en Llanogrande", "hotel"),
    ("restaurante en Guatapé", "restaurant"),
    ("hotel en Guatapé", "hotel"),
    ("atracción turística en Guatapé", "tourist_attraction"),
    ("restaurante en El Retiro Antioquia", "restaurant"),
    ("restaurante en La Ceja", "restaurant"),
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
