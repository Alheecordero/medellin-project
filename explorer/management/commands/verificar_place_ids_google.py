"""
Verifica que el place_id guardado en Places sigue siendo válido en Google.

Usa Text Search (New) con FieldMask mínimo places.id,nextPageToken
(tarifa IDs Only — gratuita ilimitada según la facturación actual de Google).

Reglas:
  0 resultados  → not_found
  1 resultado   → matched si coincide con place_id; review si difiere
  2+ resultados → matched si place_id está entre ellos; ambiguous si no

Uso:
  python manage.py verificar_place_ids_google --dry-run
  python manage.py verificar_place_ids_google --limit 50
  python manage.py verificar_place_ids_google --status matched
  python manage.py verificar_place_ids_google --only-pending
"""
import random
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from explorer.models import Places
from explorer.utils.google_places import (
    build_text_query,
    classify_id_match,
    text_search_ids_only,
)


class Command(BaseCommand):
    help = "Verifica place_id existentes con Text Search IDs Only (gratis)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="No guardar cambios")
        parser.add_argument("--limit", type=int, default=0, help="Máximo de lugares (0 = todos)")
        parser.add_argument(
            "--only-pending",
            action="store_true",
            help="Solo lugares con google_match_status=pending",
        )
        parser.add_argument(
            "--status",
            type=str,
            default="",
            choices=["", "pending", "matched", "ambiguous", "not_found", "review"],
            help="Filtrar por estado actual",
        )
        parser.add_argument(
            "--radio",
            type=float,
            default=150.0,
            help="Radio del locationBias en metros (default: 150)",
        )
        parser.add_argument(
            "--pause",
            type=float,
            default=0.3,
            help="Pausa entre llamadas API en segundos (default: 0.3)",
        )
        parser.add_argument(
            "--resumen",
            action="store_true",
            help="Solo mostrar conteo por estado y salir",
        )

    def handle(self, *args, **options):
        if options["resumen"]:
            self._print_resumen()
            return

        api_key = getattr(settings, "GOOGLE_API_KEY", None)
        if not api_key:
            raise CommandError("GOOGLE_API_KEY no configurada.")

        qs = Places.objects.all().order_by("id")
        if options["only_pending"]:
            qs = qs.filter(google_match_status="pending")
        elif options["status"]:
            qs = qs.filter(google_match_status=options["status"])

        if options["limit"] > 0:
            qs = qs[: options["limit"]]

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No hay lugares que verificar con esos filtros."))
            return

        dry_run = options["dry_run"]
        radio = options["radio"]
        pause = options["pause"]

        self.stdout.write(
            f"\n🔍 Verificando {total:,} lugar(es) con Text Search IDs Only"
            f"{' (DRY RUN)' if dry_run else ''}\n"
        )

        stats = {s: 0 for s, _ in Places.GOOGLE_MATCH_STATUS_CHOICES}
        stats["errores_api"] = 0
        api_calls = 0

        for i, lugar in enumerate(qs.iterator(), 1):
            lat, lng = None, None
            if lugar.ubicacion:
                lat, lng = lugar.ubicacion.y, lugar.ubicacion.x

            comuna_nombre = None
            comuna = lugar.comuna
            if comuna:
                comuna_nombre = getattr(comuna, "name", None) or str(comuna)

            text_query = build_text_query(lugar.nombre, lugar.direccion, comuna_nombre)

            try:
                found_ids = text_search_ids_only(
                    api_key,
                    text_query,
                    lat,
                    lng,
                    radius=radio,
                )
                api_calls += 1
            except requests.RequestException as exc:
                stats["errores_api"] += 1
                self.stdout.write(
                    self.style.ERROR(f"[{i}/{total}] {lugar.nombre}: error API — {exc}")
                )
                if pause > 0 and i < total:
                    time.sleep(pause + random.uniform(0, 0.2))
                continue

            status, confidence = classify_id_match(lugar.place_id, found_ids)
            stats[status] += 1

            icon = {
                "matched": "✅",
                "not_found": "❌",
                "ambiguous": "⚠️",
                "review": "🔎",
            }.get(status, "?")

            extra = ""
            if status == "review" and found_ids:
                extra = f" → Google devolvió {found_ids[0]}"
            elif status == "ambiguous":
                extra = f" → {len(found_ids)} candidatos"

            self.stdout.write(
                f"[{i}/{total}] {icon} {lugar.nombre[:50]} — {status}"
                f"{f' ({confidence})' if confidence is not None else ''}{extra}"
            )

            if not dry_run:
                lugar.google_match_status = status
                lugar.google_match_confidence = confidence
                lugar.google_match_checked_at = timezone.now()
                lugar.save(
                    update_fields=[
                        "google_match_status",
                        "google_match_confidence",
                        "google_match_checked_at",
                    ]
                )

            if pause > 0 and i < total:
                time.sleep(pause + random.uniform(0, 0.15))

        self.stdout.write(f"\n{'═' * 55}")
        self.stdout.write(self.style.SUCCESS("📊 RESUMEN"))
        self.stdout.write(f"   Lugares procesados: {total:,}")
        self.stdout.write(f"   Llamadas API:       {api_calls:,} (Text Search IDs Only ≈ $0)")
        for key, label in Places.GOOGLE_MATCH_STATUS_CHOICES:
            if stats.get(key):
                self.stdout.write(f"   {label}: {stats[key]:,}")
        if stats["errores_api"]:
            self.stdout.write(self.style.ERROR(f"   Errores API: {stats['errores_api']:,}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  DRY RUN — nada guardado"))

        self.stdout.write("")

    def _print_resumen(self):
        self.stdout.write("\n📋 Estado de verificación google_match_status:\n")
        for key, label in Places.GOOGLE_MATCH_STATUS_CHOICES:
            count = Places.objects.filter(google_match_status=key).count()
            self.stdout.write(f"   {label:15} {count:,}")
        sin_coords = Places.objects.filter(ubicacion__isnull=True).count()
        if sin_coords:
            self.stdout.write(
                self.style.WARNING(f"\n   ⚠️  {sin_coords:,} lugar(es) sin coordenadas (locationBias omitido)")
            )
        self.stdout.write("")
