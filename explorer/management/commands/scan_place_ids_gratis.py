"""
Descubre Google place_id usando Text Search IDs Only (GRATIS).

Guarda en GooglePlaceId — catálogo INDEPENDIENTE de Places y PendingPlace.
Recorre la grilla × tipos × zonas (Medellín, Envigado, Rionegro, Guatapé, etc.).

Flujo recomendado:
  1. generar_grilla_cobertura --preset all
  2. scan_place_ids_gratis --preset all
  3. scan_place_ids_gratis --rescan-vacios   # 2ª pasada en puntos sin IDs
  4. scan_place_ids_gratis --export-ids data/google_place_ids.txt

Plan completo gratuito: PLAN_BARRIDO_GOOGLE_IDS_GRATIS.md
  python manage.py pipeline_barrido_gratis --status

Pasadas (--pasada):
  bias        → locationBias + tipos (default, fase 1)
  restriction → locationRestriction + tipos (fase 2A)
  generico    → queries genéricas sin tipo (fase 2B)

Uso:
  python manage.py scan_place_ids_gratis --status
  python manage.py scan_place_ids_gratis --preset valle --dry-run
  python manage.py scan_place_ids_gratis --solo Guatapé --limit 5
  python manage.py scan_place_ids_gratis --export-ids ids.txt
  python manage.py scan_place_ids_gratis --sync-pending   # opcional: también PendingPlace
"""
import random
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from explorer.models import GooglePlaceId, PendingPlace, Places
from explorer.utils.google_ids_registry import register_google_place_ids
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
from explorer.utils.vive_areas import (
    GENERIC_SEARCH_QUERIES,
    VIVE_SEARCH_TYPES,
    areas_for_point,
    point_in_scan_areas,
    resolve_area_names,
)

PASADA_SOURCES = {
    "bias": "text_search_ids",
    "restriction": "text_search_restriction",
    "generico": "text_search_generico",
}


