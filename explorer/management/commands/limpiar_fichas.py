"""Limpieza de fichas: cerrados, duplicados, coordenadas fuera del valle y fichas viejas.

- Cerrados: marca `cerrado_permanente` con lo que dice Maps (y lo quita si reabrió).
- Duplicados: mismo nombre a menos de 40 m y mismas reseñas o mismo teléfono. Se queda la
  ficha con más peso (guía, indexable, carta, reseñas); las otras apuntan a ella con
  `fusionado_en` (su URL redirige con 301) y le pasan su guía y su carta si no las tiene.
- Coordenadas: fichas fuera del valle toman el punto de su ficha de Maps si cae dentro.
- Viejas: las publicadas sin ficha de Maps entran en la cola del scraper (GooglePlaceId).

No borra nada. Idempotente.

  python manage.py limpiar_fichas --dry-run    # no escribe nada
  python manage.py limpiar_fichas
  python manage.py limpiar_fichas --solo duplicados --dry-run
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from django.contrib.gis.geos import Polygon
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from explorer.models import CuratedGuideItem, GooglePlaceDetails, GooglePlaceId, PlacePartnerMenu, Places

VALLE = Polygon.from_bbox((-75.75, 5.95, -75.0, 6.55))
VALLE.srid = 4326
DISTANCIA_MAX_M = 40
METROS_POR_GRADO = 111_000
PARTES = ("cerrados", "duplicados", "coordenadas", "viejas")


def _norm(texto: str | None) -> str:
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _telefono(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")[-7:]


def _mismo_negocio(a: Places, b: Places) -> bool:
    if a.ubicacion.distance(b.ubicacion) * METROS_POR_GRADO >= DISTANCIA_MAX_M:
        return False
    ra, rb = a.total_reviews or 0, b.total_reviews or 0
    resenas = max(ra, rb) > 0 and abs(ra - rb) <= max(3, 0.02 * max(ra, rb))
    telefono = bool(_telefono(a.telefono)) and _telefono(a.telefono) == _telefono(b.telefono)
    return resenas or telefono


class Command(BaseCommand):
    help = "Marca cerrados, fusiona duplicados, corrige coordenadas y encola fichas viejas."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--solo", choices=PARTES, help="Correr solo una parte")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        partes = [options["solo"]] if options["solo"] else PARTES
        self.dry = dry
        with transaction.atomic():
            for parte in partes:
                self.stdout.write(self.style.MIGRATE_HEADING(f"== {parte}"))
                getattr(self, f"_{parte}")()
        if dry:
            self.stdout.write(self.style.WARNING("dry-run: no se guardó nada"))

    def _guardar(self, qs, **valores):
        """update() salvo en dry-run, que no escribe nada."""
        if not self.dry:
            qs.update(**valores)

    def _cerrados(self):
        cerrados = set(
            GooglePlaceDetails.objects.filter(
                Q(category__istartswith="Cerrado permanentemente") | Q(business_status="CLOSED_PERMANENTLY")
            ).values_list("place_id", flat=True)
        )
        base = Places._base_manager
        nuevos = base.filter(place_id__in=cerrados, cerrado_permanente=False)
        reabiertos = base.filter(cerrado_permanente=True).exclude(place_id__in=cerrados)
        en_guia = nuevos.filter(en_guias__guia__publicado=True).values_list("slug", "en_guias__guia__slug")
        self.stdout.write(f"cerrados nuevos: {nuevos.count()} | reabiertos: {reabiertos.count()}")
        for slug, guia in en_guia:
            self.stdout.write(f"  en la guía {guia}: {slug} (deja de mostrarse en la guía)")
        self._guardar(reabiertos, cerrado_permanente=False)
        self._guardar(nuevos, cerrado_permanente=True)

    def _duplicados(self):
        vivos = list(
            Places.objects.filter(tiene_fotos=True, ubicacion__isnull=False)
            .prefetch_related(None)
            .only("id", "slug", "nombre", "place_id", "ubicacion", "total_reviews", "telefono", "es_destacado")
        )
        por_nombre = defaultdict(list)
        for lugar in vivos:
            if _norm(lugar.nombre):
                por_nombre[_norm(lugar.nombre)].append(lugar)

        padre = {}

        def raiz(i):
            while padre.get(i, i) != i:
                i = padre[i]
            return i

        for grupo in por_nombre.values():
            for i, a in enumerate(grupo):
                for b in grupo[i + 1:]:
                    if _mismo_negocio(a, b):
                        padre[raiz(b.pk)] = raiz(a.pk)
        grupos = defaultdict(list)
        por_id = {lugar.pk: lugar for lugar in vivos}
        for pk in list(padre):
            grupos[raiz(pk)].append(por_id[pk])
        for r in list(grupos):
            if por_id[r] not in grupos[r]:
                grupos[r].append(por_id[r])

        ids = [l.pk for g in grupos.values() for l in g]
        indexables = set(Places.objects.indexables().filter(pk__in=ids).values_list("id", flat=True))
        con_carta = set(PlacePartnerMenu.objects.filter(lugar_id__in=ids).values_list("lugar_id", flat=True))
        en_guia = set(CuratedGuideItem.objects.filter(lugar_id__in=ids).values_list("lugar_id", flat=True))
        con_maps = set(
            GooglePlaceDetails.objects.filter(place_id__in=[l.place_id for g in grupos.values() for l in g], fetch_status="ok")
            .values_list("place_id", flat=True)
        )

        def peso(l):
            return (
                8 * (l.pk in en_guia) + 4 * (l.pk in indexables) + 2 * (l.pk in con_carta) + (l.place_id in con_maps),
                l.total_reviews or 0,
                not re.search(r"-\d+$", l.slug or ""),
                -l.pk,
            )

        fusionados = 0
        for grupo in grupos.values():
            grupo.sort(key=peso, reverse=True)
            queda, sobran = grupo[0], grupo[1:]
            self.stdout.write(f"{queda.slug} ← {', '.join(l.slug for l in sobran)}")
            for viejo in sobran:
                self._pasar_guias(viejo, queda)
                if viejo.pk in con_carta and queda.pk not in con_carta:
                    self._guardar(PlacePartnerMenu.objects.filter(lugar_id=viejo.pk), lugar_id=queda.pk)
                    con_carta.add(queda.pk)
                    self.stdout.write(f"  carta: {viejo.slug} → {queda.slug}")
                if viejo.es_destacado and not queda.es_destacado:
                    self._guardar(Places._base_manager.filter(pk=queda.pk), es_destacado=True)
                self._guardar(Places._base_manager.filter(pk=viejo.pk), fusionado_en=queda)
                fusionados += 1
        self.stdout.write(f"grupos: {len(grupos)} | fichas fusionadas: {fusionados}")

    def _pasar_guias(self, viejo, queda):
        for item in CuratedGuideItem.objects.filter(lugar_id=viejo.pk).select_related("guia"):
            if CuratedGuideItem.objects.filter(guia=item.guia, lugar_id=queda.pk).exists():
                self.stdout.write(f"  guía {item.guia.slug}: ya tiene {queda.slug}, {viejo.slug} deja de mostrarse")
                continue
            self._guardar(CuratedGuideItem.objects.filter(pk=item.pk), lugar_id=queda.pk)
            self.stdout.write(f"  guía {item.guia.slug}: {viejo.slug} → {queda.slug}")

    def _coordenadas(self):
        fuera = Places.objects.filter(tiene_fotos=True, ubicacion__isnull=False).exclude(ubicacion__within=VALLE)
        maps = dict(
            GooglePlaceDetails.objects.filter(
                place_id__in=fuera.values("place_id"), fetch_status="ok", ubicacion__within=VALLE
            ).values_list("place_id", "ubicacion")
        )
        for lugar in fuera.prefetch_related(None).only("id", "slug", "place_id", "ubicacion"):
            punto = maps.get(lugar.place_id)
            if punto is None:
                self.stdout.write(f"{lugar.slug}: fuera del valle ({lugar.ubicacion.y:.4f}, {lugar.ubicacion.x:.4f}) y sin punto en Maps")
                continue
            self._guardar(Places._base_manager.filter(pk=lugar.pk), ubicacion=punto)
            self.stdout.write(f"{lugar.slug}: ({lugar.ubicacion.y:.4f}, {lugar.ubicacion.x:.4f}) → ({punto.y:.4f}, {punto.x:.4f})")

    def _viejas(self):
        con_maps = GooglePlaceDetails.objects.filter(fetch_status="ok").values("place_id")
        viejas = list(
            Places.objects.filter(tiene_fotos=True).exclude(place_id__in=con_maps).values_list("place_id", flat=True)
        )
        en_cola = set(GooglePlaceId.objects.filter(place_id__in=viejas).values_list("place_id", flat=True))
        nuevas = [pid for pid in viejas if pid not in en_cola]
        if not self.dry:
            GooglePlaceId.objects.bulk_create(
                [GooglePlaceId(place_id=pid, source="places_import", scan_types=["refresco_fichas"]) for pid in nuevas],
                ignore_conflicts=True,
            )
        self.stdout.write(
            f"publicadas sin ficha de Maps: {len(viejas)} | ya en la cola del scraper: {len(en_cola)} | encoladas ahora: {len(nuevas)}"
        )
