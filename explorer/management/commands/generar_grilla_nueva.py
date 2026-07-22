"""
Genera una nueva grilla de puntos para barrer Medellín y alrededores.
Cubre: 16 comunas de Medellín + Envigado, Sabaneta, Itagüí, La Estrella, Rionegro, Guatapé.

Uso:
  python manage.py generar_grilla_nueva                # Genera con separación 2km (default)
  python manage.py generar_grilla_nueva --separacion 1.5  # Separación personalizada en km
  python manage.py generar_grilla_nueva --dry-run      # Solo muestra cuántos puntos generaría
  python manage.py generar_grilla_nueva --clear         # Limpia grilla anterior antes de generar
"""
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from explorer.models import Initialgrid
import math


# ════════════════════════════════════════════════════════════════════
# ÁREAS A CUBRIR — bounding boxes (lat_min, lat_max, lng_min, lng_max)
#
# Cada área se define con un rectángulo que cubre la zona.
# La grilla genera puntos uniformes dentro de cada rectángulo.
# ════════════════════════════════════════════════════════════════════

AREAS = {
    # ═══════════════════════════════════════════════════════════
    # ZONAS DENSAS — 1km de separación (más puntos, más cobertura)
    # La Candelaria, El Poblado, Laureles tienen 1,800-2,000 lugares
    # ═══════════════════════════════════════════════════════════

    # El Poblado + La Candelaria + Buenos Aires (centro-sur denso)
    "Centro-Sur Denso (Poblado/Candelaria)": {
        "lat_min": 6.190,
        "lat_max": 6.260,
        "lng_min": -75.600,
        "lng_max": -75.550,
        "separacion_km": 1.0,
    },

    # Laureles-Estadio + La América + Belén (centro-oeste denso)
    "Centro-Oeste Denso (Laureles/Belén)": {
        "lat_min": 6.230,
        "lat_max": 6.270,
        "lng_min": -75.610,
        "lng_max": -75.570,
        "separacion_km": 1.0,
    },

    # Envigado centro (muy denso)
    "Envigado Centro": {
        "lat_min": 6.155,
        "lat_max": 6.190,
        "lng_min": -75.600,
        "lng_max": -75.565,
        "separacion_km": 1.0,
    },

    # ═══════════════════════════════════════════════════════════
    # RESTO DEL VALLE DE ABURRÁ — 2km de separación
    # Cubre: comunas norte, Itagüí, Sabaneta, La Estrella, Bello
    # ═══════════════════════════════════════════════════════════
    "Valle de Aburrá (resto)": {
        "lat_min": 6.145,
        "lat_max": 6.340,
        "lng_min": -75.645,
        "lng_max": -75.530,
        "separacion_km": 2.0,
    },

    # Itagüí centro (moderadamente denso)
    "Itagüí": {
        "lat_min": 6.155,
        "lat_max": 6.190,
        "lng_min": -75.630,
        "lng_max": -75.600,
        "separacion_km": 1.5,
    },

    # ═══════════════════════════════════════════════════════════
    # ORIENTE — 2km de separación
    # ═══════════════════════════════════════════════════════════

    # Rionegro (aeropuerto + zona urbana + zona rosa)
    "Rionegro": {
        "lat_min": 6.120,
        "lat_max": 6.180,
        "lng_min": -75.420,
        "lng_max": -75.350,
        "separacion_km": 2.0,
    },

    # Guatapé (pueblo + embalse + Piedra del Peñol)
    "Guatapé": {
        "lat_min": 6.210,
        "lat_max": 6.275,
        "lng_min": -75.190,
        "lng_max": -75.130,
        "separacion_km": 2.0,
    },
}


class Command(BaseCommand):
    help = 'Genera grilla de puntos para barrer nuevas zonas.'

    def add_arguments(self, parser):
        parser.add_argument('--separacion', type=float, default=2.0,
                            help='Separación entre puntos en km (default: 2.0)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Solo muestra cuántos puntos generaría')
        parser.add_argument('--clear', action='store_true',
                            help='Elimina TODOS los puntos de la grilla antes de generar')

    def handle(self, *args, **options):
        sep_km = options['separacion']
        dry_run = options['dry_run']

        if options['clear']:
            deleted = Initialgrid.objects.all().delete()[0]
            self.stdout.write(self.style.WARNING(f"🗑️  {deleted} puntos eliminados de la grilla"))

        # 1 grado de latitud ≈ 111.32 km
        # 1 grado de longitud ≈ 111.32 * cos(lat) km (en Medellín ~6°N, cos(6°) ≈ 0.9945)
        cos_lat = math.cos(math.radians(6.25))  # Latitud media de Medellín

        total_puntos = 0
        puntos_por_area = {}
        all_points = set()  # Para evitar duplicados entre áreas que se solapan

        for area_name, bounds in AREAS.items():
            # Cada área puede tener su propia separación, o usa el default
            area_sep = bounds.get("separacion_km", sep_km)
            lat_step = area_sep / 111.32
            lng_step = area_sep / (111.32 * cos_lat)

            count = 0
            lat = bounds["lat_min"]
            while lat <= bounds["lat_max"]:
                lng = bounds["lng_min"]
                while lng <= bounds["lng_max"]:
                    # Redondear para detectar duplicados entre áreas solapadas
                    key = (round(lat, 5), round(lng, 5))
                    if key not in all_points:
                        all_points.add(key)
                        if not dry_run:
                            Initialgrid.objects.create(
                                points=Point(lng, lat, srid=4326),
                                is_processed=False,
                            )
                        count += 1
                    lng += lng_step
                lat += lat_step

            puntos_por_area[area_name] = (count, area_sep)
            total_puntos += count

        # Resumen
        self.stdout.write(f"\n{'═'*60}")
        self.stdout.write(self.style.SUCCESS(f"📊 GRILLA GENERADA — Separación: {sep_km}km"))
        self.stdout.write(f"")
        for area_name, (count, area_sep) in puntos_por_area.items():
            self.stdout.write(f"   📍 {area_name}: {count} puntos ({area_sep}km)")
        self.stdout.write(f"")
        self.stdout.write(self.style.SUCCESS(f"   🔢 TOTAL: {total_puntos} puntos"))
        self.stdout.write(f"   💰 Costo estimado scan: ~${total_puntos * 0.032:.2f} USD")
        self.stdout.write(f"   📏 Lat step: {lat_step:.6f}° | Lng step: {lng_step:.6f}°")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n   ⚠️  DRY RUN — nada fue creado"))
        else:
            total_en_db = Initialgrid.objects.count()
            pendientes = Initialgrid.objects.filter(is_processed=False).count()
            self.stdout.write(f"\n   📋 Total en Initialgrid: {total_en_db}")
            self.stdout.write(f"   ⏳ Pendientes de scan: {pendientes}")
            self.stdout.write(f"\n   → Siguiente paso: python manage.py scan_nuevos_lugares")
