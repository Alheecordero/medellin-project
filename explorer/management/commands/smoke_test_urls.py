from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from django.core.management.base import BaseCommand
from django.test import Client
from django.urls import reverse

from explorer.models import Places, RegionOSM


@dataclass
class Case:
    name: str
    path: str
    method: str = "GET"
    kwargs: Optional[dict[str, Any]] = None


class Command(BaseCommand):
    help = "Smoke test de URLs: hace requests con Django test client y reporta errores (500/TemplateSyntaxError)."

    def add_arguments(self, parser):
        # Usamos 127.0.0.1 por defecto para evitar DisallowedHost cuando ALLOWED_HOSTS no incluye 'testserver'
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--verbose", action="store_true")

    def handle(self, *args, **opts):
        host = opts["host"]
        verbose = bool(opts["verbose"])

        c = Client(HTTP_HOST=host)

        # Pick sample data for slugged routes.
        # Importante: algunas vistas (detail/progressive APIs) filtran por tiene_fotos=True y/o requieren ubicación.
        sample_place_detail = (
            Places.objects.filter(tiene_fotos=True)
            .exclude(slug__isnull=True)
            .exclude(slug__exact="")
            .order_by("-rating", "id")
            .only("slug")
            .first()
        )
        sample_place_geo = (
            Places.objects.filter(tiene_fotos=True, ubicacion__isnull=False)
            .exclude(slug__isnull=True)
            .exclude(slug__exact="")
            .order_by("-rating", "id")
            .only("slug")
            .first()
        )
        sample_region = RegionOSM.objects.exclude(slug__isnull=True).exclude(slug__exact="").order_by("id").only("slug", "osm_id").first()

        place_slug = getattr(sample_place_detail, "slug", None) or "demo"
        place_slug_geo = getattr(sample_place_geo, "slug", None) or place_slug
        comuna_slug = getattr(sample_region, "slug", None) or "demo"
        comuna_osm_id = getattr(sample_region, "osm_id", None) or "all"

        def safe_reverse(url_name: str, kwargs: Optional[dict[str, Any]] = None) -> str:
            return reverse(url_name, kwargs=kwargs)

        cases: list[Case] = [
            Case("home", safe_reverse("explorer:home")),
            Case("about_es", safe_reverse("explorer:about_es")),
            Case("about", safe_reverse("explorer:about")),
            Case("semantic_search_page", safe_reverse("explorer:semantic_search_page")),
            Case("lugares_list", safe_reverse("explorer:lugares_list")),
            Case("lugares_por_comuna", safe_reverse("explorer:lugares_por_comuna", {"comuna_slug": comuna_slug})),
            Case("lugares_detail", safe_reverse("explorer:lugares_detail", {"slug": place_slug})),
            Case("reviews_lugar", safe_reverse("explorer:reviews_lugar", {"slug": place_slug})),
            # APIs (GET)
            Case("api_filtros_ajax", safe_reverse("explorer:filtros_ajax")),
            Case("api_lugares_cercanos_ajax_view", safe_reverse("explorer:lugares_cercanos_ajax")),
            Case("api_semantic_search_ajax", safe_reverse("explorer:semantic_search_ajax")),
            Case("api_lugares_slug_cercanos", safe_reverse("explorer:lugares_cercanos_ajax", {"slug": place_slug_geo})),
            Case("api_lugares_slug_similares", safe_reverse("explorer:lugares_similares_ajax", {"slug": place_slug_geo})),
            Case("api_lugares_slug_comuna", safe_reverse("explorer:lugares_comuna_ajax", {"slug": place_slug_geo})),
            # translate_review_api es POST; lo probamos con payload mínimo.
            Case("api_translate_review", safe_reverse("explorer:translate_review_api"), method="POST"),
            # Global (no namespace)
            Case("sitemap", "/sitemap.xml"),
            Case("jsi18n_es", "/jsi18n/"),
            Case("jsi18n_en", "/en/jsi18n/"),
        ]

        self.stdout.write(self.style.MIGRATE_HEADING("SMOKE TEST URLS"))
        self.stdout.write(f"Sample slugs: place={place_slug!r} place_geo={place_slug_geo!r} comuna={comuna_slug!r}")

        failures: list[str] = []
        warnings: list[str] = []
        for case in cases:
            try:
                if case.method == "POST":
                    resp = c.post(
                        case.path,
                        data={"text": "hola", "target": "en"},
                        content_type="application/json",
                        follow=True,
                    )
                else:
                    # Algunos endpoints API requieren query params mínimos; añadimos defaults seguros.
                    if case.name == "api_semantic_search_ajax":
                        resp = c.get(case.path, data={"q": "ping", "top": 1}, follow=True)
                    elif case.name == "api_filtros_ajax":
                        resp = c.get(case.path, data={"area": comuna_osm_id, "categoria": "all", "caracteristica": "all"}, follow=True)
                    elif case.name == "api_lugares_cercanos_ajax_view":
                        resp = c.get(case.path, data={"lat": 6.2442, "lng": -75.5812}, follow=True)
                    else:
                        resp = c.get(case.path, follow=True)
            except Exception as e:
                failures.append(f"{case.name}: EXCEPTION {type(e).__name__}: {e}")
                continue

            code = resp.status_code
            if verbose:
                self.stdout.write(f"{case.name}: {case.method} {case.path} -> {code}")

            if code >= 500:
                failures.append(f"{case.name}: {case.method} {case.path} -> {code}")
            elif code >= 400:
                warnings.append(f"{case.name}: {case.method} {case.path} -> {code}")

        if failures:
            self.stdout.write(self.style.ERROR("FAILURES:"))
            for f in failures:
                self.stdout.write(self.style.ERROR(f"- {f}"))
            raise SystemExit(1)

        if warnings:
            self.stdout.write(self.style.WARNING("WARNINGS (4xx):"))
            for w in warnings:
                self.stdout.write(self.style.WARNING(f"- {w}"))

        self.stdout.write(self.style.SUCCESS("OK: no se detectaron 500/exceptions en las rutas probadas."))


