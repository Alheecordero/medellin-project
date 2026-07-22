"""
Orquestador del plan gratuito de barrido Google Place IDs.

Ver PLAN_BARRIDO_GOOGLE_IDS_GRATIS.md para detalle.

Uso:
  python manage.py pipeline_barrido_gratis --dry-run
  python manage.py pipeline_barrido_gratis --status
  python manage.py pipeline_barrido_gratis --fase 0
  python manage.py pipeline_barrido_gratis --fase 1A --preset core
  python manage.py pipeline_barrido_gratis --fase 2A --dry-run
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from explorer.models import GooglePlaceId
from explorer.utils.text_scan_progress import initialgrid_qs


FASES: dict[str, dict] = {
    "0": {
        "titulo": "Fusión Places + PendingPlace → catálogo",
        "cmd": "fusionar_google_place_ids",
        "kwargs": {},
    },
    "1A": {
        "titulo": "Grilla core + barrido bias",
        "steps": [
            ("generar_grilla_cobertura", {"preset": "core"}),
            ("scan_place_ids_gratis", {"pasada": "bias", "preset": "core"}),
        ],
    },
    "1B": {
        "titulo": "Grilla turismo + barrido bias",
        "steps": [
            ("generar_grilla_cobertura", {"preset": "turismo"}),
            ("scan_place_ids_gratis", {"pasada": "bias", "preset": "turismo"}),
        ],
    },
    "1C": {
        "titulo": "Grilla valle + barrido bias",
        "steps": [
            ("generar_grilla_cobertura", {"preset": "valle"}),
            ("scan_place_ids_gratis", {"pasada": "bias", "preset": "valle"}),
        ],
    },
    "2A": {
        "titulo": "Pasada restrictiva (locationRestriction)",
        "cmd": "scan_place_ids_gratis",
        "kwargs": {"pasada": "restriction", "preset": "all"},
    },
    "2B": {
        "titulo": "Pasada genérica (sin includedType)",
        "cmd": "scan_place_ids_gratis",
        "kwargs": {"pasada": "generico", "preset": "all"},
    },
    "3": {
        "titulo": "Sub-grilla saturación + barrido bias core",
        "steps": [
            ("generar_subgrilla_saturacion", {}),
            ("scan_place_ids_gratis", {"pasada": "bias", "preset": "core"}),
        ],
    },
    "4": {
        "titulo": "Rescan puntos vacíos (radio 450 m)",
        "cmd": "scan_place_ids_gratis",
        "kwargs": {"rescan_vacios": True, "radio": 450.0, "preset": "all", "pasada": "bias"},
    },
}

ORDEN = ("0", "1A", "1B", "1C", "2A", "2B", "3", "4")


class Command(BaseCommand):
    help = "Plan gratuito de barrido GooglePlaceId (ver PLAN_BARRIDO_GOOGLE_IDS_GRATIS.md)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fase",
            type=str,
            default="",
            help=f"Fase a ejecutar: {', '.join(ORDEN)} o 'all'",
        )
        parser.add_argument("--preset", type=str, default="", help="Override preset en fases 1A/1B/1C")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--status", action="store_true")
        parser.add_argument("--limit", type=int, default=0, help="Passthrough a scan (--limit)")

    def handle(self, *args, **options):
        if options["status"]:
            self._print_status()
            return

        fase = options["fase"].strip().upper() or ""
        if not fase:
            self._print_plan()
            return

        if fase == "ALL":
            for key in ORDEN:
                self._run_fase(key, options)
            return

        if fase not in FASES:
            raise CommandError(f"Fase desconocida: {fase}. Opciones: {', '.join(ORDEN)}, all")

        self._run_fase(fase, options)

    def _run_fase(self, fase: str, options) -> None:
        spec = FASES[fase]
        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(self.style.SUCCESS(f"▶ FASE {fase} — {spec['titulo']}"))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("   ⚠️  DRY RUN"))
            for line in self._describe_fase(fase, options):
                self.stdout.write(f"   → {line}")
            return

        if "steps" in spec:
            for cmd, kwargs in spec["steps"]:
                kw = self._merge_kwargs(kwargs, options)
                call_command(cmd, **kw)
        else:
            kw = self._merge_kwargs(spec["kwargs"], options)
            call_command(spec["cmd"], **kw)

    def _merge_kwargs(self, kwargs: dict, options) -> dict:
        kw = dict(kwargs)
        if options.get("preset") and "preset" in kw:
            kw["preset"] = options["preset"]
        if options.get("limit") and "pasada" in kw:
            kw["limit"] = options["limit"]
        return kw

    def _describe_fase(self, fase: str, options) -> list[str]:
        spec = FASES[fase]
        lines = []
        if "steps" in spec:
            for cmd, kwargs in spec["steps"]:
                kw = self._merge_kwargs(kwargs, options)
                args = " ".join(f"--{k} {v}" for k, v in kw.items())
                lines.append(f"python manage.py {cmd} {args}".strip())
        else:
            kw = self._merge_kwargs(spec["kwargs"], options)
            args = " ".join(f"--{k} {v}" for k, v in kw.items())
            lines.append(f"python manage.py {spec['cmd']} {args}".strip())
        return lines

    def _print_plan(self) -> None:
        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(self.style.SUCCESS("📋 PLAN BARRIDO GRATIS — GooglePlaceId"))
        self.stdout.write("   Documento: PLAN_BARRIDO_GOOGLE_IDS_GRATIS.md\n")
        for key in ORDEN:
            spec = FASES[key]
            self.stdout.write(f"   Fase {key}: {spec['titulo']}")
        self.stdout.write("\n   Ejecutar una fase:  python manage.py pipeline_barrido_gratis --fase 0")
        self.stdout.write("   Simular:             python manage.py pipeline_barrido_gratis --fase 2A --dry-run")
        self.stdout.write("   Todo (largo):        python manage.py pipeline_barrido_gratis --fase all\n")

    def _print_status(self) -> None:
        catalogo = GooglePlaceId.objects.count()
        grilla = initialgrid_qs().count()
        try:
            bias_done = initialgrid_qs().filter(text_scan_passes__contains=["bias"]).count()
            restr_done = initialgrid_qs().filter(text_scan_passes__contains=["restriction"]).count()
            gen_done = initialgrid_qs().filter(text_scan_passes__contains=["generico"]).count()
        except Exception:
            bias_done = initialgrid_qs().filter(is_text_scan_processed=True).count()
            restr_done = gen_done = 0
        vacios = initialgrid_qs().filter(is_text_scan_processed=True, google_ids_places=[]).count()

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write("📋 ESTADO PLAN GRATUITO")
        self.stdout.write(f"   GooglePlaceId:           {catalogo:,}")
        self.stdout.write(f"   Puntos grilla:           {grilla:,}")
        self.stdout.write(f"   Pasada bias hecha:       {bias_done:,}")
        self.stdout.write(f"   Pasada restriction:      {restr_done:,}")
        self.stdout.write(f"   Pasada generico:         {gen_done:,}")
        self.stdout.write(f"   Puntos vacíos (re-scan): {vacios:,}")
        self.stdout.write("")
