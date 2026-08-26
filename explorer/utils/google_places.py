"""Utilidades compartidas para Google Places API (New)."""

from __future__ import annotations

import math
import random
import re
import threading
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass, field

import requests

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
TEXT_SEARCH_IDS_MASK = "places.id,nextPageToken"
NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
NEARBY_SEARCH_IDS_MASK = "places.id"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# Text Search entrega como máximo 3 páginas de 20 (60 resultados) por consulta.
TEXT_SEARCH_MAX_PAGES = 3
TEXT_SEARCH_PAGE_SIZE = 20
# Nearby Search no pagina: 20 resultados por llamada.
NEARBY_MAX_RESULTS = 20
# Radio máximo aceptado por la API en un círculo.
MAX_CIRCLE_RADIUS_M = 50000.0


def _is_retryable_error(exc: requests.RequestException) -> bool:
    """Solo reintenta errores transitorios de red, rate limit o servidor."""
    if not isinstance(exc, requests.HTTPError) or exc.response is None:
        return True
    return exc.response.status_code == 429 or exc.response.status_code >= 500


class RateLimiter:
    """
    Limitador de peticiones por segundo compartido entre hilos.

    `penalize()` baja el ritmo cuando Google responde 429; `recover()` lo
    devuelve poco a poco al objetivo para no quedarse lento el resto del barrido.
    """

    def __init__(self, qps: float):
        self.target_qps = max(0.1, float(qps))
        self._qps = self.target_qps
        self._next_at = 0.0
        self._lock = threading.Lock()

    @property
    def qps(self) -> float:
        return self._qps

    def acquire(self) -> None:
        """Reserva el siguiente turno y espera hasta que llegue."""
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_at)
            self._next_at = slot + (1.0 / self._qps)
        delay = slot - now
        if delay > 0:
            time.sleep(delay)

    def penalize(self, factor: float = 0.5, floor: float = 0.5) -> None:
        with self._lock:
            self._qps = max(floor, self._qps * factor)

    def recover(self, factor: float = 1.1) -> None:
        with self._lock:
            self._qps = min(self.target_qps, self._qps * factor)


@dataclass
class SearchResult:
    """Resultado de una búsqueda de IDs, con métricas para el reporte."""

    ids: list[str] = field(default_factory=list)
    api_calls: int = 0
    pages: int = 0
    rate_limited: int = 0
    # Quedaban más resultados de los que la API deja paginar (zona saturada).
    truncated: bool = False


