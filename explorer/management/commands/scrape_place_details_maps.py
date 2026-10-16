"""
Scrape ficha completa desde Google Maps (Playwright, $0 API) → GooglePlaceDetails.

Uso:
  python manage.py scrape_place_details_maps --limit 20
  python manage.py scrape_place_details_maps --limit 500 --shard-index 0 --shard-count 4
  python manage.py scrape_place_details_maps --place-id ChIJ...
  python manage.py scrape_place_details_maps --area "Envigado" --limit 50 --pause 2
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone as dj_tz

from explorer.models import GooglePlaceDetails, GooglePlaceId
from explorer.scraping.maps_place_overview import SCRAPER_VERSION, scrape_place_overview
from explorer.utils.place_classify import classify_place


class Command(BaseCommand):
    help = (
        "Scrapea overview de Google Maps (sin Places API) y guarda staging "
        "en GooglePlaceDetails. Pensado para workers en VPS scraper → DB prod."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="Máximo de IDs a procesar")
        parser.add_argument("--place-id", default="", help="Procesar un solo place_id")
        parser.add_argument("--area", default="", help="Filtrar area_names (substring)")
        parser.add_argument(
            "--family",
            default="",
            help="Tras scrapear, solo contar/filtrar dry-run por tipo_family (food, nightlife…)",
        )
        parser.add_argument(
            "--only-sin-ficha",
            action="store_true",
            help="Solo IDs sin ficha en Places (default: sin GooglePlaceDetails ok)",
        )
        parser.add_argument("--shard-index", type=int, default=0)
        parser.add_argument("--shard-count", type=int, default=1)
        parser.add_argument("--pause", type=float, default=2.0, help="Segundos entre jobs")
        parser.add_argument("--wait-ms", type=int, default=8000, help="Espera carga panel Maps")
        parser.add_argument(
            "--max-photos",
            type=int,
            default=0,
            help="0 = no guardar URLs de fotos (Plan 1). Fase 2 scrapea media de seleccionados.",
        )
        parser.add_argument("--max-reviews", type=int, default=5)
        parser.add_argument(
            "--chrome",
            default="/usr/bin/google-chrome",
            help="Ruta al binario Chrome",
        )
        parser.add_argument("--headed", action="store_true", help="Chrome con UI")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo listar cola, no scrapear ni escribir DB",
        )
        parser.add_argument(
            "--refetch-errors",
            action="store_true",
            help="Incluir filas con fetch_status error/blocked/not_found",
        )

    def handle(self, *args, **options):
        place_ids = self._queue(options)
        if not place_ids:
            self.stdout.write(self.style.WARNING("Cola vacía."))
            return

        self.stdout.write(
            f"Cola: {len(place_ids)} IDs | shard {options['shard_index']}/"
            f"{options['shard_count']} | pause={options['pause']}s"
        )
        if options["dry_run"]:
            for pid in place_ids[:50]:
                self.stdout.write(f"  {pid}")
            if len(place_ids) > 50:
                self.stdout.write(f"  … +{len(place_ids) - 50} más")
            return

        ok = err = blocked = not_found = 0
        for i, place_id in enumerate(place_ids, 1):
            t0 = time.time()
            result = scrape_place_overview(
                place_id,
                headless=not options["headed"],
                chrome_path=options["chrome"],
                wait_ms=options["wait_ms"],
                max_photos=options["max_photos"],
                max_reviews=options["max_reviews"],
            )
            status = result.get("status") or "error"
            self._upsert(place_id, result)

            elapsed = time.time() - t0
            name = ""
            family = ""
            if result.get("data"):
                name = (result["data"].get("name") or "")[:40]
            detail = GooglePlaceDetails.objects.filter(place_id=place_id).first()
            if detail:
                family = detail.tipo_family or ""
            mark = {"ok": "✓", "blocked": "⛔", "not_found": "?", "error": "✗"}.get(
                status, "?"
            )
            self.stdout.write(
                f"[{i}/{len(place_ids)}] {mark} {status:9} {elapsed:5.1f}s  "
                f"{family:16} {place_id[:22]}  {name}"
            )

            if status == "ok":
                ok += 1
            elif status == "blocked":
                blocked += 1
            elif status == "not_found":
                not_found += 1
            else:
                err += 1

            if status == "blocked":
                self.stdout.write(
                    self.style.ERROR("Bloqueo Maps detectado — parando shard.")
                )
                break

            if i < len(place_ids) and options["pause"] > 0:
                time.sleep(options["pause"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Fin: ok={ok} error={err} blocked={blocked} not_found={not_found}"
            )
        )

    def _queue(self, options) -> list[str]:
        if options["place_id"]:
            return [options["place_id"].strip()]

        qs = GooglePlaceId.objects.all()
        if options["only_sin_ficha"]:
            qs = qs.sin_ficha()
        if options["area"]:
            qs = qs.filter(area_names__icontains=options["area"].strip())

        if options["refetch_errors"]:
            qs = qs.filter(
                Q(details__isnull=True)
                | Q(details__fetch_status__in=["error", "blocked", "not_found"])
            )
        else:
            qs = qs.sin_details()

        shard_count = max(1, options["shard_count"])
        shard_index = options["shard_index"] % shard_count
        # Partición estable por hash del place_id
        ids = list(qs.order_by("place_id").values_list("place_id", flat=True))
        ids = [pid for pid in ids if abs(hash(pid)) % shard_count == shard_index]
        limit = max(0, options["limit"])
        if limit:
            ids = ids[:limit]
        return ids

    def _upsert(self, place_id: str, result: dict) -> None:
        data = result.get("data") or {}
        status = result.get("status") or "error"
        now = dj_tz.now()

        catalog = GooglePlaceId.objects.filter(place_id=place_id).first()
        lat = data.get("lat")
        lng = data.get("lng")
        ubicacion = None
        if lat is not None and lng is not None:
            try:
                ubicacion = Point(float(lng), float(lat), srid=4326)
            except (TypeError, ValueError):
                ubicacion = None

        review_count = data.get("review_count")
        if isinstance(review_count, str):
            digits = "".join(c for c in review_count if c.isdigit())
            review_count = int(digits) if digits else None

        classification = classify_place(
            maps_category=data.get("category"),
            scan_types=list(catalog.scan_types or []) if catalog else [],
            search_queries=list(catalog.search_queries or []) if catalog else None,
            body_snippet=data.get("body_snippet"),
        )

        defaults = {
            "catalog_entry": catalog,
            "cid": (data.get("cid") or "")[:80],
            "display_name": (data.get("name") or "")[:500],
            "category": (data.get("category") or "")[:200],
            "primary_type": (classification.get("primary_type") or "")[:100],
            "tipo": classification.get("tipo") or "otros",
            "tipo_family": classification.get("tipo_family") or "other",
            "tipo_source": classification.get("tipo_source") or "",
            "tipo_confidence": classification.get("tipo_confidence"),
            "types": classification.get("google_types") or [],
            "formatted_address": data.get("address") or "",
            "plus_code": (data.get("plus_code") or "")[:120],
            "lat": lat,
            "lng": lng,
            "ubicacion": ubicacion,
            "rating": data.get("rating"),
            "user_rating_count": review_count,
            "phone": (data.get("phone") or "")[:80],
            "website_uri": (data.get("website") or "")[:1000],
            "google_maps_uri": (result.get("final_url") or data.get("page_url") or "")[
                :1000
            ],
            "menu_uri": (data.get("menu_uri") or "")[:1000],
            "open_now": data.get("open_now"),
            "hours_text": data.get("hours_text") or "",
            "dine_in": data.get("dine_in"),
            "takeout": data.get("takeout"),
            "delivery": data.get("delivery"),
            "amenities": data.get("amenities") or None,
            "reviews": data.get("reviews") or None,
            # Plan 1: no persistir fotos; Plan 2 = seleccionados
            "photo_urls": None,
            "fetched_at": now,
            "fetch_status": status,
            "error_message": (result.get("error") or "")[:2000],
            "scraper_version": result.get("scraper_version") or SCRAPER_VERSION,
            "raw_json": {
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "result_status": status,
                "final_url": result.get("final_url"),
                "classification": classification,
                "data": data,
            },
        }

        # URLField tolera vacío; evita ValidationError con valores raros
        for url_field in ("website_uri", "google_maps_uri", "menu_uri"):
            val = defaults.get(url_field) or ""
            if val and not (val.startswith("http://") or val.startswith("https://")):
                defaults[url_field] = ""

        GooglePlaceDetails.objects.update_or_create(
            place_id=place_id,
            defaults=defaults,
        )
