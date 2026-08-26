"""
Smoke test de discover_medellin_places: no llama a Google ni escribe en la BD.

Cubre lo que se puede romper en silencio: el limitador de peticiones, el manejo
de 429/backoff, la paginación, la detección de zonas saturadas, la geometría de
subdivisión y el armado del cuerpo de las peticiones.

    python manage.py smoke_test_discovery
"""

from __future__ import annotations

import copy
import threading
import time

import requests
from django.core.management.base import BaseCommand

from explorer.utils.google_places import (
    RateLimiter,
    circle_to_rectangle,
    meters_to_deg_lat,
    nearby_search_ids,
    text_search_ids,
)
from explorer.utils.place_discovery import BBox, TaskSpec, categories, estimate_api_calls


class FakeResponse:
    """Respuesta HTTP mínima con la interfaz que usa la capa de Places."""

    def __init__(self, status: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}
        self.content = b"{}"
        self.text = "{}"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class FakeSession:
    """Sesión que devuelve respuestas preparadas y guarda lo que se envió."""

    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.sent: list[tuple[str, dict, dict]] = []

    def post(self, url, json=None, headers=None, timeout=None):
        # Copia profunda: el body es el mismo dict que se muta entre páginas.
        self.sent.append((url, copy.deepcopy(json), dict(headers or {})))
        return self.responses.pop(0)

    @property
    def calls(self) -> int:
        return len(self.sent)


def _page(ids: list[str], token: str | None = None) -> FakeResponse:
    payload = {"places": [{"id": pid} for pid in ids]}
    if token:
        payload["nextPageToken"] = token
    return FakeResponse(200, payload)


def _ids(count: int, prefix: str = "X") -> list[str]:
    return [f"{prefix}{index}" for index in range(count)]