def _post_places(
    url: str,
    body: dict,
    *,
    api_key: str,
    field_mask: str,
    timeout: int = 15,
    retries: int = 3,
    retry_delay: float = 1.0,
    rate_limiter: RateLimiter | None = None,
    session: requests.Session | None = None,
    counters: SearchResult | None = None,
) -> dict:
    """
    POST a Places API (New) con backoff exponencial y manejo explícito de 429.

    Respeta `Retry-After` cuando Google lo envía y baja el ritmo del
    `RateLimiter` compartido para que el resto de los hilos también ceda.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }
    poster = session.post if session is not None else requests.post
    last_error: requests.RequestException | None = None

    for attempt in range(retries + 1):
        if rate_limiter is not None:
            rate_limiter.acquire()
        try:
            resp = poster(url, json=body, headers=headers, timeout=timeout)
            if counters is not None:
                counters.api_calls += 1
            resp.raise_for_status()
            if rate_limiter is not None:
                rate_limiter.recover()
            return resp.json()
        except requests.RequestException as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 429:
                if counters is not None:
                    counters.rate_limited += 1
                if rate_limiter is not None:
                    rate_limiter.penalize()
            if attempt >= retries or not _is_retryable_error(exc):
                raise
            time.sleep(_backoff_delay(exc, attempt, retry_delay))

    raise last_error or requests.RequestException("Places API falló sin detalle")


@contextmanager
def _attach_partial(result: SearchResult):
    """
    Cuelga el `SearchResult` parcial de la excepción que se esté propagando.

    Así quien llama puede contar las peticiones que sí se hicieron aunque la
    búsqueda haya terminado en error.
    """
    try:
        yield
    except requests.RequestException as exc:
        exc.search_result = result
        raise


def _backoff_delay(
    exc: requests.RequestException, attempt: int, retry_delay: float
) -> float:
    """Backoff exponencial con jitter; usa Retry-After si Google lo indica."""
    response = getattr(exc, "response", None)
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), retry_delay)
            except ValueError:
                pass
    return retry_delay * (2**attempt) + random.uniform(0, 0.5)


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


def meters_to_deg_lat(meters: float) -> float:
    return meters / 111_320.0


def meters_to_deg_lng(meters: float, lat: float) -> float:
    return meters / (111_320.0 * max(0.1, math.cos(math.radians(lat))))


def circle_to_rectangle(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    """
    Rectángulo que encierra un círculo, como (lat_min, lng_min, lat_max, lng_max).

    Text Search solo acepta rectángulos en `locationRestriction`: mandar un
    círculo devuelve HTTP 400 (Unknown name "circle").
    """
    dlat = meters_to_deg_lat(radius_m)
    dlng = meters_to_deg_lng(radius_m, lat)
    return (lat - dlat, lng - dlng, lat + dlat, lng + dlng)


def _rectangle_body(rectangle: tuple[float, float, float, float]) -> dict:
    lat_min, lng_min, lat_max, lng_max = rectangle
    return {
        "rectangle": {
            "low": {"latitude": lat_min, "longitude": lng_min},
            "high": {"latitude": lat_max, "longitude": lng_max},
        }
    }


def text_search_ids(
    api_key: str,
    text_query: str,
    lat: float | None = None,
    lng: float | None = None,
    *,
    included_type: str | None = None,
    radius: float = 150.0,
    use_restriction: bool = False,
    rectangle: tuple[float, float, float, float] | None = None,
    rank_preference: str | None = None,
    max_pages: int = TEXT_SEARCH_MAX_PAGES,
    timeout: int = 15,
    retries: int = 3,
    retry_delay: float = 1.0,
    rate_limiter: RateLimiter | None = None,
    session: requests.Session | None = None,
) -> SearchResult:
    """
    Text Search pidiendo solo IDs (SKU «Text Search Essentials IDs Only», gratis).

    El FieldMask `places.id,nextPageToken` mantiene la llamada en la tarifa
    gratuita y permite paginar. Devuelve un `SearchResult` con los IDs y las
    métricas de la consulta; `truncated` indica que aún quedaba `nextPageToken`
    al alcanzar `max_pages`, es decir que la zona está saturada.

    Ubicación: `rectangle` (o `use_restriction`) usa `locationRestriction`, que
    obliga a que los resultados caigan dentro. Con lat/lng sueltos se usa
    `locationBias`, que solo prioriza esa zona.
    """
    result = SearchResult()
    body: dict = {
        "textQuery": text_query,
        "languageCode": "es",
        "regionCode": "CO",
        "pageSize": TEXT_SEARCH_PAGE_SIZE,
    }
    if included_type:
        body["includedType"] = included_type
        body["strictTypeFiltering"] = False
    if rank_preference:
        body["rankPreference"] = rank_preference

    if rectangle is None and use_restriction and lat is not None and lng is not None:
        rectangle = circle_to_rectangle(lat, lng, radius)

    if rectangle is not None:
        body["locationRestriction"] = _rectangle_body(rectangle)
    elif lat is not None and lng is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": min(float(radius), MAX_CIRCLE_RADIUS_M),
            }
        }

    seen: set[str] = set()
    page_token: str | None = None
    last_page_size = 0
    max_pages = max(1, max_pages)

    for _ in range(max_pages):
        if page_token:
            body["pageToken"] = page_token
        else:
            body.pop("pageToken", None)

        with _attach_partial(result):
            data = _post_places(
                TEXT_SEARCH_URL,
                body,
                api_key=api_key,
                field_mask=TEXT_SEARCH_IDS_MASK,
                timeout=timeout,
                retries=retries,
                retry_delay=retry_delay,
                rate_limiter=rate_limiter,
                session=session,
                counters=result,
            )
        result.pages += 1
        places = data.get("places", [])
        last_page_size = len(places)

        for place in places:
            pid = extract_place_id(place.get("id", ""))
            if pid and pid not in seen:
                seen.add(pid)
                result.ids.append(pid)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    # Google corta en 60 resultados y deja de enviar nextPageToken en la última
    # página aunque queden lugares: una página final llena es la única señal de
    # que la zona está saturada y hay que subdividirla.
    result.truncated = bool(page_token) or (
        result.pages >= max_pages and last_page_size >= TEXT_SEARCH_PAGE_SIZE
    )
    return result


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
    retries: int = 3,
    retry_delay: float = 1.0,
) -> list[str]:
    """Igual que `text_search_ids` pero devuelve solo la lista de place_id."""
    return text_search_ids(
        api_key,
        text_query,
        lat,
        lng,
        included_type=included_type,
        radius=radius,
        use_restriction=use_restriction,
        timeout=timeout,
        retries=retries,
        retry_delay=retry_delay,
    ).ids


def nearby_search_ids(
    api_key: str,
    lat: float,
    lng: float,
    radius: float,
    *,
    included_types: list[str] | tuple[str, ...] = (),
    excluded_types: list[str] | tuple[str, ...] = (),
    rank_preference: str = "POPULARITY",
    max_result_count: int = NEARBY_MAX_RESULTS,
    timeout: int = 15,
    retries: int = 3,
    retry_delay: float = 1.0,
    rate_limiter: RateLimiter | None = None,
    session: requests.Session | None = None,
) -> SearchResult:
    """
    Nearby Search pidiendo solo IDs. **No es gratis**: Nearby no tiene SKU
    «IDs Only», así que cada llamada se cobra como Nearby Search Pro
    (5.000 gratis al mes y ~$32 por 1.000 después).

    No pagina: si devuelve `max_result_count` marca `truncated=True` para que
    quien llame subdivida la zona y vuelva a buscar.
    """
    result = SearchResult()
    body: dict = {
        "maxResultCount": min(max_result_count, NEARBY_MAX_RESULTS),
        "rankPreference": rank_preference,
        "languageCode": "es",
        "regionCode": "CO",
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": min(float(radius), MAX_CIRCLE_RADIUS_M),
            }
        },
    }
    if included_types:
        body["includedTypes"] = list(included_types)
    if excluded_types:
        body["excludedTypes"] = list(excluded_types)

    with _attach_partial(result):
        data = _post_places(
            NEARBY_SEARCH_URL,
            body,
            api_key=api_key,
            field_mask=NEARBY_SEARCH_IDS_MASK,
            timeout=timeout,
            retries=retries,
            retry_delay=retry_delay,
            rate_limiter=rate_limiter,
            session=session,
            counters=result,
        )
    result.pages = 1

    for place in data.get("places", []):
        pid = extract_place_id(place.get("id", ""))
        if pid and pid not in result.ids:
            result.ids.append(pid)

    result.truncated = len(result.ids) >= min(max_result_count, NEARBY_MAX_RESULTS)
    return result


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
