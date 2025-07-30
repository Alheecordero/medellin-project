import json
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.db import transaction
from explorer.models import Initialgrid, RegionOSM
from django.contrib.gis.db.models.aggregates import Union
from django.core.exceptions import ObjectDoesNotExist

class Command(BaseCommand):
    help = 'Puebla el modelo Initialgrid desde un archivo GeoJSON, filtrando los puntos que están dentro de los polígonos de RegionOSM.'

    def add_arguments(self, parser):
        parser.add_argument('geojson_file', type=str, help='La ruta al archivo GeoJSON.')

    @transaction.atomic
    def handle(self, *args, **options):
        geojson_file_path = options['geojson_file']

        self.stdout.write("Eliminando datos existentes de Initialgrid...")
        Initialgrid.objects.all().delete()

        self.stdout.write("Obteniendo y uniendo todos los polígonos de RegionOSM...")
        
        try:
            # Asumimos que queremos filtrar por una ciudad específica, por ejemplo, Medellín.
            # Si no se necesita filtrar por ciudad, se puede quitar el filtro `ciudad='Medellín'`.
            regions = RegionOSM.objects.filter(geom_4326__isnull=False)
            if not regions.exists():
                self.stderr.write(self.style.ERROR("No se encontraron objetos RegionOSM con geometría."))
                return

            # Unificar todos los polígonos en una sola geometría para mayor eficiencia
            unified_polygon = regions.aggregate(union=Union('geom_4326'))['union']

            if not unified_polygon:
                self.stderr.write(self.style.ERROR("No se pudieron unificar los polígonos de RegionOSM."))
                return

        except ObjectDoesNotExist:
            self.stderr.write(self.style.ERROR("No se encontraron regiones OSM."))
            return

        self.stdout.write("Leyendo el archivo GeoJSON...")
        try:
            with open(geojson_file_path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"Archivo no encontrado: {geojson_file_path}"))
            return
        except json.JSONDecodeError:
            self.stderr.write(self.style.ERROR(f"Error al decodificar JSON del archivo: {geojson_file_path}"))
            return

        features = data.get('features', [])
        if not features:
            self.stderr.write(self.style.WARNING("No se encontraron 'features' en el archivo GeoJSON."))
            return

        points_to_create = []
        self.stdout.write("Procesando puntos desde GeoJSON...")
        for feature in features:
            if feature.get('geometry') and feature['geometry']['type'] == 'Point':
                coords = feature['geometry']['coordinates']
                # GeoJSON especifica coordenadas como [longitud, latitud]
                point = Point(coords[0], coords[1], srid=4326)

                if unified_polygon.covers(point):
                    points_to_create.append(Initialgrid(points=point))
        
        if points_to_create:
            self.stdout.write(f"Se encontraron {len(points_to_create)} puntos dentro de las regiones. Creando en lote...")
            Initialgrid.objects.bulk_create(points_to_create)
            self.stdout.write(self.style.SUCCESS('Se ha poblado el modelo Initialgrid con éxito.'))
        else:
            self.stdout.write(self.style.WARNING("Ningún punto del archivo GeoJSON se encontraba dentro de los polígonos de RegionOSM.")) 