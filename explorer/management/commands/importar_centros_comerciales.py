"""Crea o actualiza los centros comerciales desde OSM y asigna a cada lugar el suyo.

Lee los polígonos `shop=mall` del valle en planet_osm_polygon, une las etapas de un mismo
centro (Mayorca I y II), limpia el nombre y cuenta los lugares con foto que caen dentro.
Solo guarda los que llegan a CC_MIN_LUGARES; los que bajan de ahí quedan sin publicar.
No borra nada. Idempotente: se puede volver a correr cuando entren lugares nuevos.

  python manage.py importar_centros_comerciales --dry-run
  python manage.py importar_centros_comerciales
"""

from __future__ import annotations

import re
from collections import defaultdict

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils.text import slugify

from explorer.models import CC_MIN_LUGARES, CentroComercial, Places, RegionOSM

# Valle de Aburrá y oriente cercano, como en publicar_pendientes_enriquecidos.
VALLE = (-75.75, 5.95, -75.0, 6.55)
# Nombres de OSM que no basta con limpiar.
NOMBRES = {
    "Unicentro Medelllín": "Unicentro",
    "Centro Comercial ARKADIA": "Arkadia",
    "Centro Comercial Aves Maria": "Aves María",
    "Centro Comercial del Este": "Del Este",
    "Centro comercial Megacentro": "Megacentro",
}
# "Centro Comercial Outlet Mayorca Etapa I" → "Mayorca"; "El Tesoro Parque Comercial" → "El Tesoro".
# "Mall Sao Paulo" o "De Moda Outlet" se llaman así y no se tocan.
SUFIJO = re.compile(r"\s+(centro comercial|parque comercial|etapa\s+[ivx\d]+)$", re.I)
PREFIJO = re.compile(r"^(centro comercial\s+)(outlet\s+)?", re.I)


def nombre_limpio(nombre_osm: str) -> str:
    if nombre_osm in NOMBRES:
        return NOMBRES[nombre_osm]
    nombre = nombre_osm.strip()
    while SUFIJO.search(nombre):
        nombre = SUFIJO.sub("", nombre)
    nombre = PREFIJO.sub("", nombre)
    return nombre.strip() or nombre_osm


def _multi(geom: GEOSGeometry) -> MultiPolygon:
    if isinstance(geom, Polygon):
        geom = MultiPolygon(geom, srid=4326)
    geom.srid = 4326
    return geom


class Command(BaseCommand):
    help = "Importa centros comerciales de OSM y asigna sus lugares."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH m AS (
                    SELECT osm_id, name, ST_Transform(way, 4326) AS g FROM planet_osm_polygon
                    WHERE shop = 'mall' AND name IS NOT NULL
                      AND ST_Intersects(ST_Transform(way, 4326), ST_MakeEnvelope(%s, %s, %s, %s, 4326))
                )
                SELECT m.osm_id, m.name, ST_AsText(m.g), array_agg(pl.id)
                FROM m JOIN explorer_places pl
                  ON pl.tiene_fotos AND ST_Contains(m.g, pl.ubicacion::geometry)
                GROUP BY m.osm_id, m.name, m.g
                """,
                list(VALLE),
            )
            filas = cursor.fetchall()

        grupos = defaultdict(lambda: {"osm_ids": [], "geoms": [], "lugares": set(), "nombres": set()})
        for osm_id, nombre_osm, wkt, ids in filas:
            grupo = grupos[nombre_limpio(nombre_osm)]
            grupo["osm_ids"].append(osm_id)
            grupo["geoms"].append(GEOSGeometry(wkt, srid=4326))
            grupo["lugares"].update(ids)
            grupo["nombres"].add(nombre_osm)

        indexables = set(Places.objects.indexables().values_list("id", flat=True))
        validos = {n: g for n, g in grupos.items() if len(g["lugares"]) >= CC_MIN_LUGARES}
        # Un lugar en dos polígonos que se solapan se queda con el centro más grande.
        orden = sorted(validos.items(), key=lambda kv: -len(kv[1]["lugares"]))
        asignado = {}
        for nombre, grupo in orden:
            for lugar_id in grupo["lugares"]:
                asignado.setdefault(lugar_id, nombre)

        with transaction.atomic():
            vistos = []
            for nombre, grupo in orden:
                geom = grupo["geoms"][0]
                for otra in grupo["geoms"][1:]:
                    geom = geom.union(otra)
                geom = _multi(geom)
                ids = [i for i in grupo["lugares"] if asignado[i] == nombre]
                n_idx = len(indexables.intersection(ids))
                zona = (
                    RegionOSM.objects.filter(geom_4326__contains=geom.point_on_surface)
                    .order_by("way_area").first()
                )
                portada = self._portada(ids)
                self.stdout.write(
                    f"{nombre:28} {len(ids):3} lugares, {n_idx:3} indexables, "
                    f"{zona.name if zona else '-':18} ← {', '.join(sorted(grupo['nombres']))}"
                )
                if dry:
                    continue
                centro = (
                    CentroComercial.objects.filter(osm_ids__overlap=grupo["osm_ids"]).first()
                    or CentroComercial(slug=self._slug_libre(nombre))
                )
                centro.nombre = nombre
                centro.osm_ids = sorted(grupo["osm_ids"])
                centro.geom = geom
                centro.zona = zona
                centro.portada = portada
                centro.total_lugares = len(ids)
                centro.lugares_indexables = n_idx
                centro.save()
                vistos.append(centro.pk)
                Places.objects.filter(pk__in=ids).exclude(centro_comercial=centro).update(centro_comercial=centro)
                Places.objects.filter(centro_comercial=centro).exclude(pk__in=ids).update(centro_comercial=None)

            if not dry:
                fuera = CentroComercial.objects.exclude(pk__in=vistos)
                Places.objects.filter(centro_comercial__in=fuera).update(centro_comercial=None)
                fuera.update(total_lugares=0, lugares_indexables=0)

        self.stdout.write(self.style.SUCCESS(
            f"{len(orden)} centros con {CC_MIN_LUGARES}+ lugares; {len(asignado)} lugares asignados"
        ))
        if dry:
            self.stdout.write(self.style.WARNING("dry-run: no se guardó nada"))

    def _portada(self, ids) -> str:
        """Foto mediana del lugar mejor valorado del centro."""
        lugar = (
            Places.objects.filter(pk__in=ids, fotos__isnull=False)
            .only("id").order_by("-weighted_rating", "-total_reviews").first()
        )
        if lugar is None:
            return ""
        foto = min(lugar.fotos.all(), key=lambda f: f.pk)
        return (foto.imagen_mediana or foto.imagen or "")[:1000]

    def _slug_libre(self, nombre: str) -> str:
        base = slugify(nombre)[:130] or "centro-comercial"
        slug, n = base, 2
        while CentroComercial.objects.filter(slug=slug).exists():
            slug, n = f"{base}-{n}", n + 1
        return slug