class Command(BaseCommand):
    help = "Smoke test del descubrimiento de place_id (sin red ni escrituras)."

    def add_arguments(self, parser):
        parser.add_argument("--verbose", action="store_true")

    def handle(self, *args, **options):
        self.verbose = bool(options["verbose"])
        self.failures: list[str] = []

        self.stdout.write(self.style.MIGRATE_HEADING("SMOKE TEST DISCOVERY"))
        self._test_rate_limiter()
        self._test_retries()
        self._test_pagination()
        self._test_request_body()
        self._test_nearby()
        self._test_geometry()
        self._test_categories()

        if self.failures:
            self.stdout.write(self.style.ERROR("FAILURES:"))
            for failure in self.failures:
                self.stdout.write(self.style.ERROR(f"- {failure}"))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("OK: la lógica de descubrimiento se comporta."))

    def _expect(self, name: str, ok: bool, detail: object = "") -> None:
        if ok:
            if self.verbose:
                self.stdout.write(f"  ok   {name}")
            return
        self.failures.append(f"{name} {detail}".strip())

    # ── limitador ────────────────────────────────────────────────

    def _test_rate_limiter(self) -> None:
        limiter = RateLimiter(20.0)
        acquired: list[float] = []
        lock = threading.Lock()

        def worker():
            for _ in range(10):
                limiter.acquire()
                with lock:
                    acquired.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        start = time.monotonic()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        elapsed = time.monotonic() - start

        self._expect("el limitador no se bloquea con varios hilos", len(acquired) == 40, len(acquired))
        self._expect("ningún hilo quedó vivo", not any(t.is_alive() for t in threads))
        self._expect(
            "respeta el techo de peticiones por segundo",
            len(acquired) / max(elapsed, 0.001) <= 26,
            f"{len(acquired) / max(elapsed, 0.001):.1f} req/s",
        )

        penalized = RateLimiter(10.0)
        penalized.penalize()
        self._expect("un 429 baja el ritmo", penalized.qps == 5.0, penalized.qps)
        for _ in range(30):
            penalized.recover()
        self._expect("el ritmo se recupera sin pasarse", penalized.qps == 10.0, penalized.qps)

    # ── reintentos ───────────────────────────────────────────────

    def _test_retries(self) -> None:
        session = FakeSession(
            [
                FakeResponse(429, {}, {"Retry-After": "0"}),
                FakeResponse(429, {}),
                _page(_ids(3)),
            ]
        )
        limiter = RateLimiter(10.0)
        result = text_search_ids(
            "k", "bar", session=session, rate_limiter=limiter, retry_delay=0.01, retries=4
        )
        self._expect("reintenta tras un 429", result.ids == _ids(3), result.ids)
        self._expect("cuenta todas las llamadas", result.api_calls == 3, result.api_calls)
        self._expect("cuenta los 429", result.rate_limited == 2, result.rate_limited)
        self._expect("los 429 bajan el ritmo global", limiter.qps < 10.0, limiter.qps)

        session = FakeSession([FakeResponse(429, {}, {"Retry-After": "0"}) for _ in range(4)])
        try:
            text_search_ids("k", "bar", session=session, retry_delay=0.01, retries=3)
            self._expect("un 429 permanente termina en error", False)
        except requests.HTTPError as exc:
            partial = getattr(exc, "search_result", None)
            self._expect("un 429 permanente termina en error", True)
            self._expect("la excepción trae el parcial", partial is not None)
            self._expect(
                "el parcial cuenta los intentos",
                partial is not None and partial.api_calls == 4,
                getattr(partial, "api_calls", None),
            )

        session = FakeSession([FakeResponse(500, {}), FakeResponse(500, {}), _page(_ids(1))])
        start = time.monotonic()
        result = text_search_ids("k", "bar", session=session, retry_delay=0.05, retries=3)
        elapsed = time.monotonic() - start
        self._expect("reintenta los 5xx", result.ids == ["X0"], result.ids)
        self._expect("el backoff crece", elapsed >= 0.14, f"{elapsed:.3f}s")

        session = FakeSession([FakeResponse(429, {}, {"Retry-After": "0.4"}), _page(_ids(1))])
        start = time.monotonic()
        text_search_ids("k", "bar", session=session, retry_delay=0.01, retries=2)
        self._expect(
            "respeta Retry-After", time.monotonic() - start >= 0.39, f"{time.monotonic() - start:.3f}s"
        )

        session = FakeSession([FakeResponse(400, {"error": {"message": "API key not valid"}})])
        try:
            text_search_ids("k", "bar", session=session, retries=4, retry_delay=0.01)
            self._expect("un 400 no se reintenta", False)
        except requests.HTTPError:
            self._expect("un 400 no se reintenta", session.calls == 1, session.calls)

    # ── paginación ───────────────────────────────────────────────

    def _test_pagination(self) -> None:
        session = FakeSession(
            [_page(_ids(20, "a"), "t1"), _page(_ids(20, "b"), "t2"), _page(_ids(20, "c"))]
        )
        result = text_search_ids("k", "bar", session=session)
        self._expect("consume las 3 páginas", result.pages == 3, result.pages)
        self._expect("acumula los 60 ids", len(result.ids) == 60, len(result.ids))
        self._expect("60 ids ⇒ zona saturada", result.truncated is True)
        self._expect("reenvía el pageToken", session.sent[1][1].get("pageToken") == "t1")
        self._expect("el pageToken avanza", session.sent[2][1].get("pageToken") == "t2")

        session = FakeSession([_page(_ids(5))])
        result = text_search_ids("k", "bar", session=session)
        self._expect("una página corta no está saturada", result.truncated is False)

        session = FakeSession([_page(_ids(20, "a"), "t1")])
        result = text_search_ids("k", "bar", session=session, max_pages=1)
        self._expect("token pendiente ⇒ saturada", result.truncated is True)

        session = FakeSession([_page(["dup", "dup", "otro"])])
        result = text_search_ids("k", "bar", session=session)
        self._expect("deduplica la respuesta", result.ids == ["dup", "otro"], result.ids)

    # ── cuerpo de la petición ────────────────────────────────────

    def _test_request_body(self) -> None:
        session = FakeSession([_page(_ids(1))])
        text_search_ids(
            "k",
            "restaurante en El Poblado",
            included_type="restaurant",
            rectangle=(6.1, -75.6, 6.3, -75.5),
            rank_preference="DISTANCE",
            session=session,
        )
        url, body, headers = session.sent[0]
        restriction = body.get("locationRestriction", {})
        self._expect("Text Search usa rectángulo", "rectangle" in restriction)
        self._expect("Text Search nunca manda círculo en restriction", "circle" not in restriction)
        self._expect(
            "esquina suroeste correcta",
            restriction["rectangle"]["low"] == {"latitude": 6.1, "longitude": -75.6},
            restriction.get("rectangle"),
        )
        self._expect("manda el rankPreference", body.get("rankPreference") == "DISTANCE")
        self._expect("manda el includedType", body.get("includedType") == "restaurant")
        self._expect("no filtra estrictamente por tipo", body.get("strictTypeFiltering") is False)
        self._expect(
            "field mask de solo ids",
            headers.get("X-Goog-FieldMask") == "places.id,nextPageToken",
            headers.get("X-Goog-FieldMask"),
        )

        session = FakeSession([_page(_ids(1))])
        text_search_ids("k", "bar", lat=6.2, lng=-75.5, radius=800, session=session)
        body = session.sent[0][1]
        self._expect("lat/lng ⇒ locationBias circle", "circle" in body.get("locationBias", {}))

        session = FakeSession([_page(_ids(1))])
        text_search_ids(
            "k", "bar", lat=6.2, lng=-75.5, radius=1000, use_restriction=True, session=session
        )
        self._expect(
            "use_restriction convierte el círculo en rectángulo",
            "rectangle" in session.sent[0][1].get("locationRestriction", {}),
        )

        session = FakeSession([_page(_ids(1))])
        text_search_ids("k", "bar", lat=6.2, lng=-75.5, radius=99999, session=session)
        self._expect(
            "el radio se topa en 50 km",
            session.sent[0][1]["locationBias"]["circle"]["radius"] == 50000.0,
        )

    # ── nearby ───────────────────────────────────────────────────

    def _test_nearby(self) -> None:
        session = FakeSession([FakeResponse(200, {"places": [{"id": f"n{i}"} for i in range(20)]})])
        result = nearby_search_ids(
            "k", 6.2, -75.5, 400, included_types=["restaurant"], session=session
        )
        body, headers = session.sent[0][1], session.sent[0][2]
        self._expect("20 resultados ⇒ subdividir", result.truncated is True)
        self._expect("Nearby no pagina", result.api_calls == 1 and result.pages == 1)
        self._expect("Nearby usa círculo", "circle" in body.get("locationRestriction", {}))
        self._expect("Nearby pide 20 como máximo", body.get("maxResultCount") == 20)
        self._expect("Nearby manda includedTypes", body.get("includedTypes") == ["restaurant"])
        self._expect("Nearby pide solo ids", headers.get("X-Goog-FieldMask") == "places.id")

        session = FakeSession([FakeResponse(200, {"places": [{"id": "n1"}]})])
        result = nearby_search_ids("k", 6.2, -75.5, 400, session=session)
        self._expect("pocos resultados ⇒ no subdividir", result.truncated is False)

    # ── geometría ────────────────────────────────────────────────

    def _test_geometry(self) -> None:
        box = BBox(6.17, -75.60, 6.23, -75.54)
        quads = box.quadrants()
        parent_area = (box.lat_max - box.lat_min) * (box.lng_max - box.lng_min)
        children_area = sum((q.lat_max - q.lat_min) * (q.lng_max - q.lng_min) for q in quads)
        self._expect("4 cuadrantes", len(quads) == 4)
        self._expect(
            "los cuadrantes cubren el padre sin sobrar",
            abs(parent_area - children_area) < 1e-12,
        )
        self._expect("cuadrantes distintos", len({q.as_tuple() for q in quads}) == 4)
        self._expect("el radio del hijo es menor", quads[0].radius_m < box.radius_m)
        self._expect("radio en metros plausible", 4000 < box.radius_m < 5500, box.radius_m)

        cells = box.grid(400.0)
        self._expect("la malla cubre el área", 100 < len(cells) < 400, len(cells))
        self._expect(
            "las celdas no se salen del área",
            all(
                c.lat_min >= box.lat_min - 1e-9
                and c.lat_max <= box.lat_max + 1e-9
                and c.lng_min >= box.lng_min - 1e-9
                and c.lng_max <= box.lng_max + 1e-9
                for c in cells
            ),
        )
        self._expect(
            "el radio de celda respeta lo pedido",
            max(cell.radius_m for cell in cells) <= 430,
        )

        lat_min, lng_min, lat_max, lng_max = circle_to_rectangle(6.20, -75.57, 1000.0)
        self._expect(
            "el rectángulo encierra el círculo",
            lat_min < 6.20 < lat_max and lng_min < -75.57 < lng_max,
        )
        self._expect(
            "la altura equivale al diámetro",
            abs((lat_max - lat_min) - 2 * meters_to_deg_lat(1000.0)) < 1e-12,
        )

        spec = TaskSpec(
            kind="text",
            area_name="El Poblado",
            area_slug="el-poblado",
            area_kind="comuna",
            category="restaurante",
            included_type="restaurant",
            query="restaurante en El Poblado, Medellín",
            rank_preference="RELEVANCE",
            bbox=box,
        )
        self._expect("la firma es estable", spec.signature == TaskSpec(**spec.__dict__).signature)
        other = TaskSpec(**{**spec.__dict__, "rank_preference": "DISTANCE"})
        self._expect("otro ranking ⇒ otra firma", spec.signature != other.signature)

        children = spec.children()
        grandchildren = children[0].children()
        self._expect("4 subtareas", len(children) == 4)
        self._expect("las subtareas suben de nivel", all(c.depth == 1 for c in children))
        self._expect("firmas de subtareas únicas", len({c.signature for c in children}) == 4)
        self._expect("la subtarea no repite al padre", spec.signature not in {c.signature for c in children})
        self._expect("la subtarea hereda la consulta", all(c.query == spec.query for c in children))
        self._expect("segundo nivel de subdivisión", all(g.depth == 2 for g in grandchildren))
        self._expect(
            "el segundo nivel no choca con el primero",
            not {g.signature for g in grandchildren} & {c.signature for c in children},
        )

    # ── categorías ───────────────────────────────────────────────

    def _test_categories(self) -> None:
        cats = categories(("base", "cocina", "generico"))
        self._expect("hay suficientes categorías", len(cats) > 60, len(cats))
        self._expect(
            "sin categorías repetidas",
            len({(c.label, c.included_type) for c in cats}) == len(cats),
        )
        self._expect(
            "las genéricas no llevan includedType",
            all(not c.included_type for c in cats if c.group == "generico"),
        )
        self._expect(
            "las de cocina sí llevan includedType",
            all(c.included_type for c in cats if c.group == "cocina"),
        )
        self._expect("el filtro por grupo funciona", 0 < len(categories(("base",))) < len(cats))
        self._expect("un grupo inexistente no aporta nada", categories(("inventado",)) == [])

        estimate = estimate_api_calls(
            [
                TaskSpec(
                    kind="text",
                    area_name="A",
                    area_slug="a",
                    area_kind="comuna",
                    category="bar",
                    included_type="bar",
                    query="bar en A",
                    rank_preference="RELEVANCE",
                    bbox=BBox(6.1, -75.6, 6.2, -75.5),
                )
            ]
        )
        self._expect("la estimación cuenta tareas", estimate["text_tasks"] == 1)
        self._expect("la estimación cuenta llamadas", estimate["text_calls"] == 2)
