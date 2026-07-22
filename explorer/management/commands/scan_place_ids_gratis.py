"""
Descubre Google place_id en Medellín/Envigado usando Text Search IDs Only (GRATIS).

A diferencia de scan_nuevos_lugares (Nearby Search, de pago), este comando:
  - Recorre la grilla (Initialgrid)
  - Por cada punto ejecuta Text Search con includedType + locationBias
  - FieldMask: places.id,nextPageToken  → tarifa IDs Only (gratis ilimitado)
  - Guarda IDs nuevos en PendingPlace para scrape/enriquecimiento posterior

Flujo recomendado:
  1. generar_grilla_vive_medellin
  2. scan_place_ids_gratis
  3. descartar_pendientes_inutiles
  4. exportar IDs o procesar selectivamente

Uso:
  python manage.py scan_place_ids_gratis --dry-run
  python manage.py scan_place_ids_gratis --limit 5 --limit-tipos 3
  python manage.py scan_place_ids_gratis --export-ids ids_medellin.txt
  python manage.py scan_place_ids_gratis --reset-text-scan
"""
import random
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from explorer.models import PendingPlace, Places
from explorer.utils.google_places import text_search_ids_only
from explorer.utils.text_scan_progress import (
    PROGRESS_FILE,
    count_progress,
    has_db_text_scan_field,
    initialgrid_qs,
    load_progress_ids,
    mark_done,
    reset_progress,
)
from explorer.utils.vive_areas import VIVE_MEDELLIN_ENVIGADO, VIVE_SEARCH_TYPES, point_in_vive_areas


