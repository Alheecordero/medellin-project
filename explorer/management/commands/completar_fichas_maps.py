"""Completa fichas publicadas con lo que GooglePlaceDetails ya tiene, sin llamar a la API.

- Atributos de Maps (`amenities`) → booleanos de Places, solo donde Places no tiene valor.
- Horario de un instante ("Abierto · Cierra a las 9 p.m.") → se borra: caduca enseguida
  y no es un horario semanal.

  python manage.py completar_fichas_maps --dry-run
  python manage.py completar_fichas_maps
"""

from __future__ import annotations

import re
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import BooleanField

from explorer.models import GooglePlaceDetails, Places

HORARIO_INSTANTANEO = re.compile(r"^\s*(abierto|cerrado|abre|cierra)\b.*·", re.I)
CAMPOS_BOOL = {
    field.name for field in Places._meta.get_fields() if isinstance(field, BooleanField) and field.null
}


def atributos(amenities) -> dict:
    """Solo claves que existen en Places con valor booleano."""
    if not isinstance(amenities, dict):
        return {}
    return {k: v for k, v in amenities.items() if k in CAMPOS_BOOL and isinstance(v, bool)}


class Command(BaseCommand):
    help = "Copia atributos de Maps a Places y limpia horarios de un instante."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        conteo = Counter()

        detalles = dict(
            GooglePlaceDetails.objects.filter(fetch_status="ok", amenities__isnull=False)
            .exclude(amenities={})
            .values_list("place_id", "amenities")
        )
        lugares = Places.objects.filter(place_id__in=list(detalles)).only("id", "place_id", *CAMPOS_BOOL)
        with transaction.atomic():
            for lugar in lugares.iterator(chunk_size=500):
                cambios = {
                    campo: valor
                    for campo, valor in atributos(detalles[lugar.place_id]).items()
                    if getattr(lugar, campo) is None
                }
                if not cambios:
                    continue
                conteo["fichas_con_atributos"] += 1
                conteo.update(cambios.keys())
                if not dry:
                    Places.objects.filter(pk=lugar.pk).update(**cambios)

            instantaneos = [
                pk for pk, texto in Places.objects.exclude(horario_texto__isnull=True).values_list("pk", "horario_texto")
                if HORARIO_INSTANTANEO.match(texto or "") and "\n" not in texto
            ]
            conteo["horarios_borrados"] = len(instantaneos)
            if instantaneos and not dry:
                Places.objects.filter(pk__in=instantaneos).update(horario_texto=None, abierto_ahora=None)

        for clave, n in conteo.most_common():
            self.stdout.write(f"{clave}: {n}")
        if dry:
            self.stdout.write(self.style.WARNING("dry-run: no se guardó nada"))
