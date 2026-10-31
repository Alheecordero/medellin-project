"""Carga el borrador de guías sin publicarlo.

Cada parada solo entra si su place_id ya está en Places. Las que faltan
se listan y se quedan en el JSON. Parque Arví y Guatapé, que no tienen
place_id, también se listan.

  python manage.py import_guias_borrador --dry-run
  python manage.py import_guias_borrador
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from explorer.models import CuratedGuide, CuratedGuideItem, GooglePlaceDetails, PendingPlace, Places

CATEGORIES = {code for code, _label in CuratedGuide._meta.get_field("categoria").choices}
# Borradores con las categorías de antes de la migración 0040.
CATEGORIAS_ANTIGUAS = {"sector": "zona", "daytrip": "escapada", "gastronomia": "plan", "actividad": "plan", "audiencia": "plan"}


class Command(BaseCommand):
    help = "Importa data/medellin-anchors/guias-borrador.json como guías sin publicar."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            type=Path,
            default=Path("data/medellin-anchors/guias-borrador.json"),
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = options["input"]
        if not path.is_file():
            raise CommandError(f"No existe {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        linked = missing = 0
        for guide in payload.get("guias") or []:
            categoria = CATEGORIAS_ANTIGUAS.get(guide.get("categoria"), guide.get("categoria"))
            if categoria not in CATEGORIES:
                categoria = "zona"
            stops = guide.get("paradas") or []
            ready = []
            absent = []
            for stop in stops:
                place_id = stop.get("place_id")
                nombre = stop.get("nombre") or ""
                if not place_id:
                    absent.append(f"{nombre} (sin place_id)")
                    continue
                lugar = Places.objects.filter(place_id=place_id).only(
                    "id", "nombre", "tipo", "solo_en_guia"
                ).first()
                if lugar is None:
                    where = _where(place_id)
                    absent.append(f"{nombre} [{where}]")
                    continue
                ready.append((stop, lugar))
            self.stdout.write(
                f"{guide.get('titulo')}: {len(ready)} paradas con ficha, {len(absent)} pendientes"
            )
            for line in absent:
                self.stdout.write(f"  falta  {line}")
            linked += len(ready)
            missing += len(absent)
            if options["dry_run"] or not ready:
                continue
            with transaction.atomic():
                guia, created = CuratedGuide.objects.update_or_create(
                    slug=guide.get("slug") or "",
                    defaults={
                        "titulo": (guide.get("titulo") or "")[:200],
                        "descripcion": guide.get("descripcion") or "",
                        "como_recorrer": guide.get("como_recorrer") or "",
                        "categoria": categoria,
                        "orden": guide.get("orden") or 0,
                    },
                )
                if created:
                    guia.publicado = False
                    guia.save(update_fields=["publicado"])
                for stop, lugar in ready:
                    if not _es_comida(lugar.tipo) and not lugar.solo_en_guia:
                        Places.objects.filter(pk=lugar.pk).update(solo_en_guia=True)
                    CuratedGuideItem.objects.update_or_create(
                        guia=guia,
                        lugar=lugar,
                        defaults={
                            "posicion": stop.get("posicion") or 1,
                            "comentario": stop.get("por_que") or "",
                            "destacado": (stop.get("destacado") or "")[:50],
                            "como_llegar": (stop.get("como_llegar") or "")[:300],
                            "advertencia": (stop.get("advertencia") or "")[:300],
                        },
                    )
        mode = "revisión" if options["dry_run"] else "listas"
        self.stdout.write(
            self.style.SUCCESS(f"{mode}: {linked} paradas con ficha, {missing} todavía fuera.")
        )


_COMIDA = {
    "restaurant",
    "cafe",
    "cafeteria",
    "bar",
    "pub",
    "wine_bar",
    "night_club",
    "karaoke",
    "food",
    "food_court",
    "diner",
    "steak_house",
    "meal_takeaway",
    "meal_delivery",
    "sandwich_shop",
    "cat_cafe",
    "dog_cafe",
    "bar_and_grill",
}


def _es_comida(tipo: str) -> bool:
    tipo = tipo or ""
    return tipo in _COMIDA or tipo.endswith("_restaurant")


def _where(place_id: str) -> str:
    if GooglePlaceDetails.objects.filter(place_id=place_id).exists():
        return "en detalle Maps, sin ficha pública"
    pending = PendingPlace.objects.filter(place_id=place_id).only("status").first()
    if pending:
        return f"pendiente ({pending.status})"
    return "fuera del catálogo"