class Command(BaseCommand):
    help = "Descubre place_id gratis vía Text Search (grilla × tipos ViveMedellín)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Estimar sin llamar API ni guardar")
        parser.add_argument("--limit", type=int, default=0, help="Máx. puntos de grilla (0 = todos)")
        parser.add_argument(
            "--limit-tipos",
            type=int,
            default=0,
            help="Máx. tipos por punto (0 = todos; útil para pruebas)",
        )
        parser.add_argument(
            "--radio",
            type=float,
            default=600.0,
            help="Radio del círculo de búsqueda en metros (default: 600)",
        )
        parser.add_argument(
            "--pause",
            type=float,
            default=0.25,
            help="Pausa entre llamadas API en segundos",
        )
        parser.add_argument(
            "--reset-text-scan",
            action="store_true",
            help="Marcar todos los puntos como no escaneados (text)",
        )
        parser.add_argument(
            "--incluir-fuera-vive",
            action="store_true",
            help="Incluir puntos fuera de Medellín/Envigado (ej. Rionegro en la grilla)",
        )
        parser.add_argument(
            "--export-ids",
            type=str,
            default="",
            help="Al terminar, exportar todos los place_id (Places + PendingPlace) a un archivo",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Solo mostrar estadísticas y salir",
        )

    def handle(self, *args, **options):
        if options["status"]:
            self._print_status()
            return

        if options["reset_text_scan"]:
            if has_db_text_scan_field():
                n = initialgrid_qs().filter(is_text_scan_processed=True).update(
                    is_text_scan_processed=False
                )
                self.stdout.write(self.style.WARNING(f"🔄 {n} puntos reseteados en BD"))
            n_file = reset_progress()
            if n_file:
                self.stdout.write(self.style.WARNING(f"🔄 {n_file} IDs borrados de {PROGRESS_FILE}"))
            if not has_db_text_scan_field() and not n_file:
                self.stdout.write("   (sin progreso previo)")
            if not any(v for k, v in options.items() if k not in ("status", "reset_text_scan", "verbosity") and v):
                return

        api_key = getattr(settings, "GOOGLE_API_KEY", None)
        if not api_key and not options["dry_run"]:
            raise CommandError("GOOGLE_API_KEY no configurada.")

        search_types = VIVE_SEARCH_TYPES
        if options["limit_tipos"] > 0:
            search_types = search_types[: options["limit_tipos"]]

        puntos = self._get_pending_points()
        if not options["incluir_fuera_vive"]:
            puntos = self._filter_vive_points(puntos)

        if options["limit"] > 0:
            puntos = puntos[: options["limit"]]

        total_puntos = puntos.count()
        if total_puntos == 0:
            self.stdout.write(self.style.SUCCESS("✅ No hay puntos pendientes de Text Search."))
            self.stdout.write("   → generar_grilla_vive_medellin  o  --reset-text-scan")
            return

        dry_run = options["dry_run"]
        radio = options["radio"]
        pause = options["pause"]
        llamadas_estimadas = total_puntos * len(search_types)

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(self.style.SUCCESS("🆓 SCAN GRATIS — Text Search IDs Only"))
        self.stdout.write(f"   Puntos grilla:     {total_puntos:,}")
        self.stdout.write(f"   Tipos por punto:   {len(search_types)}")
        self.stdout.write(f"   Llamadas API est.: {llamadas_estimadas:,}  (~$0 USD)")
        self.stdout.write(f"   Radio búsqueda:    {radio:.0f} m")
        if dry_run:
            self.stdout.write(self.style.WARNING("   ⚠️  DRY RUN"))
        self.stdout.write("")

        if dry_run:
            for i, (query, tipo) in enumerate(search_types[:5], 1):
                self.stdout.write(f"   Tipo {i}: «{query}» → {tipo}")
            if len(search_types) > 5:
                self.stdout.write(f"   … y {len(search_types) - 5} tipos más")
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n   IDs en cola actual: PendingPlace={PendingPlace.objects.count():,} | "
                    f"Places={Places.objects.count():,}"
                )
            )
            return

        known_ids = set(Places.objects.values_list("place_id", flat=True))
        known_ids |= set(PendingPlace.objects.values_list("place_id", flat=True))

        stats = {
            "puntos": 0,
            "api_calls": 0,
            "ids_devueltos": 0,
            "nuevos": 0,
            "ya_existian": 0,
            "errores": 0,
        }

        for i, punto in enumerate(puntos, 1):
            lat, lng = punto.points.y, punto.points.x
            self.stdout.write(f"\n📍 [{i}/{total_puntos}] Punto {punto.id} ({lat:.5f}, {lng:.5f})")
            nuevos_punto = 0

            for query, included_type in search_types:
                try:
                    found = text_search_ids_only(
                        api_key,
                        query,
                        lat,
                        lng,
                        included_type=included_type,
                        radius=radio,
                    )
                    stats["api_calls"] += 1
                    stats["ids_devueltos"] += len(found)
                except requests.RequestException as exc:
                    stats["errores"] += 1
                    self.stdout.write(self.style.ERROR(f"   ✗ {included_type}: {exc}"))
                    if pause > 0:
                        time.sleep(pause)
                    continue

                for pid in found:
                    if pid in known_ids:
                        stats["ya_existian"] += 1
                        continue

                    PendingPlace.objects.get_or_create(
                        place_id=pid,
                        defaults={
                            "nombre": "",
                            "lat": lat,
                            "lng": lng,
                            "tipos": [included_type],
                            "status": "pending",
                        },
                    )
                    known_ids.add(pid)
                    stats["nuevos"] += 1
                    nuevos_punto += 1

                if pause > 0:
                    time.sleep(pause + random.uniform(0, 0.1))

            self._mark_point_done(punto)
            stats["puntos"] += 1

            if nuevos_punto:
                self.stdout.write(self.style.SUCCESS(f"   🆕 +{nuevos_punto} IDs nuevos"))
            else:
                self.stdout.write("   — sin IDs nuevos")

        self._print_resumen(stats)

        if options["export_ids"]:
            self._export_ids(options["export_ids"])

    def _get_pending_points(self):
        qs = initialgrid_qs().order_by("id")
        if has_db_text_scan_field():
            return qs.filter(is_text_scan_processed=False)
        done = load_progress_ids()
        if done:
            return qs.exclude(id__in=done)
        return qs

    def _count_pending_points(self) -> int:
        return self._get_pending_points().count()

    def _mark_point_done(self, punto) -> None:
        if has_db_text_scan_field():
            punto.is_text_scan_processed = True
            punto.save(update_fields=["is_text_scan_processed"])
        else:
            mark_done(punto.id)

    def _filter_vive_points(self, qs):
        """Filtra puntos dentro de Medellín/Envigado/zonas prioritarias."""
        ids_ok = []
        for p in qs.iterator():
            if point_in_vive_areas(p.points.y, p.points.x):
                ids_ok.append(p.id)
        return initialgrid_qs().filter(id__in=ids_ok).order_by("id")

    def _print_resumen(self, stats):
        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(self.style.SUCCESS("📊 RESUMEN SCAN GRATIS"))
        self.stdout.write(f"   Puntos procesados:  {stats['puntos']:,}")
        self.stdout.write(f"   Llamadas API:       {stats['api_calls']:,}  (Text Search IDs Only ≈ $0)")
        self.stdout.write(f"   IDs devueltos:      {stats['ids_devueltos']:,}")
        self.stdout.write(f"   Ya conocidos:       {stats['ya_existian']:,}")
        self.stdout.write(self.style.SUCCESS(f"   🆕 NUEVOS en cola:   {stats['nuevos']:,}"))
        if stats["errores"]:
            self.stdout.write(self.style.ERROR(f"   Errores API:        {stats['errores']:,}"))

        pending = PendingPlace.objects.filter(status="pending").count()
        pendientes_grilla = self._count_pending_points()
        self.stdout.write(f"\n   📋 PendingPlace pending: {pending:,}")
        self.stdout.write(f"   ⏳ Puntos grilla restantes: {pendientes_grilla:,}")
        self.stdout.write("\n   → python manage.py descartar_pendientes_inutiles")
        self.stdout.write("   → python manage.py scan_place_ids_gratis --export-ids ids.txt\n")

    def _export_ids(self, filepath):
        places_ids = set(Places.objects.values_list("place_id", flat=True))
        pending_ids = set(PendingPlace.objects.values_list("place_id", flat=True))
        all_ids = sorted(places_ids | pending_ids)
        with open(filepath, "w", encoding="utf-8") as f:
            for pid in all_ids:
                f.write(f"{pid}\n")
        self.stdout.write(self.style.SUCCESS(f"📄 Exportados {len(all_ids):,} place_id → {filepath}"))

    def _print_status(self):
        total_grilla = initialgrid_qs().count()
        if has_db_text_scan_field():
            text_done = initialgrid_qs().filter(is_text_scan_processed=True).count()
        else:
            text_done = count_progress()
        nearby_done = initialgrid_qs().filter(is_processed=True).count()
        pending = PendingPlace.objects.filter(status="pending").count()
        places = Places.objects.count()

        vive_pendientes = 0
        for p in self._get_pending_points().iterator():
            if point_in_vive_areas(p.points.y, p.points.x):
                vive_pendientes += 1

        tipos = len(VIVE_SEARCH_TYPES)
        llamadas_restantes = vive_pendientes * tipos

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write("📋 ESTADO — Descubrimiento gratis de place_id")
        self.stdout.write(f"   Places en BD:              {places:,}")
        self.stdout.write(f"   PendingPlace (pending):   {pending:,}")
        self.stdout.write(f"   Grilla total:             {total_grilla:,}")
        self.stdout.write(f"   Text scan hecho:          {text_done:,}")
        self.stdout.write(f"   Nearby scan hecho:        {nearby_done:,}")
        self.stdout.write(f"   Puntos Vive pendientes:   {vive_pendientes:,}")
        self.stdout.write(f"   Llamadas API restantes:   ~{llamadas_restantes:,}  (~$0)")
        self.stdout.write(f"   Tipos por punto:          {tipos}")
        if not has_db_text_scan_field():
            self.stdout.write(self.style.WARNING(f"   Progreso en archivo:      {PROGRESS_FILE}"))
        self.stdout.write("")
