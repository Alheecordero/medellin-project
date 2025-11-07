from __future__ import annotations

from django.utils.translation import gettext, get_language


def derive_english_from_code(code: str) -> str:
    """Best-effort English label from a place type code.
    Example: "night_club" -> "Night Club", "fast_food_restaurant" -> "Fast Food Restaurant".
    """
    if not code:
        return ""
    words = code.replace("-", "_").split("_")
    pretty = " ".join(w.capitalize() for w in words if w)
    # Small normalization pass
    replacements = {
        "And": "and",
        "Of": "of",
        "De": "de",
        "Y": "y",
    }
    parts = []
    for token in pretty.split():
        parts.append(replacements.get(token, token))
    return " ".join(parts)


def get_localized_place_type(place) -> str:
    """Return localized type label for a Place.

    - Try gettext on the Spanish label from get_tipo_display().
    - If language is English and translation is missing, derive from the type code.
    """
    spanish_label = getattr(place, "get_tipo_display", lambda: "")() or getattr(place, "tipo", "")
    translated = gettext(spanish_label)
    lang = (get_language() or "").lower()
    if lang.startswith("en") and translated == spanish_label:
        return derive_english_from_code(getattr(place, "tipo", ""))
    return translated


