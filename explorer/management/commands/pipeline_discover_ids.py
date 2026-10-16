"""
Campaña multi-ola de descubrimiento de Google Place IDs únicos.

Cada ola usa firmas distintas (área × query × rank × geometría) para maximizar
IDs nuevos. Ver STRATEGIA_NUEVOS_LUGARES.md (sección campaña W1–W7).

Uso:
  python manage.py pipeline_discover_ids
  python manage.py pipeline_discover_ids --dry-run
  python manage.py pipeline_discover_ids --ola W3
  python manage.py pipeline_discover_ids --desde W2 --skip-nearby
  python manage.py pipeline_discover_ids --status
"""

from __future__ import annotations

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from explorer.models import GooglePlaceId, PlaceDiscoveryRun, PlaceDiscoveryTask


OLAS: dict[str, dict] = {
    "W1": {
        "titulo": "Municipios OSM (Text Search IDs Only)",
        "cmd": "discover_medellin_places",
        "kwargs": {"municipios": True},
    },
    "W2": {
        "titulo": "Grilla SCAN_AREAS + pasada bias (turbo)",
        "steps": [
            ("generar_grilla_cobertura", {"preset": "all"}),
            (
                "scan_place_ids_gratis",
                {
                    "pasada": "bias",
                    "preset": "all",
                    "turbo": True,
                    "pause": 2.0,
                },
            ),
        ],
    },
    "W3": {
        "titulo": "Grilla pasadas restriction + generico (high-yield)",
        "steps": [
            (
                "scan_place_ids_gratis",
                {
                    "pasada": "restriction",
                    "preset": "all",
                    "high_yield_only": True,
                    "skip_after_ids": 50,
                    "pause": 2.0,
                },
            ),
            (
                "scan_place_ids_gratis",
                {
                    "pasada": "generico",
                    "preset": "all",
                    "skip_after_ids": 40,
                    "pause": 2.0,
                },
            ),
        ],
    },
    "W4": {
        "titulo": "Subdivisión profunda de saturadas (max-depth 3)",
        "cmd": "discover_medellin_places",
        "kwargs": {
            "municipios": True,
            "only_saturated": True,
            "max_depth": 3,
            "workers": 6,
            "qps": 10.0,
        },
    },
    "W5": {
        "titulo": "Categorías extra (hospitality / turismo / ocio)",
        "cmd": "discover_medellin_places",
        "kwargs": {
            "municipios": True,
            "categorias": "extra",
            "workers": 6,
            "qps": 10.0,
        },
    },
    "W6": {
        "titulo": "Rescan huecos + smart sub-grilla (ronda 1)",
        "steps": [
            ("generar_subgrilla_saturacion", {"ronda": 1}),
            (
                "scan_place_ids_gratis",
                {
                    "pasada": "bias",
                    "preset": "all",
                    "smart": True,
                    "solo_huecos": True,
                    "pause": 2.0,
                },
            ),
            (
                "scan_place_ids_gratis",
                {
                    "pasada": "bias",
                    "preset": "all",
                    "smart": True,
                    "rescan_vacios": True,
                    "radio": 450.0,
                    "pause": 2.0,
                },
            ),
        ],
    },
    "W7": {
        "titulo": "Nearby Search acotado (SKU Pro) — DESACTIVADA",
        "cmd": "discover_medellin_places",
        "kwargs": {
            "municipios": True,
            "nearby": True,
            "nearby_budget": 400,
            "nearby_radius": 400.0,
        },
        "nearby": True,
    },
    "W8": {
        "titulo": "Malla desplazada 3 rondas + bias/restriction/generico",
        "steps": [
            ("generar_subgrilla_saturacion", {"todas_rondas": True}),
            (
                "scan_place_ids_gratis",
                {"pasada": "bias", "preset": "all", "pause": 2.0},
            ),
            (
                "scan_place_ids_gratis",
                {
                    "pasada": "restriction",
                    "preset": "all",
                    "high_yield_only": True,
                    "skip_after_ids": 55,
                    "pause": 2.0,
                },
            ),
            (
                "scan_place_ids_gratis",
                {
                    "pasada": "generico",
                    "preset": "all",
                    "skip_after_ids": 40,
                    "pause": 2.0,
                },
            ),
        ],
    },
    "W9": {
        "titulo": "Consultas por barrio/corredor (Provenza, La 70, Guatapé…)",
        "cmd": "discover_medellin_places",
        "kwargs": {
            "municipios": True,
            "categorias": "barrio",
            "workers": 6,
            "qps": 10.0,
        },
    },
    "W10": {
        "titulo": "Subdivisión profunda saturadas (max-depth 5)",
        "cmd": "discover_medellin_places",
        "kwargs": {
            "municipios": True,
            "only_saturated": True,
            "max_depth": 5,
            "workers": 6,
            "qps": 10.0,
        },
    },
}

