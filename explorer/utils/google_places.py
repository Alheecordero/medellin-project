"""Utilidades compartidas para Google Places API (New)."""

from __future__ import annotations

import re
import unicodedata

import requests

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
TEXT_SEARCH_IDS_MASK = "places.id,nextPageToken"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"


def extract_place_id(raw_id: str) -> str:
    """Convierte 'places/ChIJ...' en 'ChIJ...'."""
    if not raw_id:
        return ""
    return raw_id.split("/")[-1] if "/" in raw_id else raw_id


def normalize_name(name: str) -> str:
    """Normaliza un nombre para comparación aproximada."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_text_query(nombre: str, direccion: str | None = None, zona: str | None = None) -> str:
    """Arma el textQuery a partir de datos del lugar."""
    parts = [nombre.strip()]
    if direccion:
        parts.append(direccion.strip())
    if zona:
        parts.append(zona.strip())
    parts.append("Medellín")
    return " ".join(p for p in parts if p)


def text_search_ids_only(
    api_key: str,
    text_query: str,
    lat: float | None = None,
    lng: float | None = None,
    *,
    included_type: str | None = None,
    radius: float = 150.0,
    use_restriction: bool = False,
    timeout: int = 15,
) -> list[str]:
    """
    Text Search pidiendo solo IDs (tarifa IDs Only, gratuita ilimitada).
    Devuelve lista de place_id encontrados (con paginación).

    use_restriction=True usa locationRestriction (círculo duro) en vez de locationBias.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": TEXT_SEARCH_IDS_MASK,
    }
    body: dict = {
        "textQuery": text_query,
        "languageCode": "es",
        "regionCode": "CO",
        "pageSize": 20,
    }
    if included_type:
        body["includedType"] = included_type
        body["strictTypeFiltering"] = False

    if lat is not None and lng is not None:
        circle = {
            "center": {"latitude": lat, "longitude": lng},
            "radius": float(radius),
        }
        if use_restriction:
            body["locationRestriction"] = {"circle": circle}
        else:
            body["locationBias"] = {"circle": circle}

    ids: list[str] = []
    page_token = None

    while True:
        if page_token:
            body["pageToken"] = page_token
        elif "pageToken" in body:
            del body["pageToken"]

        resp = requests.post(TEXT_SEARCH_URL, json=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        for place in data.get("places", []):
            pid = extract_place_id(place.get("id", ""))
            if pid:
                ids.append(pid)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return ids


def classify_id_match(stored_id: str, found_ids: list[str]) -> tuple[str, float | None]:
    """
    Aplica reglas de coincidencia sobre IDs devueltos por Text Search.

    Returns:
        (status, confidence) donde status ∈ matched|not_found|ambiguous|review
    """
    if not found_ids:
        return "not_found", None

    if len(found_ids) == 1:
        if found_ids[0] == stored_id:
            return "matched", 1.0
        return "review", 0.50

    if stored_id in found_ids:
        # Varios candidatos pero el nuestro está entre ellos
        return "matched", round(0.70 + 0.30 / len(found_ids), 2)

    return "ambiguous", round(1.0 / len(found_ids), 2)
