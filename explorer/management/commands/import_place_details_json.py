"""
Importa JSON de overview Maps (VPS scraper) → GooglePlaceDetails + clasificación.

Uso en hserver3:
  python manage.py import_place_details_json /tmp/batch.json
  python manage.py import_place_details_json /tmp/one.json --stdin   # no
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as dj_tz

from explorer.models import GooglePlaceDetails, GooglePlaceId
from explorer.scraping.maps_place_overview import SCRAPER_VERSION
from explorer.utils.place_classify import classify_place


class Command(BaseCommand):
    help = "Importa resultados scrapeados (JSON) a GooglePlaceDetails con clasificación."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default="", help="Archivo JSON (obj o lista)")
        parser.add_argument(
            "--stdin",
            action="store_true",
            help="Leer JSON desde stdin",
        )

    def handle(self, *args, **options):
        if options["stdin"]:
            import sys

            payload = json.load(sys.stdin)
        else:
            path = Path(options["path"])
            if not path.exists():
                raise CommandError(f"No existe {path}")
            payload = json.loads(path.read_text(encoding="utf-8"))

        items = payload if isinstance(payload, list) else [payload]
        ok = err = 0
        for result in items:
            place_id = result.get("place_id")
            if not place_id:
                err += 1
                continue
            try:
                self._upsert(place_id, result)
                status = result.get("status") or "error"
                data = result.get("data") or {}
                detail = GooglePlaceDetails.objects.get(place_id=place_id)
                self.stdout.write(
                    f"  {status:9} family={detail.tipo_family:16} "
                    f"tipo={detail.tipo:24} {(data.get('name') or '')[:40]}"
                )
                ok += 1
            except Exception as exc:
                err += 1
                self.stdout.write(self.style.ERROR(f"  fail {place_id}: {exc}"))
        self.stdout.write(self.style.SUCCESS(f"Importados ok={ok} err={err}"))

    def _upsert(self, place_id: str, result: dict) -> None:
        data = result.get("data") or {}
        status = result.get("status") or "error"
        now = dj_tz.now()
        catalog = GooglePlaceId.objects.filter(place_id=place_id).first()

        lat, lng = data.get("lat"), data.get("lng")
        ubicacion = None
        if lat is not None and lng is not None:
            try:
                ubicacion = Point(float(lng), float(lat), srid=4326)
            except (TypeError, ValueError):
                pass

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
            "website_uri": "",
            "google_maps_uri": "",
            "menu_uri": "",
            "open_now": data.get("open_now"),
            "hours_text": data.get("hours_text") or "",
            "dine_in": data.get("dine_in"),
            "takeout": data.get("takeout"),
            "delivery": data.get("delivery"),
            "amenities": data.get("amenities") or None,
            "reviews": data.get("reviews") or None,
            "photo_urls": data.get("photo_urls") or None,
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
        for field, key in (
            ("website_uri", "website"),
            ("menu_uri", "menu_uri"),
        ):
            val = (data.get(key) or "")[:1000]
            if val.startswith("http://") or val.startswith("https://"):
                defaults[field] = val
        gmaps = (result.get("final_url") or data.get("page_url") or "")[:1000]
        if gmaps.startswith("http://") or gmaps.startswith("https://"):
            defaults["google_maps_uri"] = gmaps

        GooglePlaceDetails.objects.update_or_create(place_id=place_id, defaults=defaults)
