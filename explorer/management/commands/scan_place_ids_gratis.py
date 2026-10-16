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
    initialgrid_db_columns,
    initialgrid_qs,
    load_progress_ids,
    mark_done,
    reset_progress,
)
from explorer.utils.vive_areas import (
    GENERIC_SEARCH_QUERIES,
    VIVE_SEARCH_TYPES,
    VIVE_SEARCH_TYPES_HIGH_YIELD,
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
            "--rate-limit-sleep",
            type=float,
            default=120.0,
            help="Pausa en segundos tras 429 antes de pasar al siguiente punto (default: 120)",
        )
        parser.add_argument(
            "--high-yield-only",
            action="store_true",
            help="Solo 14 tipos clave (menos llamadas, ~85%% cobertura)",
        )
        parser.add_argument(
            "--skip-after-ids",
            type=int,
            default=0,
            help="Tras acumular N IDs en un punto, saltar tipos restantes (ej: 50)",
        )
        parser.add_argument(
            "--fast",
            action="store_true",
            help="Atajo: --high-yield-only --pause 5 --skip-after-ids 50",
        )
        parser.add_argument(
            "--turbo",
            action="store_true",
            help="Atajo: --high-yield-only --pause 3 --skip-after-ids 60",
        )
        parser.add_argument(
            "--smart",
            action="store_true",
            help="Turbo + omitir pasadas 2A/2B en puntos ya saturados (>=50 IDs guardados)",
        )
        parser.add_argument(
            "--solo-huecos",
            action="store_true",
            help="Solo puntos con google_ids_places vacío (sub-grilla / huecos)",
        )
        parser.add_argument(
            "--auto-skip-saturated",
            action="store_true",
            help="En restriction/generico, marcar hecho sin API si el punto ya tiene muchos IDs",
        )
        parser.add_argument(
            "--saturated-threshold",
            type=int,
            default=50,
            help="Umbral de IDs guardados para --auto-skip-saturated (default: 50)",
        )
        parser.add_argument(
            "--max-stored-ids",
            type=int,
            default=0,
            help="Solo puntos con menos de N IDs en google_ids_places (0 = sin filtro)",
        )
        parser.add_argument(
            "--skip-if-page-full",
            action="store_true",
            help="Si una llamada devuelve 60 IDs (tope Google), omitir tipos restantes",
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
                columns = initialgrid_db_columns()
                updates = {"is_text_scan_processed": False}
                if "google_ids_places" in columns:
                    updates["google_ids_places"] = []
                if "text_scan_passes" in columns:
                    updates["text_scan_passes"] = []
                n = initialgrid_qs().filter(is_text_scan_processed=True).update(**updates)
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

        if options["smart"]:
            options["auto_skip_saturated"] = True
            options["high_yield_only"] = True
            options["skip_after_ids"] = options["skip_after_ids"] or 50
            options["skip_if_page_full"] = True
            if options["pause"] == 0.25:
                options["pause"] = 2.0
            if options["radio"] == 600.0 and options.get("solo_huecos"):
                options["radio"] = 350.0
        elif options["turbo"]:
            options["high_yield_only"] = True
            options["skip_after_ids"] = options["skip_after_ids"] or 60
            options["skip_if_page_full"] = True
            if options["pause"] == 0.25:
                options["pause"] = 3.0
        elif options["fast"]:
            options["high_yield_only"] = True
            options["skip_after_ids"] = options["skip_after_ids"] or 50
            if options["pause"] == 0.25:
                options["pause"] = 5.0

        search_types = self._search_types_for_pasada(
            options["pasada"], high_yield_only=options["high_yield_only"]
        )
        if options["limit_tipos"] > 0:
            search_types = search_types[: options["limit_tipos"]]

        pasada = options["pasada"]
        use_restriction = pasada in ("restriction", "generico")
        source = PASADA_SOURCES[pasada]

        puntos = self._get_pending_points(options)
        puntos = self._filter_by_stored_ids(puntos, options)
        puntos = self._filter_solo_huecos(puntos, options)
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
        rate_limit_sleep = options["rate_limit_sleep"]
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
        if options["high_yield_only"]:
            self.stdout.write("   Modo:               high-yield (14 tipos clave)")
        if options["skip_after_ids"]:
            self.stdout.write(f"   Skip tras IDs:      {options['skip_after_ids']}")
        if options.get("auto_skip_saturated"):
            self.stdout.write(
                f"   Skip saturados:     ≥{options['saturated_threshold']} IDs guardados"
            )
        if options.get("max_stored_ids"):
            self.stdout.write(f"   Máx IDs guardados:  <{options['max_stored_ids']}")
        if options.get("solo_huecos"):
            self.stdout.write("   Modo:               solo huecos (0 IDs guardados)")
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
            "puntos_omitidos_saturados": 0,
        }

        for i, punto in enumerate(puntos, 1):
            lat, lng = punto.points.y, punto.points.x
            zonas_punto = areas_for_point(lat, lng, self.area_names)
            stored_count = self._stored_ids_count(punto)
            if (
                options.get("auto_skip_saturated")
                and pasada in ("restriction", "generico")
                and stored_count >= options.get("saturated_threshold", 50)
            ):
                self._mark_point_done(punto, None, pasada)
                stats["puntos"] += 1
                stats["puntos_omitidos_saturados"] += 1
                if i <= 3 or i % 250 == 0 or i == total_puntos:
                    self.stdout.write(
                        f"\n📍 [{i}/{total_puntos}] Punto {punto.id} — "
                        f"⏭ saturado ({stored_count} IDs), {pasada} sin API"
                    )
                continue

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
                    if (
                        isinstance(exc, requests.HTTPError)
                        and exc.response is not None
                        and exc.response.status_code == 429
                    ):
                        retry_after = exc.response.headers.get("Retry-After")
                        wait_s = rate_limit_sleep
                        if retry_after:
                            try:
                                wait_s = max(wait_s, float(retry_after))
                            except ValueError:
                                pass
                        self.stdout.write(
                            self.style.WARNING(
                                f"   ⏸ Rate limit 429: pausa {wait_s:.0f}s y se salta el resto del punto"
                            )
                        )
                        time.sleep(wait_s)
                        break
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

                skip_after_ids = options.get("skip_after_ids") or 0
                if skip_after_ids and len(ids_en_punto) >= skip_after_ids:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"   ⏭ Punto saturado ({len(ids_en_punto)} IDs), tipos restantes omitidos"
                        )
                    )
                    break
                if options.get("skip_if_page_full") and len(found) >= 60:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "   ⏭ Página llena (60 IDs), tipos restantes omitidos"
                        )
                    )
                    break

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

    def _search_types_for_pasada(
        self, pasada: str, *, high_yield_only: bool = False
    ) -> list[tuple[str, str]]:
        if pasada == "generico":
            return [(q, "") for q in GENERIC_SEARCH_QUERIES]
        if high_yield_only:
            return list(VIVE_SEARCH_TYPES_HIGH_YIELD)
        return list(VIVE_SEARCH_TYPES)

    def _get_pending_points(self, options):
        pasada = options.get("pasada", "bias")
        qs = initialgrid_qs().order_by("id")
        if options["rescan_vacios"]:
            if has_db_text_scan_field() and "google_ids_places" in initialgrid_db_columns():
                return qs.filter(is_text_scan_processed=True, google_ids_places=[])
            self.stdout.write(
                self.style.WARNING("   --rescan-vacios requiere migración 0031 (google_ids_places)")
            )
        columns = initialgrid_db_columns()
        if pasada == "bias":
            # Pendientes = sin pasada bias en text_scan_passes (no solo el flag booleano:
            # puntos marcados processed por otras pasadas quedaban fuera y no se
            # volvían a barrer).
            if "text_scan_passes" in columns:
                return qs.exclude(text_scan_passes__contains=["bias"])
            if has_db_text_scan_field():
                return qs.filter(is_text_scan_processed=False)
            done = load_progress_ids()
            if done:
                return qs.exclude(id__in=done)
            return qs
        if "text_scan_passes" not in columns:
            raise CommandError(
                f"La pasada {pasada} requiere la columna text_scan_passes (migración 0033)."
            )
        # restriction / generico: bias hecho, esta pasada pendiente
        return qs.filter(text_scan_passes__contains=["bias"]).exclude(
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

    def _stored_ids_count(self, punto) -> int:
        if "google_ids_places" not in initialgrid_db_columns():
            return 0
        return len(punto.google_ids_places or [])

    def _filter_by_stored_ids(self, qs, options):
        max_stored = options.get("max_stored_ids") or 0
        if max_stored <= 0 or "google_ids_places" not in initialgrid_db_columns():
            return qs
        ids_ok = [
            p.id
            for p in qs.iterator()
            if len(p.google_ids_places or []) < max_stored
        ]
        return initialgrid_qs().filter(id__in=ids_ok).order_by("id")

    def _filter_solo_huecos(self, qs, options):
        if not options.get("solo_huecos"):
            return qs
        if "google_ids_places" not in initialgrid_db_columns():
            self.stdout.write(
                self.style.WARNING("   --solo-huecos requiere columna google_ids_places")
            )
            return qs
        return qs.filter(google_ids_places=[])

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
            columns = initialgrid_db_columns()
            update_fields = []
            if "text_scan_passes" in columns:
                passes = list(punto.text_scan_passes or [])
                if pasada not in passes:
                    passes.append(pasada)
                punto.text_scan_passes = passes
                update_fields.append("text_scan_passes")
            if pasada == "bias":
                punto.is_text_scan_processed = True
                update_fields.append("is_text_scan_processed")
            if google_ids_places is not None and "google_ids_places" in columns:
                if pasada == "bias":
                    punto.google_ids_places = google_ids_places
                else:
                    merged = sorted(set(punto.google_ids_places or []) | set(google_ids_places))
                    punto.google_ids_places = merged
                update_fields.append("google_ids_places")
            if update_fields:
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
        if stats.get("puntos_omitidos_saturados"):
            self.stdout.write(
                f"   Puntos saturados (sin API): {stats['puntos_omitidos_saturados']:,}"
            )

        catalogo = GooglePlaceId.objects.count()
        pendientes_grilla = self._count_pending_points(options)
        vacios = 0
        if has_db_text_scan_field() and "google_ids_places" in initialgrid_db_columns():
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
            if "google_ids_places" in initialgrid_db_columns():
                vacios = initialgrid_qs().filter(
                    is_text_scan_processed=True, google_ids_places=[]
                ).count()
            else:
                vacios = 0
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
