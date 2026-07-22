"""
Genera grilla de cobertura total para barrido de Google Place IDs.

Cubre Medellín, Envigado, Valle de Aburrá, Rionegro, Guatapé y zonas turísticas.
No borra puntos existentes; evita duplicados por coordenada redondeada.

Uso:
  python manage.py generar_grilla_cobertura --dry-run
  python manage.py generar_grilla_cobertura --preset valle
  python manage.py generar_grilla_cobertura --preset all
  python manage.py generar_grilla_cobertura --solo Guatapé
"""
import math

from django.core.management.base import BaseCommand, CommandError

from explorer.utils.text_scan_progress import create_grid_points_bulk, has_db_text_scan_field, initialgrid_qs, load_progress_ids
from explorer.utils.vive_areas import SCAN_AREAS, VIVE_SEARCH_TYPES, resolve_area_names


class Command(BaseCommand):
    help = "Grilla de cobertura total para catálogo GooglePlaceId (scan gratis)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--preset",
            type=str,
            default="all",
            help="core | valle | turismo | all (default: all)",
        )
        parser.add_argument(
            "--solo",
            type=str,
            default="",
            help="Solo un área (ej: 'Rionegro', 'Guatapé'). Ver SCAN_AREAS.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        try:
            area_names = resolve_area_names(solo=options["solo"].strip(), preset=options["preset"].strip())
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        areas = {name: SCAN_AREAS[name] for name in area_names}

        existing = set()
        for p in initialgrid_qs().values_list("points", flat=True):
            existing.add((round(p.y, 5), round(p.x, 5)))

        self.stdout.write(f"📦 {len(existing):,} puntos ya en grilla")
        self.stdout.write(f"🗺️  Preset/áreas: {', '.join(area_names)}")

        cos_lat = math.cos(math.radians(6.24))
        total_nuevos = 0
        por_area = {}
        nuevos_coords: list[tuple[float, float]] = []

        for area_name, bounds in areas.items():
            sep_km = bounds.get("separacion_km", 0.7)
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
                            nuevos_coords.append((lng, lat))
                        count += 1
                    lng += lng_step
                lat += lat_step

            por_area[area_name] = (count, sep_km)
            total_nuevos += count

        if not dry_run and nuevos_coords:
            create_grid_points_bulk(nuevos_coords)

        tipos = len(VIVE_SEARCH_TYPES)
        llamadas = total_nuevos * tipos

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(self.style.SUCCESS("📊 GRILLA COBERTURA TOTAL"))
        for name, (count, sep) in por_area.items():
            self.stdout.write(f"   📍 {name}: +{count:,} puntos ({sep} km)")
        self.stdout.write(self.style.SUCCESS(f"\n   🆕 Total nuevos: {total_nuevos:,}"))
        self.stdout.write(f"   📡 Llamadas Text Search est.: ~{llamadas:,}  (~$0 USD)")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n   ⚠️  DRY RUN — nada creado"))
        else:
            if has_db_text_scan_field():
                pendientes = initialgrid_qs().filter(is_text_scan_processed=False).count()
            else:
                pendientes = initialgrid_qs().exclude(id__in=load_progress_ids()).count()
            self.stdout.write(f"\n   ⏳ Puntos pendientes text scan: {pendientes:,}")
            self.stdout.write("   → python manage.py scan_place_ids_gratis --preset all --dry-run")
            self.stdout.write("   → python manage.py scan_place_ids_gratis --preset all\n")
