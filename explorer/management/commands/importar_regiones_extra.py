"""Añade a RegionOSM los municipios y corregimientos que faltaban y asigna sus lugares.

No borra nada (a diferencia de importar_poligonos_especificos). Idempotente.

  python manage.py importar_regiones_extra --dry-run
  python manage.py importar_regiones_extra
"""

from __future__ import annotations

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from explorer.models import Places, RegionOSM

# osm_id de planet_osm_polygon → ciudad
REGIONES_EXTRA = {
    -1307262: "Bello",
    -1350575: "El Retiro",
    -1343285: "Marinilla",
    -3947502: "El Carmen de Viboral",
    -3541287: "Medellín",  # Santa Elena
    -3541286: "Medellín",  # San Antonio de Prado
    -3541285: "Medellín",  # San Cristóbal
    -3541283: "Medellín",  # Altavista
}


class Command(BaseCommand):
    help = "Importa municipios y corregimientos extra a RegionOSM y asigna lugares sin zona."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT osm_id, name, admin_level, way_area, ST_AsText(ST_Transform(way, 4326))
                FROM planet_osm_polygon WHERE osm_id = ANY(%s)
                """,
                [list(REGIONES_EXTRA)],
            )
            filas = cursor.fetchall()

        with transaction.atomic():
            for osm_id, name, admin_level, way_area, wkt in filas:
                geom = GEOSGeometry(wkt, srid=4326)
                if isinstance(geom, MultiPolygon):
                    geom = max(geom, key=lambda poly: poly.area)
                existe = RegionOSM.objects.filter(osm_id=osm_id).exists()
                self.stdout.write(f"{'ya está' if existe else 'nueva'}: {name} ({osm_id}, nivel {admin_level})")
                if existe or dry:
                    continue
                region = RegionOSM(
                    osm_id=osm_id,
                    name=name,
                    admin_level=admin_level,
                    way_area=way_area,
                    geom_4326=geom,
                    geom_3857=geom.transform(3857, clone=True),
                    ciudad=REGIONES_EXTRA[osm_id],
                )
                region.save()

            asignados = 0
            sin_zona = Places.objects.filter(ubicacion__isnull=False, comuna_osm_id__isnull=True).only("id", "ubicacion")
            for lugar in sin_zona.iterator(chunk_size=1000):
                region = RegionOSM.objects.filter(geom_4326__contains=lugar.ubicacion).only("osm_id").first()
                if region is None:
                    continue
                asignados += 1
                if not dry:
                    Places.objects.filter(pk=lugar.pk).update(comuna_osm_id=region.osm_id)
            self.stdout.write(self.style.SUCCESS(f"lugares asignados a una zona: {asignados}"))
            if dry:
                self.stdout.write(self.style.WARNING("dry-run: no se guardó nada"))
