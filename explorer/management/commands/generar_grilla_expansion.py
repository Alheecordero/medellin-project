"""
Genera puntos de grilla ADICIONALES en áreas no cubiertas por la grilla principal.
No toca los puntos existentes — solo agrega nuevos.

Uso:
  python manage.py generar_grilla_expansion --dry-run    # Solo muestra cuántos
  python manage.py generar_grilla_expansion               # Genera los puntos
"""
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from explorer.models import Initialgrid
import math


# Áreas que NO cubría la grilla anterior
AREAS_EXPANSION = {
    # ═══════════════════════════════════════════════════════════
    # NORTE DEL VALLE DE ABURRÁ
    # ═══════════════════════════════════════════════════════════

    "Bello Norte / Copacabana": {
        "lat_min": 6.325,
        "lat_max": 6.400,
        "lng_min": -75.590,
        "lng_max": -75.540,
        "separacion_km": 2.0,
    },

    # ═══════════════════════════════════════════════════════════
    # SUR DEL VALLE DE ABURRÁ
    # ═══════════════════════════════════════════════════════════

    "Caldas": {
        "lat_min": 6.080,
        "lat_max": 6.145,
        "lng_min": -75.650,
        "lng_max": -75.600,
        "separacion_km": 2.0,
    },

    "Sabaneta Denso": {
        "lat_min": 6.145,
        "lat_max": 6.165,
        "lng_min": -75.625,
        "lng_max": -75.600,
        "separacion_km": 1.0,
    },

    "La Estrella Centro": {
        "lat_min": 6.140,
        "lat_max": 6.165,
        "lng_min": -75.650,
        "lng_max": -75.625,
        "separacion_km": 1.5,
    },

    # ═══════════════════════════════════════════════════════════
    # CORREDOR MEDELLÍN → RIONEGRO (Las Palmas, Santa Elena)
    # Muchos restaurantes campestres y miradores
    # ═══════════════════════════════════════════════════════════

    "Las Palmas / Santa Elena": {
        "lat_min": 6.175,
        "lat_max": 6.240,
        "lng_min": -75.535,
        "lng_max": -75.425,
        "separacion_km": 2.0,
    },

    # ═══════════════════════════════════════════════════════════
    # ORIENTE ANTIOQUEÑO (alrededor de Rionegro)
    # ═══════════════════════════════════════════════════════════

    "El Retiro": {
        "lat_min": 6.040,
        "lat_max": 6.080,
        "lng_min": -75.520,
        "lng_max": -75.470,
        "separacion_km": 2.0,
    },

    "La Ceja": {
        "lat_min": 5.950,
        "lat_max": 5.990,
        "lng_min": -75.450,
        "lng_max": -75.410,
        "separacion_km": 2.0,
    },

    "Marinilla": {
        "lat_min": 6.160,
        "lat_max": 6.195,
        "lng_min": -75.360,
        "lng_max": -75.320,
        "separacion_km": 2.0,
    },

    "El Peñol (zona embalse)": {
        "lat_min": 6.195,
        "lat_max": 6.240,
        "lng_min": -75.260,
        "lng_max": -75.190,
        "separacion_km": 2.0,
    },

    # ═══════════════════════════════════════════════════════════
    # OCCIDENTE TURÍSTICO
    # ═══════════════════════════════════════════════════════════

    "Santa Fe de Antioquia": {
        "lat_min": 6.545,
        "lat_max": 6.575,
        "lng_min": -75.840,
        "lng_max": -75.810,
        "separacion_km": 1.5,
    },

    "San Jerónimo": {
        "lat_min": 6.430,
        "lat_max": 6.460,
        "lng_min": -75.750,
        "lng_max": -75.720,
        "separacion_km": 2.0,
    },
}


class Command(BaseCommand):
    help = 'Genera puntos adicionales en áreas no cubiertas.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        cos_lat = math.cos(math.radians(6.20))

        # Cargar puntos existentes para no duplicar
        existing = set()
        for p in Initialgrid.objects.all().values_list('points', flat=True):
            existing.add((round(p.y, 5), round(p.x, 5)))
        self.stdout.write(f"📦 {len(existing)} puntos ya existen en la grilla")

        total_nuevos = 0
        resumen = {}

        for area_name, bounds in AREAS_EXPANSION.items():
            sep_km = bounds["separacion_km"]
            lat_step = sep_km / 111.32
            lng_step = sep_km / (111.32 * cos_lat)

            count = 0
            lat = bounds["lat_min"]
            while lat <= bounds["lat_max"]:
                lng = bounds["lng_min"]
                while lng <= bounds["lng_max"]:
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

            resumen[area_name] = (count, sep_km)
            total_nuevos += count

        # Resumen
        self.stdout.write(f"\n{'═'*60}")
        self.stdout.write(self.style.SUCCESS(f"📊 EXPANSIÓN DE GRILLA"))
        self.stdout.write(f"")
        for area_name, (count, sep) in resumen.items():
            if count > 0:
                self.stdout.write(f"   📍 {area_name}: {count} puntos ({sep}km)")
        self.stdout.write(f"")
        self.stdout.write(self.style.SUCCESS(f"   🆕 NUEVOS PUNTOS: {total_nuevos}"))
        self.stdout.write(f"   💰 Costo estimado scan: ~${total_nuevos * 0.032:.2f} USD")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n   ⚠️  DRY RUN — nada fue creado"))
        else:
            pendientes = Initialgrid.objects.filter(is_processed=False).count()
            self.stdout.write(f"\n   📋 Pendientes de scan: {pendientes}")
            self.stdout.write(f"   → python manage.py scan_nuevos_lugares")