class Command(BaseCommand):
    help = "Descubre place_id gratis → catálogo GooglePlaceId (independiente de Places)."

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
            "--preset",
            type=str,
            default="all",
            help="core | valle | turismo | all (default: all)",
        )
        parser.add_argument(
            "--solo",
            type=str,
            default="",
            help="Solo un área SCAN_AREAS (ej: Rionegro, Guatapé)",
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
            "--retries",
            type=int,
            default=3,
            help="Reintentos por error transitorio de Google (default: 3)",
        )
        parser.add_argument(
            "--reset-text-scan",
            action="store_true",
            help="Marcar todos los puntos como no escaneados (text)",
        )
        parser.add_argument(
            "--rescan-vacios",
            action="store_true",
            help="Re-escanear puntos ya procesados pero sin IDs en google_ids_places",
        )
        parser.add_argument(
            "--sync-pending",
            action="store_true",
            help="También crear PendingPlace para IDs nuevos (pipeline legacy)",
        )
        parser.add_argument(
            "--export-ids",
            type=str,
            default="",
            help="Al terminar, exportar todos los place_id del catálogo a un archivo",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Solo mostrar estadísticas y salir",
        )
        parser.add_argument(
            "--pasada",
            type=str,
            default="bias",
            choices=("bias", "restriction", "generico"),
            help="Modo de barrido: bias (fase 1), restriction (2A), generico (2B)",
        )
        parser.add_argument(
            "--shard",
            type=int,
            default=0,
            help="Índice de shard para paralelizar (0..shards-1)",
        )
        parser.add_argument(
            "--shards",
            type=int,
            default=1,
            help="Total de shards disjuntos (ej: 3 workers en paralelo)",
        )
        parser.add_argument(
            "--incluir-fuera-vive",
            action="store_true",
            help="(Obsoleto) Usar --preset all",
        )

    def handle(self, *args, **options):
        if options["status"]:
            self._print_status(options)
            return

        if options["reset_text_scan"]:
            if has_db_text_scan_field():
                n = initialgrid_qs().filter(is_text_scan_processed=True).update(
                    is_text_scan_processed=False,
                    google_ids_places=[],
                    text_scan_passes=[],
                )
                self.stdout.write(self.style.WARNING(f"🔄 {n} puntos reseteados en BD"))
            n_file = reset_progress()
            if n_file:
                self.stdout.write(self.style.WARNING(f"🔄 {n_file} IDs borrados de {PROGRESS_FILE}"))
            if not has_db_text_scan_field() and not n_file:
                self.stdout.write("   (sin progreso previo)")
            if not any(
                v
                for k, v in options.items()
                if k not in ("status", "reset_text_scan", "verbosity", "incluir_fuera_vive") and v
            ):
                return

        try:
            self.area_names = resolve_area_names(
                solo=options["solo"].strip(),
                preset="all" if options["incluir_fuera_vive"] else options["preset"].strip(),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        api_key = getattr(settings, "GOOGLE_API_KEY", None)
        if not api_key and not options["dry_run"]:
            raise CommandError("GOOGLE_API_KEY no configurada.")

        search_types = self._search_types_for_pasada(options["pasada"])
        if options["limit_tipos"] > 0:
            search_types = search_types[: options["limit_tipos"]]

        pasada = options["pasada"]
        use_restriction = pasada in ("restriction", "generico")
        source = PASADA_SOURCES[pasada]

        puntos = self._get_pending_points(options)
        puntos = self._filter_scan_points(puntos)
        puntos = self._filter_shard(puntos, options)

        if options["limit"] > 0:
            puntos = puntos[: options["limit"]]

        total_puntos = puntos.count()
        if total_puntos == 0:
            self.stdout.write(self.style.SUCCESS("✅ No hay puntos pendientes de Text Search."))
            self.stdout.write("   → generar_grilla_cobertura --preset all")
            self.stdout.write("   → scan_place_ids_gratis --reset-text-scan  (repetir barrido)")
            return

        dry_run = options["dry_run"]
        radio = options["radio"]
        pause = options["pause"]
        llamadas_estimadas = total_puntos * len(search_types)

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(self.style.SUCCESS("🆓 SCAN GRATIS → GooglePlaceId (catálogo independiente)"))
        self.stdout.write(f"   Pasada:              {pasada}")
        if options["shards"] > 1:
            self.stdout.write(
                f"   Shard:               {options['shard']}/{options['shards'] - 1}"
            )
        self.stdout.write(f"   Zonas:             {', '.join(self.area_names)}")
        self.stdout.write(f"   Puntos grilla:     {total_puntos:,}")
        self.stdout.write(f"   Tipos por punto:   {len(search_types)}")
        self.stdout.write(f"   Llamadas API est.: {llamadas_estimadas:,}  (~$0 USD)")
        self.stdout.write(f"   Radio búsqueda:    {radio:.0f} m")
        if options["sync_pending"]:
            self.stdout.write(self.style.WARNING("   ↪ También escribe PendingPlace (--sync-pending)"))
        if dry_run:
            self.stdout.write(self.style.WARNING("   ⚠️  DRY RUN"))
        self.stdout.write("")

        if dry_run:
            for i, item in enumerate(search_types[:5], 1):
                if pasada == "generico":
                    self.stdout.write(f"   Query {i}: «{item[0]}»")
                else:
                    self.stdout.write(f"   Tipo {i}: «{item[0]}» → {item[1]}")
            if len(search_types) > 5:
                self.stdout.write(f"   … y {len(search_types) - 5} tipos más")
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n   Catálogo GooglePlaceId: {GooglePlaceId.objects.count():,} | "
                    f"Places={Places.objects.count():,} | PendingPlace={PendingPlace.objects.count():,}"
                )
            )
            return

        # Falla antes de gastar llamadas a Google si la BD no está disponible.
        try:
            connections["default"].ensure_connection()
        except Exception as exc:
            raise CommandError(
                "La base de datos no está disponible; el scan no inició para evitar "
                f"perder progreso. Detalle: {exc}"
            ) from exc

        known_pending = set()
        if options["sync_pending"]:
            known_pending = set(Places.objects.values_list("place_id", flat=True))
            known_pending |= set(PendingPlace.objects.values_list("place_id", flat=True))

        stats = {
            "puntos": 0,
            "api_calls": 0,
            "ids_devueltos": 0,
            "nuevos_catalogo": 0,
            "actualizados_catalogo": 0,
            "nuevos_pending": 0,
            "errores": 0,
            "puntos_con_error": 0,
        }

        for i, punto in enumerate(puntos, 1):
            lat, lng = punto.points.y, punto.points.x
            zonas_punto = areas_for_point(lat, lng, self.area_names)
            self.stdout.write(
                f"\n📍 [{i}/{total_puntos}] Punto {punto.id} ({lat:.5f}, {lng:.5f})"
                + (f" — {', '.join(zonas_punto)}" if zonas_punto else "")
            )
            ids_en_punto: set[str] = set()
            punto_completo = True

            for query, included_type in search_types:
                try:
                    found = text_search_ids_only(
                        api_key,
                        query,
                        lat,
                        lng,
                        included_type=included_type or None,
                        radius=radio,
                        use_restriction=use_restriction,
                        retries=options["retries"],
                    )
                    stats["api_calls"] += 1
                    stats["ids_devueltos"] += len(found)
                except requests.RequestException as exc:
                    stats["errores"] += 1
                    punto_completo = False
                    label = included_type or query
                    self.stdout.write(self.style.ERROR(f"   ✗ {label}: {exc}"))
                    if pause > 0:
                        time.sleep(pause)
                    continue

                for pid in found:
                    ids_en_punto.add(pid)

                nuevos_tipo, actualizados_tipo = register_google_place_ids(
                    found,
                    grid_point_id=punto.id,
                    scan_lat=lat,
                    scan_lng=lng,
                    included_type=included_type or pasada,
                    area_names=zonas_punto,
                    source=source,
                )
                stats["nuevos_catalogo"] += nuevos_tipo
                stats["actualizados_catalogo"] += actualizados_tipo

                if options["sync_pending"]:
                    for pid in found:
                        if pid in known_pending:
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
                        known_pending.add(pid)
                        stats["nuevos_pending"] += 1

                if pause > 0:
                    time.sleep(pause + random.uniform(0, 0.1))

            if punto_completo:
                self._mark_point_done(punto, sorted(ids_en_punto), pasada)
                stats["puntos"] += 1
            else:
                stats["puntos_con_error"] += 1
                self.stdout.write(
                    self.style.WARNING(
                        "   ↻ Punto no marcado como terminado: se reintentará completo al reanudar."
                    )
                )

            if ids_en_punto:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"   ✓ {len(ids_en_punto)} IDs en este punto "
                        f"(catálogo total: {GooglePlaceId.objects.count():,})"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING("   ⚠️  0 IDs — considera --rescan-vacios con --radio 450"))

        self._print_resumen(stats, options)

        if options["export_ids"]:
            self._export_ids(options["export_ids"])

    def _search_types_for_pasada(self, pasada: str) -> list[tuple[str, str]]:
        if pasada == "generico":
            return [(q, "") for q in GENERIC_SEARCH_QUERIES]
        return list(VIVE_SEARCH_TYPES)

    def _get_pending_points(self, options):
        pasada = options.get("pasada", "bias")
        qs = initialgrid_qs().order_by("id")
        if options["rescan_vacios"]:
            if has_db_text_scan_field():
                return qs.filter(is_text_scan_processed=True, google_ids_places=[])
            self.stdout.write(
                self.style.WARNING("   --rescan-vacios requiere migración 0031 (google_ids_places)")
            )
        if pasada == "bias":
            if has_db_text_scan_field():
                return qs.filter(is_text_scan_processed=False)
            done = load_progress_ids()
            if done:
                return qs.exclude(id__in=done)
            return qs
        # restriction / generico: requiere bias hecho, pasada pendiente
        return qs.filter(is_text_scan_processed=True).exclude(
            text_scan_passes__contains=[pasada]
        )

    def _count_pending_points(self, options) -> int:
        return self._get_pending_points(options).count()

    def _filter_shard(self, qs, options):
        shards = options.get("shards", 1)
        shard = options.get("shard", 0)
        if shards <= 1:
            return qs
        if shard < 0 or shard >= shards:
            raise CommandError(f"--shard debe estar entre 0 y {shards - 1}")
        ids = [p.id for p in qs.only("id").iterator() if p.id % shards == shard]
        return initialgrid_qs().filter(id__in=ids).order_by("id")

    def _filter_scan_points(self, qs):
        ids_ok = []
        for p in qs.iterator():
            if point_in_scan_areas(p.points.y, p.points.x, self.area_names):
                ids_ok.append(p.id)
        return initialgrid_qs().filter(id__in=ids_ok).order_by("id")

    def _mark_point_done(
        self, punto, google_ids_places: list[str] | None, pasada: str = "bias"
    ) -> None:
        if has_db_text_scan_field():
            passes = list(punto.text_scan_passes or [])
            if pasada not in passes:
                passes.append(pasada)
            punto.text_scan_passes = passes
            update_fields = ["text_scan_passes"]
            if pasada == "bias":
                punto.is_text_scan_processed = True
                update_fields.append("is_text_scan_processed")
            if google_ids_places is not None:
                if pasada == "bias":
                    punto.google_ids_places = google_ids_places
                else:
                    merged = sorted(set(punto.google_ids_places or []) | set(google_ids_places))
                    punto.google_ids_places = merged
                update_fields.append("google_ids_places")
            punto.save(update_fields=update_fields)
        else:
            mark_done(punto.id)

    def _print_resumen(self, stats, options):
        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(self.style.SUCCESS("📊 RESUMEN SCAN GRATIS → GooglePlaceId"))
        self.stdout.write(f"   Puntos procesados:        {stats['puntos']:,}")
        self.stdout.write(f"   Llamadas API:             {stats['api_calls']:,}  (~$0)")
        self.stdout.write(f"   IDs devueltos por Google: {stats['ids_devueltos']:,}")
        self.stdout.write(self.style.SUCCESS(f"   🆕 Nuevos en catálogo:     {stats['nuevos_catalogo']:,}"))
        self.stdout.write(f"   ↻ Actualizados catálogo:   {stats['actualizados_catalogo']:,}")
        if options["sync_pending"]:
            self.stdout.write(f"   PendingPlace nuevos:      {stats['nuevos_pending']:,}")
        if stats["errores"]:
            self.stdout.write(self.style.ERROR(f"   Errores API:              {stats['errores']:,}"))
        if stats["puntos_con_error"]:
            self.stdout.write(
                self.style.WARNING(f"   Puntos para reintentar:      {stats['puntos_con_error']:,}")
            )

        catalogo = GooglePlaceId.objects.count()
        pendientes_grilla = self._count_pending_points(options)
        vacios = 0
        if has_db_text_scan_field():
            vacios = initialgrid_qs().filter(
                is_text_scan_processed=True,
                google_ids_places=[],
            ).count()

        self.stdout.write(f"\n   📚 Catálogo GooglePlaceId: {catalogo:,}")
        self.stdout.write(f"   ⏳ Puntos grilla restantes: {pendientes_grilla:,}")
        if vacios:
            self.stdout.write(self.style.WARNING(f"   ⚠️  Puntos escaneados sin IDs: {vacios:,}"))
            self.stdout.write("   → python manage.py scan_place_ids_gratis --rescan-vacios --radio 450")
        self.stdout.write("   → python manage.py scan_place_ids_gratis --export-ids data/google_place_ids.txt\n")

    def _export_ids(self, filepath):
        all_ids = list(GooglePlaceId.objects.order_by("place_id").values_list("place_id", flat=True))
        with open(filepath, "w", encoding="utf-8") as f:
            for pid in all_ids:
                f.write(f"{pid}\n")
        self.stdout.write(self.style.SUCCESS(f"📄 Exportados {len(all_ids):,} place_id → {filepath}"))

    def _print_status(self, options):
        try:
            area_names = resolve_area_names(
                solo=options["solo"].strip(),
                preset=options["preset"].strip(),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        total_grilla = initialgrid_qs().count()
        if has_db_text_scan_field():
            text_done = initialgrid_qs().filter(is_text_scan_processed=True).count()
            vacios = initialgrid_qs().filter(is_text_scan_processed=True, google_ids_places=[]).count()
        else:
            text_done = count_progress()
            vacios = 0
        nearby_done = initialgrid_qs().filter(is_processed=True).count()
        catalogo = GooglePlaceId.objects.count()
        places = Places.objects.count()
        pending = PendingPlace.objects.filter(status="pending").count()

        scan_pendientes = 0
        for p in self._get_pending_points(options).iterator():
            if point_in_scan_areas(p.points.y, p.points.x, area_names):
                scan_pendientes += 1

        tipos = len(VIVE_SEARCH_TYPES)
        llamadas_restantes = scan_pendientes * tipos

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write("📋 ESTADO — Catálogo GooglePlaceId (independiente)")
        self.stdout.write(f"   GooglePlaceId (catálogo):  {catalogo:,}")
        self.stdout.write(f"   Places (sitio):            {places:,}")
        self.stdout.write(f"   PendingPlace (legacy):     {pending:,}")
        self.stdout.write(f"   Grilla total:              {total_grilla:,}")
        self.stdout.write(f"   Text scan hecho:           {text_done:,}")
        self.stdout.write(f"   Nearby scan hecho:         {nearby_done:,}")
        self.stdout.write(f"   Zonas activas:             {', '.join(area_names)}")
        self.stdout.write(f"   Puntos pendientes scan:    {scan_pendientes:,}")
        self.stdout.write(f"   Llamadas API restantes:    ~{llamadas_restantes:,}  (~$0)")
        self.stdout.write(f"   Tipos por punto:           {tipos}")
        if vacios:
            self.stdout.write(self.style.WARNING(f"   Puntos sin IDs (re-scan):  {vacios:,}"))
        if not has_db_text_scan_field():
            self.stdout.write(self.style.WARNING(f"   Progreso en archivo:       {PROGRESS_FILE}"))
        self.stdout.write("")