# Gratis por defecto (sin W7 Nearby)
ORDEN = ("W1", "W2", "W3", "W4", "W5", "W6", "W8", "W9", "W10")
ORDEN_CON_NEARBY = ("W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10")
SEP = "═" * 64


class Command(BaseCommand):
    help = (
        "Campaña W1–W7 de barridos para maximizar Google Place IDs únicos. "
        "Por defecto SOLO gratis (Text Search IDs Only); W7 Nearby requiere --include-nearby."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--ola",
            type=str,
            default="",
            help=f"Ejecutar una sola ola: {', '.join(ORDEN)}",
        )
        parser.add_argument(
            "--desde",
            type=str,
            default="",
            help="Ejecutar desde esta ola hasta el final (ej: W2)",
        )
        parser.add_argument(
            "--include-nearby",
            action="store_true",
            help="Incluir W7 Nearby Search Pro (DE PAGO). Por defecto la campaña es solo gratis.",
        )
        parser.add_argument(
            "--skip-nearby",
            action="store_true",
            help="(Redundante) W7 ya se omite por defecto; se mantiene por compatibilidad.",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--status", action="store_true")

    def handle(self, *args, **options):
        # Política por defecto: solo Text Search IDs Only ($0).
        if options.get("include_nearby"):
            import os

            if os.environ.get("ALLOW_PAID_GOOGLE_PLACES") != "1":
                raise CommandError(
                    "Nearby desactivado. Para habilitarlo: "
                    "ALLOW_PAID_GOOGLE_PLACES=1 … --include-nearby"
                )
            options["skip_nearby"] = False
        else:
            options["skip_nearby"] = True

        if options["status"]:
            self._print_status()
            return

        ola = options["ola"].strip().upper()
        desde = options["desde"].strip().upper()

        if ola and desde:
            raise CommandError("Usa --ola o --desde, no ambos.")

        if not ola and not desde:
            self._print_plan(options)
            if options["dry_run"]:
                for key in self._olas_a_ejecutar("W1", options):
                    self._run_ola(key, options)
            return

        if ola:
            key = self._normalize(ola)
            self._run_ola(key, options)
            return

        start = self._normalize(desde)
        for key in self._olas_a_ejecutar(start, options):
            self._run_ola(key, options)

    def _normalize(self, key: str) -> str:
        key = key.upper()
        if key not in OLAS:
            raise CommandError(
                f"Ola desconocida: {key}. Opciones: {', '.join(ORDEN_CON_NEARBY)}"
            )
        return key

    def _olas_a_ejecutar(self, start: str, options) -> list[str]:
        start = self._normalize(start)
        orden = ORDEN_CON_NEARBY if not options.get("skip_nearby") else ORDEN
        if start == "W7" and options.get("skip_nearby"):
            raise CommandError(
                "W7 Nearby está desactivado (de pago). "
                "Usa --include-nearby y ALLOW_PAID_GOOGLE_PLACES=1."
            )
        if start not in orden:
            raise CommandError(f"Ola {start} no está en el plan activo.")
        return list(orden[orden.index(start) :])

    def _catalog_count(self) -> int:
        return GooglePlaceId.objects.count()

    def _run_ola(self, key: str, options) -> None:
        spec = OLAS[key]
        if spec.get("nearby") and options["skip_nearby"]:
            self.stdout.write(self.style.WARNING(f"⏭  {key} omitida (--skip-nearby)"))
            return

        before = self._catalog_count()
        self.stdout.write(f"\n{SEP}")
        self.stdout.write(self.style.SUCCESS(f"▶ {key} — {spec['titulo']}"))
        self.stdout.write(f"   Catálogo antes: {before:,}")

        if options["dry_run"]:
            for line in self._describe(key):
                self.stdout.write(f"   → {line}")
            self.stdout.write(self.style.WARNING("   ⚠️  DRY RUN — sin llamadas API"))
            return

        started = time.monotonic()
        if "steps" in spec:
            for cmd, kwargs in spec["steps"]:
                call_command(cmd, **dict(kwargs))
        else:
            call_command(spec["cmd"], **dict(spec["kwargs"]))

        after = self._catalog_count()
        delta = after - before
        elapsed = time.monotonic() - started
        self.stdout.write(f"\n{SEP}")
        self.stdout.write(
            self.style.SUCCESS(
                f"✔ {key} lista · catálogo {after:,} · "
                f"delta +{delta:,} · {elapsed / 60:.1f} min"
            )
        )
        if delta == 0:
            self.stdout.write(
                self.style.WARNING(
                    "   Delta 0: la siguiente ola puede tener poco margen en este alcance"
                )
            )

    def _describe(self, key: str) -> list[str]:
        spec = OLAS[key]
        lines = []
        if "steps" in spec:
            for cmd, kwargs in spec["steps"]:
                args = " ".join(self._fmt_arg(k, v) for k, v in kwargs.items())
                lines.append(f"python manage.py {cmd} {args}".strip())
        else:
            args = " ".join(self._fmt_arg(k, v) for k, v in spec["kwargs"].items())
            lines.append(f"python manage.py {spec['cmd']} {args}".strip())
        return lines

    @staticmethod
    def _fmt_arg(key: str, value) -> str:
        flag = key.replace("_", "-")
        if value is True:
            return f"--{flag}"
        if value is False:
            return ""
        return f"--{flag} {value}"

    def _print_plan(self, options) -> None:
        self.stdout.write(f"\n{SEP}")
        self.stdout.write(self.style.SUCCESS("📋 CAMPAÑA MULTI-BARRIDO — IDs únicos"))
        self.stdout.write(f"   Catálogo actual: {self._catalog_count():,}\n")
        for key in ORDEN:
            self.stdout.write(f"   {key}: {OLAS[key]['titulo']}")
        self.stdout.write(
            self.style.WARNING(f"   W7: {OLAS['W7']['titulo']}")
        )
        self.stdout.write("\n   Una ola:     python manage.py pipeline_discover_ids --ola W8")
        self.stdout.write("   Desde W8:    python manage.py pipeline_discover_ids --desde W8")
        self.stdout.write("   Simular:     python manage.py pipeline_discover_ids --desde W8 --dry-run\n")
        self.stdout.write(
            self.style.WARNING("   Política activa: SOLO GRATIS (Nearby desactivado)\n")
        )

    def _print_status(self) -> None:
        from django.db.models import Count
        from django.db import connection

        catalogo = self._catalog_count()
        with connection.cursor() as c:
            c.execute(
                """
                SELECT COUNT(*) FROM explorer_googleplaceid g
                WHERE NOT EXISTS (
                  SELECT 1 FROM explorer_places p WHERE p.place_id = g.place_id
                )
                """
            )
            sin_ficha = c.fetchone()[0]
        by_status = {
            row["status"]: row["n"]
            for row in PlaceDiscoveryTask.objects.values("status").annotate(n=Count("id"))
        }
        run = PlaceDiscoveryRun.objects.order_by("-id").first()
        self.stdout.write(f"\n{SEP}")
        self.stdout.write("📋 ESTADO CAMPAÑA DISCOVER IDs")
        self.stdout.write(f"   GooglePlaceId:     {catalogo:,}")
        self.stdout.write(f"   Sin ficha:         {sin_ficha:,}")
        for status in ("pending", "running", "done", "error"):
            self.stdout.write(f"   tasks {status:8}  {by_status.get(status, 0):,}")
        if run:
            self.stdout.write(
                f"   Última corrida:    #{run.id} {run.status} · "
                f"nuevos={run.ids_new:,} · api={run.api_calls:,}"
            )
        self.stdout.write("")
