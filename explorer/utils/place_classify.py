"""
Clasificación controlada de lugares scrapeados / descubiertos.

Objetivo: orden sobre el catálogo masivo (todo tipo de sitio) mapeando a:
  - tipo: código Vive (PLACE_TYPE_CHOICES) cuando es posible
  - primary_type: código Google (snake_case) canónico
  - tipo_family: bucket de control (food, nightlife, lodging, …)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from explorer.models import PLACE_TYPE_CHOICES
from explorer.utils.vive_areas import (
    CUISINE_SEARCH_TYPES,
    EXTRA_SEARCH_TYPES,
    VIVE_SEARCH_TYPES,
    VIVE_SEARCH_TYPES_HIGH_YIELD,
)

# Familias de control (reportes, filtros, colas)
TIPO_FAMILY_CHOICES = (
    ("food", "Comida / restaurantes"),
    ("cafe_bakery", "Café / panadería / postres"),
    ("nightlife", "Noche / bares / clubs"),
    ("lodging", "Alojamiento"),
    ("culture_tourism", "Cultura / turismo"),
    ("leisure", "Ocio / deporte"),
    ("services", "Servicios"),
    ("other", "Otros / sin clasificar"),
)

_VIVE_TIPO_SET = {code for code, _ in PLACE_TYPE_CHOICES}

# Google type → familia
_FAMILY_BY_GOOGLE: dict[str, str] = {}

_FOOD = {
    "restaurant", "mexican_restaurant", "italian_restaurant", "japanese_restaurant",
    "chinese_restaurant", "korean_restaurant", "thai_restaurant", "indian_restaurant",
    "spanish_restaurant", "french_restaurant", "greek_restaurant", "mediterranean_restaurant",
    "middle_eastern_restaurant", "brazilian_restaurant", "vietnamese_restaurant",
    "asian_restaurant", "american_restaurant", "afghani_restaurant", "african_restaurant",
    "ramen_restaurant", "barbecue_restaurant", "bar_and_grill", "steak_house",
    "hamburger_restaurant", "sandwich_shop", "breakfast_restaurant", "brunch_restaurant",
    "buffet_restaurant", "vegan_restaurant", "vegetarian_restaurant", "fine_dining_restaurant",
    "seafood_restaurant", "sushi_restaurant", "pizza_restaurant", "fast_food_restaurant",
    "food_court", "meal_takeaway", "meal_delivery", "food", "food_delivery", "diner",
    "cafeteria", "turkish_restaurant", "lebanese_restaurant",
}
_CAFE = {
    "cafe", "coffee_shop", "bakery", "ice_cream_shop", "dessert_shop", "dessert_restaurant",
    "chocolate_shop", "donut_shop", "juice_shop", "tea_house", "acai_shop", "cat_cafe",
    "dog_cafe", "internet_cafe",
}
_NIGHT = {
    "bar", "pub", "wine_bar", "cocktail_bar", "night_club", "karaoke", "live_music_venue",
    "sports_bar",
}
_LODGING = {
    "hotel", "hostel", "bed_and_breakfast", "resort_hotel", "motel", "campground", "guest_house",
}
_CULTURE = {
    "museum", "art_gallery", "tourist_attraction", "park", "historical_landmark",
    "historical_place", "cultural_landmark", "monument", "cultural_center", "plaza",
    "observation_deck", "visitor_center", "church", "library", "amphitheatre",
    "performing_arts_theater", "concert_hall", "auditorium", "event_venue", "banquet_hall",
}
_LEISURE = {
    "movie_theater", "bowling_alley", "amusement_center", "amusement_park", "zoo",
    "aquarium", "golf_course", "marina", "vineyard", "farm", "stadium", "gym",
    "sports_club", "sports_complex", "playground", "hiking_area", "spa", "wellness_center",
    "childrens_camp", "ranch",
}
_SERVICES = {
    "barber_shop", "beauty_salon", "beautician", "laundry", "car_wash", "parking",
    "real_estate_agency", "school", "university", "community_center", "doctor", "health",
    "market", "catering_service", "art_studio",
}

for _code in _FOOD:
    _FAMILY_BY_GOOGLE[_code] = "food"
for _code in _CAFE:
    _FAMILY_BY_GOOGLE[_code] = "cafe_bakery"
for _code in _NIGHT:
    _FAMILY_BY_GOOGLE[_code] = "nightlife"
for _code in _LODGING:
    _FAMILY_BY_GOOGLE[_code] = "lodging"
for _code in _CULTURE:
    _FAMILY_BY_GOOGLE[_code] = "culture_tourism"
for _code in _LEISURE:
    _FAMILY_BY_GOOGLE[_code] = "leisure"
for _code in _SERVICES:
    _FAMILY_BY_GOOGLE[_code] = "services"

# Etiquetas ES/EN de Maps → google type
_LABEL_TO_GOOGLE: dict[str, str] = {}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s_/.-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _register_label(label: str, google_type: str) -> None:
    key = _norm(label)
    if key and key not in _LABEL_TO_GOOGLE:
        _LABEL_TO_GOOGLE[key] = google_type


def _bootstrap_labels() -> None:
    for label, gtype in (
        list(VIVE_SEARCH_TYPES)
        + list(VIVE_SEARCH_TYPES_HIGH_YIELD)
        + list(CUISINE_SEARCH_TYPES)
        + list(EXTRA_SEARCH_TYPES)
    ):
        _register_label(label, gtype)
        _FAMILY_BY_GOOGLE.setdefault(gtype, "other")

    for code, es_label in PLACE_TYPE_CHOICES:
        _register_label(str(es_label), code)
        _register_label(code.replace("_", " "), code)
        if code not in _FAMILY_BY_GOOGLE:
            if code.endswith("_restaurant") or code in _FOOD:
                _FAMILY_BY_GOOGLE[code] = "food"
            elif code in _CAFE:
                _FAMILY_BY_GOOGLE[code] = "cafe_bakery"
            elif code in _NIGHT:
                _FAMILY_BY_GOOGLE[code] = "nightlife"
            else:
                _FAMILY_BY_GOOGLE[code] = "other"

    # Aliases frecuentes del panel Maps (ES)
    extras = {
        "restaurante": "restaurant",
        "restaurant": "restaurant",
        "bar": "bar",
        "cafe": "cafe",
        "cafeteria": "cafe",
        "cafetería": "cafe",
        "coffee shop": "coffee_shop",
        "panaderia": "bakery",
        "bakery": "bakery",
        "pizzeria": "pizza_restaurant",
        "pizza": "pizza_restaurant",
        "hotel": "hotel",
        "hostal": "hostel",
        "hostel": "hostel",
        "museo": "museum",
        "museum": "museum",
        "parque": "park",
        "park": "park",
        "discoteca": "night_club",
        "night club": "night_club",
        "club": "night_club",
        "spa": "spa",
        "gimnasio": "gym",
        "gym": "gym",
        "iglesia": "church",
        "church": "church",
        "tienda": "market",
        "store": "market",
        "supermercado": "market",
        "farmacia": "health",
        "hospital": "health",
        "clinica": "doctor",
        "universidad": "university",
        "colegio": "school",
        "escuela": "school",
        "atraccion turistica": "tourist_attraction",
        "tourist attraction": "tourist_attraction",
        "punto de interes": "tourist_attraction",
        "heladeria": "ice_cream_shop",
        "sushi": "sushi_restaurant",
        "comida rapida": "fast_food_restaurant",
        "fast food": "fast_food_restaurant",
        "takeaway": "meal_takeaway",
        "delivery": "meal_delivery",
    }
    for label, gtype in extras.items():
        _register_label(label, gtype)

    # Aliases ES frecuentes del panel (post-fix)
    for label, gtype in {
        "cocteleria": "cocktail_bar",
        "coctelería": "cocktail_bar",
        "cocktail bar": "cocktail_bar",
        "restaurante halal": "restaurant",
        "restaurante de comida rapida": "fast_food_restaurant",
        "restaurante de comida rápida": "fast_food_restaurant",
        "comida rapida": "fast_food_restaurant",
        "granizados": "dessert_restaurant",
        "heladeria": "ice_cream_shop",
    }.items():
        _register_label(label, gtype)


_bootstrap_labels()

# Prioridad al elegir entre varios scan_types (más específico primero)
_PRIORITY = (
    list(_FOOD - {"restaurant", "food"})
    + list(_CAFE)
    + list(_NIGHT - {"bar"})
    + list(_LODGING)
    + list(_CULTURE)
    + list(_LEISURE)
    + list(_SERVICES)
    + ["restaurant", "bar", "cafe", "food"]
)
_PRIORITY_INDEX = {t: i for i, t in enumerate(_PRIORITY)}


def _pick_best_google(types: list[str]) -> str | None:
    if not types:
        return None
    clean = [t for t in types if t]
    if not clean:
        return None

    def score(t: str) -> tuple[int, int]:
        return (_PRIORITY_INDEX.get(t, 10_000), -len(t))

    return sorted(clean, key=score)[0]


def google_type_from_label(category: str | None) -> str | None:
    if not category:
        return None
    key = _norm(category)
    if not key:
        return None

    # Chips / ruido de UI de Maps — NUNCA clasificar con esto
    noise = {
        "restaurantes cercanos",
        "hoteles",
        "cosas que hacer",
        "bares",
        "cafes",
        "para llevar",
        "tiendas de comestibles",
        "guardado",
        "recientes",
        "obtener app",
        "ver fotos",
        "indicaciones",
        "descripcion general",
        "opiniones",
        "acerca de",
        "pedir en linea",
    }
    if key in noise:
        return None

    if key in _LABEL_TO_GOOGLE:
        return _LABEL_TO_GOOGLE[key]

    # Match parcial conservador: evita que "granizados" dispare dentro del nombre del local
    for label, gtype in sorted(_LABEL_TO_GOOGLE.items(), key=lambda x: -len(x[0])):
        if len(label) < 5:
            continue
        if key == label:
            return gtype
        # "restaurante mexicano", "bar de vinos", etc.
        if key.startswith(label + " ") or key.endswith(" " + label):
            return gtype
        if label.startswith(key) and len(key) >= 8:
            return gtype

    if "comida rapida" in key or "fast food" in key:
        return "fast_food_restaurant"
    if "coctel" in key or "cocktail" in key:
        return "cocktail_bar"
    if "halal" in key:
        return "restaurant"
    if "restaurant" in key or "restaurante" in key:
        return "restaurant"
    if re.search(r"\bbar\b", key) and "bares" not in key:
        return "bar"
    if "cafe" in key or "cafeter" in key or "coffee" in key:
        return "cafe"
    if "hotel" in key or "hostal" in key:
        return "hotel"
    return None


def family_for_google(google_type: str | None) -> str:
    if not google_type:
        return "other"
    return _FAMILY_BY_GOOGLE.get(google_type, "other")


def vive_tipo_for_google(google_type: str | None) -> str:
    """Mapea a PLACE_TYPE_CHOICES; si no existe, 'otros'."""
    if not google_type:
        return "otros"
    if google_type in _VIVE_TIPO_SET:
        return google_type
    # aproximaciones comunes no listadas en Places.tipo
    approx = {
        "coffee_shop": "cafe",
        "bakery": "cafe",
        "ice_cream_shop": "dessert_restaurant",
        "dessert_shop": "dessert_restaurant",
        "chocolate_shop": "dessert_restaurant",
        "donut_shop": "dessert_restaurant",
        "juice_shop": "cafe",
        "tea_house": "cafe",
        "cocktail_bar": "bar",
        "sports_bar": "bar",
        "live_music_venue": "night_club",
        "hotel": "otros",
        "hostel": "otros",
        "museum": "cultural_center",
        "art_gallery": "art_studio",
        "park": "playground",
        "tourist_attraction": "historical_landmark",
        "gym": "sports_club",
        "church": "otros",
        "movie_theater": "amusement_center",
        "stadium": "sports_complex",
    }
    mapped = approx.get(google_type)
    if mapped and mapped in _VIVE_TIPO_SET:
        return mapped
    return "otros"


def classify_place(
    *,
    maps_category: str | None = None,
    scan_types: list[str] | None = None,
    search_queries: list[str] | None = None,
    body_snippet: str | None = None,
) -> dict[str, Any]:
    """
    Clasificación unificada.

    Prioridad:
      1) category limpia del panel Maps (no chips UI)
      2) scan_types del discovery (includedType)
      3) search_queries / body
    Si Maps y scan_types discrepan, Maps gana solo si confidence alta;
    primary = el más específico entre candidatos válidos.
    """
    candidates: list[str] = []
    source = "unknown"
    confidence = 0.0

    from_label = google_type_from_label(maps_category)
    if from_label:
        candidates.append(from_label)
        source = "maps_category"
        confidence = 0.9

    for t in scan_types or []:
        if t and t not in candidates:
            candidates.append(t)
    if source == "unknown" and (scan_types or []):
        source = "scan_types"
        confidence = 0.75

    if not candidates and search_queries:
        for q in search_queries:
            g = google_type_from_label(q)
            if g:
                candidates.append(g)
                source = "search_query"
                confidence = 0.55
                break

    if not from_label and body_snippet:
        # Buscar línea de categoría típica en body (post-fix)
        for raw_line in (body_snippet or "").split("\n"):
            g = google_type_from_label(raw_line.strip())
            if g:
                if g not in candidates:
                    candidates.insert(0, g)
                if source == "unknown":
                    source = "body_heuristic"
                    confidence = 0.5
                break

    primary = _pick_best_google(candidates)
    # Si Maps dio un tipo válido, preferirlo como primary aunque scan_types
    # aporte uno más "específico" erróneo (ej. discovery cocktail vs Maps food).
    if from_label and from_label in candidates:
        primary = from_label

    if not primary:
        primary = ""
        source = "unknown"
        confidence = 0.0

    tipo = vive_tipo_for_google(primary or None)
    family = family_for_google(primary or None)
    if tipo == "otros" and family == "other":
        confidence = min(confidence, 0.25) if confidence else 0.0

    return {
        "primary_type": primary or "",
        "tipo": tipo,
        "tipo_family": family,
        "tipo_source": source,
        "tipo_confidence": round(confidence, 2),
        "google_types": candidates,
        "maps_category": maps_category or "",
    }
