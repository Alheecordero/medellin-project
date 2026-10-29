"""Carga las cartas de Rappi y DiDi en lugares que ya están publicados.

Lee data/partner-menus/out/{place_id}.json. Solo entra un archivo con ok
verdadero y un place_id que ya existe en Places. No crea fichas nuevas y
no toca las fotos de Maps.

  python manage.py import_partner_menus --dry-run
  python manage.py import_partner_menus
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from explorer.models import PlacePartnerDish, PlacePartnerMenu, Places

PLATFORMS = {code for code, _label in PlacePartnerMenu.PLATFORM_CHOICES}


class Command(BaseCommand):
    help = "Importa cartas de partner a Places. No publica lugares nuevos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-dir",
            type=Path,
            default=Path("data/partner-menus/out"),
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        folder = options["input_dir"]
        if not folder.is_dir():
            raise CommandError(f"No existe {folder}")
        files = sorted(folder.glob("*.json"))
        if options["limit"]:
            files = files[: options["limit"]]

        loaded = skipped = waiting = empty = 0
        dishes = 0
        for path in files:
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not doc.get("ok"):
                skipped += 1
                continue
            menus = [menu for menu in doc.get("menus") or [] if menu.get("items")]
            if not menus:
                empty += 1
                continue
            chosen = next((menu for menu in menus if menu.get("chosen")), menus[0])
            platform = str(chosen.get("platform") or "")
            if platform not in PLATFORMS:
                skipped += 1
                continue
            place_id = doc.get("place_id") or path.stem
            lugar = Places.objects.filter(place_id=place_id).only("id").first()
            if lugar is None:
                waiting += 1
                continue
            rows = _dish_rows(chosen)
            if not rows:
                empty += 1
                continue
            if options["dry_run"]:
                loaded += 1
                dishes += len(rows)
                continue
            with transaction.atomic():
                carta, _created = PlacePartnerMenu.objects.update_or_create(
                    lugar=lugar,
                    defaults={
                        "platform": platform,
                        "source_url": (chosen.get("source_url") or "")[:1000],
                        "external_id": str(chosen.get("external_id") or "")[:80],
                        "store_name": (chosen.get("name") or doc.get("name") or "")[:300],
                        "address": chosen.get("address") or "",
                        "partner_urls": list(doc.get("partner_urls") or []),
                        "item_count": len(rows),
                    },
                )
                carta.platos.all().delete()
                PlacePartnerDish.objects.bulk_create(
                    [PlacePartnerDish(carta=carta, **row) for row in rows],
                    batch_size=500,
                )
            loaded += 1
            dishes += len(rows)
            if loaded % 200 == 0:
                self.stdout.write(f"  {loaded} cartas")

        mode = "revisión" if options["dry_run"] else "cargadas"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: {loaded} cartas, {dishes} platos. "
                f"sin ficha: {waiting}. vacías: {empty}. omitidas: {skipped}."
            )
        )


def _dish_rows(menu: dict) -> list[dict]:
    rows = []
    position = 0
    for item in menu.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        price = item.get("price")
        if not isinstance(price, int) or price < 0:
            price = None
        rows.append(
            {
                "external_id": str(item.get("external_id") or "")[:80],
                "name": name[:300],
                "description": item.get("description") or "",
                "price": price,
                "price_text": (item.get("price_text") or "")[:40],
                "original_price_text": (item.get("original_price_text") or "")[:40],
                "image_url": (item.get("image_url") or "")[:1000],
                "section": (item.get("section") or "")[:200],
                "is_available": bool(item.get("is_available", True)),
                "position": position,
            }
        )
        position += 1
    return rows
