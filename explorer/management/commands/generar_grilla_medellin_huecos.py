"""
Genera puntos de grilla ADICIONALES solo dentro de Medellín (16 comunas)
para rellenar huecos que dejó la grilla principal (2km en "Valle de Aburrá resto").
No toca puntos existentes; no incluye Envigado, Bello, Itagüí ni otros municipios.

Uso:
  python manage.py generar_grilla_medellin_huecos --dry-run   # Solo muestra cuántos
  python manage.py generar_grilla_medellin_huecos             # Genera los puntos
  python manage.py generar_grilla_medellin_huecos --separacion 0.5   # Más denso
"""
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from explorer.models import Initialgrid
import math


# Bounding box aproximado de la ciudad de Medellín (16 comunas)
# Excluye Envigado (sur), Bello (norte), Itagüí (sur) — solo área urbana municipal
MEDELLIN_BBOX = {
    "lat_min": 6.195,
    "lat_max": 6.295,
    "lng_min": -75.620,
    "lng_max": -75.545,
    "separacion_km": 0.7,  # Más denso que la grilla principal para cubrir huecos
}


class Command(BaseCommand):
    help = 'Añade puntos solo dentro de Medellín para rellenar huecos (no otros municipios).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Solo muestra cuántos puntos se añadirían')
        parser.add_argument('--separacion', type=float, default=None,
                            help='Separación en km (default: 0.7). Ej: 0.5 para más denso')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        sep_km = options['separacion'] or MEDELLIN_BBOX["separacion_km"]

        cos_lat = math.cos(math.radians(6.24))
        lat_step = sep_km / 111.32
        lng_step = sep_km / (111.32 * cos_lat)

        # Cargar puntos existentes para no duplicar
        existing = set()
        for p in Initialgrid.objects.all().values_list('points', flat=True):
            existing.add((round(p.y, 5), round(p.x, 5)))
        self.stdout.write(f"📦 {len(existing)} puntos ya existen en la grilla")

        count = 0
        lat = MEDELLIN_BBOX["lat_min"]
        while lat <= MEDELLIN_BBOX["lat_max"]:
            lng = MEDELLIN_BBOX["lng_min"]
            while lng <= MEDELLIN_BBOX["lng_max"]:
                key = (round(lat, 5), round(lng, 5))
                if key not in existing:
                    existing.add(key)
                    if not dry_run:
                        Initialgrid.objects.create(
                            points=Point(lng, lat, srid=4326),
                            is_processed=False,
                        )
                    count += 1
                lng += lng_step
            lat += lat_step

        self.stdout.write(f"\n{'═'*60}")
        self.stdout.write(self.style.SUCCESS("📊 GRILLA HUECOS — Solo Medellín (16 comunas)"))
        self.stdout.write(f"   Bbox: lat {MEDELLIN_BBOX['lat_min']}–{MEDELLIN_BBOX['lat_max']}, "
                          f"lng {MEDELLIN_BBOX['lng_min']}–{MEDELLIN_BBOX['lng_max']}")
        self.stdout.write(f"   Separación: {sep_km} km")
        self.stdout.write(f"   🆕 Puntos nuevos: {count}")
        self.stdout.write(f"   💰 Costo estimado scan: ~${count * 0.032:.2f} USD")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n   ⚠️  DRY RUN — nada fue creado"))
        else:
            pendientes = Initialgrid.objects.filter(is_processed=False).count()
            self.stdout.write(f"\n   📋 Pendientes de scan: {pendientes}")
            self.stdout.write(f"   → python manage.py scan_nuevos_lugares")
