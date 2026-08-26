"""
Fase 3 del plan gratuito: subdividir puntos de grilla saturados.

Tres rondas con offsets distintos (más cobertura sin repetir las mismas coords):
  Ronda 1 — cardinal 250 m (N/S/E/O)   [ya aplicada en producción]
  Ronda 2 — diagonal 250 m (NE/NW/SE/SO)
  Ronda 3 — cardinal 400 m (N/S/E/O)

Uso:
  python manage.py generar_subgrilla_saturacion --dry-run
  python manage.py generar_subgrilla_saturacion --ronda 2 --dry-run
  python manage.py generar_subgrilla_saturacion --ronda 3
  python manage.py generar_subgrilla_saturacion --todas-rondas --dry-run
"""
import math

from django.core.management.base import BaseCommand, CommandError

from explorer.utils.text_scan_progress import create_grid_points_bulk, initialgrid_qs
from explorer.utils.vive_areas import SATURATION_IDS_THRESHOLD

RONDA_LABELS = {
    1: "cardinal 250 m (N/S/E/O)",
    2: "diagonal 250 m (NE/NW/SE/SO)",
    3: "cardinal 400 m (N/S/E/O)",
}


def offsets_for_ronda(ronda: int, offset_m: float) -> list[tuple[float, float]]:
    cos_lat = math.cos(math.radians(6.24))
    dlat = offset_m / 111_320
    dlng = offset_m / (111_320 * cos_lat)

    if ronda == 1:
        return [(dlat, 0), (-dlat, 0), (0, dlng), (0, -dlng)]

    if ronda == 2:
        d = offset_m / math.sqrt(2)
        dlat_d = d / 111_320
        dlng_d = d / (111_320 * cos_lat)
        return [
            (dlat_d, dlng_d),
            (dlat_d, -dlng_d),
            (-dlat_d, dlng_d),
            (-dlat_d, -dlng_d),
        ]

    if ronda == 3:
        dlat3 = offset_m / 111_320
        dlng3 = offset_m / (111_320 * cos_lat)
        return [(dlat3, 0), (-dlat3, 0), (0, dlng3), (0, -dlng3)]

    raise CommandError(f"Ronda desconocida: {ronda}. Usa 1, 2 o 3.")


def default_offset_m(ronda: int) -> float:
    return 400.0 if ronda == 3 else 250.0


class Command(BaseCommand):
    help = "Sub-grilla en puntos saturados — 3 rondas con offsets distintos."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--ronda",
            type=int,
            choices=(1, 2, 3),
            default=1,
            help="Patrón de sub-puntos: 1=cardinal 250m, 2=diagonal 250m, 3=cardinal 400m",
        )
        parser.add_argument(
            "--todas-rondas",
            action="store_true",
            help="Ejecuta rondas 1→3 en secuencia (solo generación, no scan)",
        )
        parser.add_argument(
            "--umbral",
            type=int,
            default=SATURATION_IDS_THRESHOLD,
            help=f"Mín. IDs en google_ids_places para subdividir (default: {SATURATION_IDS_THRESHOLD})",
        )
        parser.add_argument(
            "--alcance",
            type=str,
            choices=("saturados", "base"),
            default="saturados",
            help="saturados=todos con >=umbral IDs; base=solo celdas originales (pasada restriction)",
        )
        parser.add_argument(
            "--offset-m",
            type=float,
            default=0.0,
            help="Distancia al padre en metros (default: 250 rondas 1/2, 400 ronda 3)",
        )

    def handle(self, *args, **options):
        if options["todas_rondas"]:
            total = 0
            for ronda in (1, 2, 3):
                n = self._run_ronda(ronda, options)
                total += n
            self.stdout.write(self.style.SUCCESS(f"\n   Σ Sub-puntos nuevos (3 rondas): {total:,}"))
            return

        self._run_ronda(options["ronda"], options)

    def _run_ronda(self, ronda: int, options) -> int:
        umbral = options["umbral"]
        offset_m = options["offset_m"] or default_offset_m(ronda)
        dry_run = options["dry_run"]

        existing = set()
        for p in initialgrid_qs().values_list("points", flat=True):
            existing.add((round(p.y, 5), round(p.x, 5)))

        padres = []
        use_base = options["alcance"] == "base"
        for punto in initialgrid_qs().iterator():
            ids = punto.google_ids_places or []
            if len(ids) < umbral:
                continue
            if use_base:
                passes = punto.text_scan_passes or []
                if "restriction" not in passes:
                    continue
            padres.append(punto)

        offsets = offsets_for_ronda(ronda, offset_m)
        nuevos_coords: list[tuple[float, float]] = []
        for padre in padres:
            lat, lng = padre.points.y, padre.points.x
            for dlat_o, dlng_o in offsets:
                nlat, nlng = lat + dlat_o, lng + dlng_o
                key = (round(nlat, 5), round(nlng, 5))
                if key not in existing:
                    existing.add(key)
                    nuevos_coords.append((nlng, nlat))

        if not dry_run and nuevos_coords:
            create_grid_points_bulk(nuevos_coords)

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(
            self.style.SUCCESS(f"📊 FASE 3 — Sub-grilla ronda {ronda}: {RONDA_LABELS[ronda]}")
        )
        self.stdout.write(f"   Alcance padres:            {options['alcance']}")
        self.stdout.write(f"   Offset:                    {offset_m:.0f} m")
        self.stdout.write(f"   Puntos padre (≥{umbral} IDs): {len(padres):,}")
        self.stdout.write(f"   Sub-puntos nuevos:           {len(nuevos_coords):,}")
        if dry_run:
            self.stdout.write(self.style.WARNING("\n   ⚠️  DRY RUN — nada creado"))
        else:
            self.stdout.write(
                "\n   → python manage.py scan_place_ids_gratis --smart --pasada bias "
                "--preset all --solo-huecos\n"
            )
        return len(nuevos_coords)
