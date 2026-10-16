"""
Descubre la mayor cantidad posible de Google Place IDs activos en Medellín.

Estrategia (ver STRATEGIA_NUEVOS_LUGARES.md):

  1. Divide el territorio en comunas/municipios (RegionOSM) × categorías.
  2. Text Search pidiendo solo `places.id` → SKU «IDs Only», gratis e ilimitado.
     Consume las 3 páginas (60 resultados) que permite la API.
  3. Si una consulta se trunca, parte el rectángulo en 4 cuadrantes y reintenta.
  4. Opcionalmente complementa con Nearby Search sobre una malla (de pago).
  5. Todo se deduplica contra GooglePlaceId (place_id UNIQUE).

No pide Place Details ni fotos: el descubrimiento nunca gasta las tarifas caras.

Uso:
  python manage.py discover_medellin_places --status
  python manage.py discover_medellin_places --dry-run
  python manage.py discover_medellin_places
  python manage.py discover_medellin_places --comuna "El Poblado" --limit-tasks 20
  python manage.py discover_medellin_places --nearby --nearby-budget 200
"""

from __future__ import annotations

import signal
import time
from collections import deque
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from explorer.models import (
    GooglePlaceId,
    PlaceDiscoveryRun,
    PlaceDiscoveryTask,
    Places,
)
from explorer.management.commands.scan_nuevos_lugares import INCLUDED_TYPES
from explorer.utils.google_ids_registry import register_google_place_ids
from explorer.utils.google_places import (
    RateLimiter,
    SearchResult,
    nearby_search_ids,
    text_search_ids,
)
from explorer.utils.place_discovery import (
    CATEGORY_GROUPS,
    DEFAULT_CATEGORY_GROUPS,
    BBox,
    TaskSpec,
    categories,
    discovery_areas,
    estimate_api_calls,
    plan_nearby_tasks,
    plan_text_tasks,
)

TEXT_SOURCES = {
    "RELEVANCE": "text_search_relevance",
    "DISTANCE": "text_search_distance",
}
NEARBY_SOURCES = {
    "POPULARITY": "nearby_search_popularity",
    "DISTANCE": "nearby_search_distance",
}
# Nearby Search acepta como máximo 50 valores en includedTypes.
NEARBY_INCLUDED_TYPES = INCLUDED_TYPES[:50]
SEP = "═" * 64


@dataclass
class Job:
    """Tarea lista para ejecutarse en un hilo (sin acceso a la base de datos)."""

    task_id: int
    kind: str
    area_name: str
    area_slug: str
    area_kind: str
    category: str
    included_type: str
    query: str
    rank_preference: str
    bbox: BBox
    depth: int

    def to_spec(self) -> TaskSpec:
        return TaskSpec(
            kind=self.kind,
            area_name=self.area_name,
            area_slug=self.area_slug,
            area_kind=self.area_kind,
            category=self.category,
            included_type=self.included_type,
            query=self.query,
            rank_preference=self.rank_preference,
            bbox=self.bbox,
            depth=self.depth,
        )


@dataclass
class JobResult:
    job: Job
    result: SearchResult | None = None
    error: str = ""


class Command(BaseCommand):
    help = (
        "Descubre Google Place IDs en Medellín por comuna × categoría "
        "(Text Search IDs Only, gratis) con subdivisión automática."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--comuna",
            action="append",
            default=[],
            metavar="NOMBRE",
            help="Limitar a una comuna/municipio (repetible). Ej: --comuna 'El Poblado'",
        )
        parser.add_argument(
            "--municipios",
            action="store_true",
            help="Incluir municipios vecinos (Envigado, Itagüí, Rionegro, Guatapé…)",
        )
        parser.add_argument(
            "--categorias",
            default=",".join(DEFAULT_CATEGORY_GROUPS),
            help=f"Grupos de categorías separados por coma: {', '.join(CATEGORY_GROUPS)}",
        )
        parser.add_argument(
            "--rank",
            default="both",
            choices=("relevance", "distance", "both"),
            help="Orden pedido a Google. 'both' casi duplica los IDs únicos (default)",
        )
        parser.add_argument(
            "--max-depth",
            type=int,
            default=2,
            help="Niveles de subdivisión de una zona saturada (default: 2)",
        )
        parser.add_argument(
            "--workers", type=int, default=4, help="Hilos concurrentes (default: 4)"
        )
        parser.add_argument(
            "--qps",
            type=float,
            default=8.0,
            help="Techo de peticiones por segundo a Google (default: 8)",
        )
        parser.add_argument(
            "--limit-tasks",
            type=int,
            default=0,
            help="Máximo de tareas a ejecutar en esta corrida (0 = todas)",
        )
        parser.add_argument(
            "--timeout", type=int, default=20, help="Timeout HTTP en segundos"
        )
        parser.add_argument(
            "--retries", type=int, default=4, help="Reintentos por error transitorio"
        )
        parser.add_argument(
            "--nearby",
            action="store_true",
            help="Complementar con Nearby Search sobre una malla (SKU Pro, de pago)",
        )
        parser.add_argument(
            "--nearby-radius",
            type=float,
            default=400.0,
            help="Radio de cada celda de la malla Nearby en metros (default: 400)",
        )
        parser.add_argument(
            "--nearby-budget",
            type=int,
            default=500,
            help="Máximo de llamadas Nearby en la corrida (default: 500)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Planificar y estimar sin llamar a Google ni escribir en la BD",
        )
        parser.add_argument(
            "--status", action="store_true", help="Mostrar estado persistido y salir"
        )
        parser.add_argument(
            "--reset", action="store_true", help="Borrar el plan de tareas y replanificar"
        )
        parser.add_argument(
            "--retry-errors",
            action="store_true",
            help="Volver a encolar las tareas que quedaron en error",
        )
        parser.add_argument(
            "--only-saturated",
            action="store_true",
            help=(
                "Ola W4: encolar cuadrantes hijos de tareas saturadas con "
                "depth < --max-depth (sin resetear el plan completo)"
            ),
        )

    # ──────────────────────────────────────────────────────────────
    # Entrada
    # ──────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self.stop_requested = False
        self.verbosity = options.get("verbosity", 1)

        if options["status"]:
            self._print_status()
            return

        groups = tuple(
            part.strip()
            for part in options["categorias"].split(",")
            if part.strip()
        )
        unknown = [group for group in groups if group not in CATEGORY_GROUPS]
        if unknown:
            raise CommandError(
                f"Grupos desconocidos: {', '.join(unknown)}. "
                f"Opciones: {', '.join(CATEGORY_GROUPS)}"
            )

        try:
            areas = discovery_areas(
                comunas=True,
                municipios=options["municipios"],
                only=options["comuna"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        cats = categories(groups)
        if not cats:
            raise CommandError("Ninguna categoría seleccionada.")

        ranks = {
            "relevance": ("RELEVANCE",),
            "distance": ("DISTANCE",),
            "both": ("RELEVANCE", "DISTANCE"),
        }[options["rank"]]

        area_slugs = [area.slug for area in areas]

        if options["only_saturated"]:
            # W4: no replanifica el catálogo completo; solo cuadrantes más profundos.
            parents = PlaceDiscoveryTask.objects.filter(
                area_slug__in=area_slugs,
                kind="text",
                saturated=True,
                status="done",
                depth__lt=options["max_depth"],
            )
            if options["comuna"]:
                pass  # ya filtrado por area_slugs
            self.scope_categories = set(parents.values_list("category", flat=True).distinct())
            if not self.scope_categories:
                # Sin padres saturados aún: alcance vacío pero informativo.
                self.scope_categories = {c.label for c in cats}
            specs = []
            self._print_plan(areas, cats, ranks, specs, options)
            self.stdout.write(
                self.style.WARNING(
                    f"   Modo --only-saturated: padres candidatos={parents.count():,} "
                    f"(depth < {options['max_depth']})"
                )
            )
        else:
            specs = plan_text_tasks(areas, cats, ranks)
            if options["nearby"]:
                specs += plan_nearby_tasks(areas, options["nearby_radius"])
            # Alcance: subtareas heredan categoría del padre.
            self.scope_categories = {spec.category for spec in specs}
            self._print_plan(areas, cats, ranks, specs, options)

        if options["dry_run"]:
            if options["only_saturated"]:
                preview = self._preview_saturated_children(
                    area_slugs, options["max_depth"]
                )
                self.stdout.write(
                    f"   Cuadrantes nuevos estimados: {preview:,}"
                )
            self.stdout.write(
                self.style.WARNING("\n⚠️  DRY RUN — no se llamó a Google ni se escribió nada\n")
            )
            return

        api_key = getattr(settings, "GOOGLE_API_KEY", None)
        if not api_key:
            raise CommandError("GOOGLE_API_KEY no configurada.")

        if options["reset"]:
            # Solo lo que entra en este alcance: un --reset por comuna no debe
            # borrar el progreso de las demás.
            deleted = self._scoped_tasks(area_slugs).delete()[0]
            self.stdout.write(
                self.style.WARNING(f"🗑️  {deleted:,} tareas borradas en este alcance")
            )

        if options["only_saturated"]:
            created = self._enqueue_saturated_children(area_slugs, options["max_depth"])
            self.stdout.write(
                f"🗂️  --only-saturated: {created:,} cuadrantes nuevos encolados"
            )
        else:
            created = self._upsert_tasks(specs)
            self.stdout.write(f"🗂️  Plan: {created:,} tareas nuevas registradas")
        if options["retry_errors"]:
            requeued = self._scoped_tasks(area_slugs).filter(status="error").update(
                status="pending", error_message=""
            )
            self.stdout.write(self.style.WARNING(f"↻ {requeued:,} tareas en error reencoladas"))

        # Tareas que quedaron 'running' vienen de un proceso cortado: se reanudan.
        stale = (
            self._scoped_tasks(area_slugs)
            .filter(status="running")
            .update(status="pending", started_at=None)
        )
        if stale:
            self.stdout.write(self.style.WARNING(f"↻ {stale:,} tareas interrumpidas reanudadas"))

        # Un proceso matado sin darle tiempo a cerrar (kill -9, caída del servidor)
        # deja su corrida abierta para siempre: la damos por interrumpida.
        abandoned = PlaceDiscoveryRun.objects.filter(status="running").update(
            status="interrupted", finished_at=timezone.now()
        )
        if abandoned:
            self.stdout.write(
                self.style.WARNING(f"↻ {abandoned:,} corrida(s) anterior(es) sin cerrar")
            )

        self._execute(api_key, area_slugs, options)

    # ──────────────────────────────────────────────────────────────
    # Planificación
    # ──────────────────────────────────────────────────────────────

    def _upsert_tasks(self, specs: list[TaskSpec]) -> int:
        """Registra el plan sin duplicar: la firma de cada tarea es única."""
        signatures = [spec.signature for spec in specs]
        known = set(
            PlaceDiscoveryTask.objects.filter(signature__in=signatures).values_list(
                "signature", flat=True
            )
        )
        nuevos = [
            PlaceDiscoveryTask(**self._task_kwargs(spec))
            for spec in specs
            if spec.signature not in known
        ]
        if nuevos:
            PlaceDiscoveryTask.objects.bulk_create(
                nuevos, batch_size=500, ignore_conflicts=True
            )
        return len(nuevos)

    def _saturated_parent_qs(self, area_slugs, max_depth: int):
        return PlaceDiscoveryTask.objects.filter(
            area_slug__in=area_slugs,
            kind="text",
            saturated=True,
            status="done",
            depth__lt=max_depth,
        )

    def _child_specs_from_saturated(
        self, area_slugs, max_depth: int
    ) -> list[TaskSpec]:
        """Cuadrantes hijos de tareas saturadas que aún no alcanzaron max_depth."""
        specs: list[TaskSpec] = []
        for task in self._saturated_parent_qs(area_slugs, max_depth).iterator():
            parent = self._job_from_task(task).to_spec()
            for child in parent.children():
                if child.depth <= max_depth:
                    specs.append(child)
        return specs

    def _preview_saturated_children(self, area_slugs, max_depth: int) -> int:
        specs = self._child_specs_from_saturated(area_slugs, max_depth)
        if not specs:
            return 0
        known = set(
            PlaceDiscoveryTask.objects.filter(
                signature__in=[s.signature for s in specs]
            ).values_list("signature", flat=True)
        )
        return sum(1 for s in specs if s.signature not in known)

    def _enqueue_saturated_children(self, area_slugs, max_depth: int) -> int:
        """
        Ola W4: crea tareas pending para cuadrantes de zonas saturadas.
        Amplía scope_categories con las categorías de los hijos.
        """
        specs = self._child_specs_from_saturated(area_slugs, max_depth)
        if specs:
            self.scope_categories |= {s.category for s in specs}
        return self._upsert_tasks(specs)

    def _task_kwargs(self, spec: TaskSpec) -> dict:
        return {
            "signature": spec.signature,
            "kind": spec.kind,
            "area_name": spec.area_name,
            "area_slug": spec.area_slug,
            "area_kind": spec.area_kind,
            "category": spec.category,
            "included_type": spec.included_type,
            "query": spec.query,
            "rank_preference": spec.rank_preference,
            "lat_min": spec.bbox.lat_min,
            "lat_max": spec.bbox.lat_max,
            "lng_min": spec.bbox.lng_min,
            "lng_max": spec.bbox.lng_max,
            "radius_m": spec.bbox.radius_m,
            "depth": spec.depth,
        }

    def _scoped_tasks(self, area_slugs):
        """Tareas que caen dentro del alcance pedido (áreas × categorías)."""
        return PlaceDiscoveryTask.objects.filter(
            area_slug__in=area_slugs, category__in=self.scope_categories
        )

    def _job_from_task(self, task: PlaceDiscoveryTask) -> Job:
        return Job(
            task_id=task.pk,
            kind=task.kind,
            area_name=task.area_name,
            area_slug=task.area_slug,
            area_kind=task.area_kind,
            category=task.category,
            included_type=task.included_type,
            query=task.query,
            rank_preference=task.rank_preference,
            bbox=BBox(task.lat_min, task.lng_min, task.lat_max, task.lng_max),
            depth=task.depth,
        )

    # ──────────────────────────────────────────────────────────────
    # Ejecución concurrente
    # ──────────────────────────────────────────────────────────────

    def _execute(self, api_key: str, area_slugs: list[str], options) -> None:
        limiter = RateLimiter(options["qps"])
        workers = max(1, options["workers"])
        wave_size = workers * 8
        limit_tasks = options["limit_tasks"]
        max_depth = options["max_depth"]
        nearby_budget = options["nearby_budget"] if options["nearby"] else 0

        run = PlaceDiscoveryRun.objects.create(
            params={
                "areas": area_slugs,
                "categorias": options["categorias"],
                "rank": options["rank"],
                "workers": workers,
                "qps": options["qps"],
                "max_depth": max_depth,
                "nearby": bool(options["nearby"]),
                "nearby_budget": nearby_budget,
                "limit_tasks": limit_tasks,
            }
        )
        started = time.monotonic()

        pending: deque[Job] = deque(
            self._job_from_task(task)
            for task in self._scoped_tasks(area_slugs)
            .filter(status="pending")
            .order_by("depth", "id")
        )
        if not pending:
            self.stdout.write(
                self.style.SUCCESS("✅ No hay tareas pendientes. Usa --reset para replanificar.")
            )
            run.status = "done"
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "finished_at"])
            return

        self.stdout.write(
            f"\n🚀 {len(pending):,} tareas pendientes · {workers} hilos · "
            f"{options['qps']:.1f} req/s máx.\n"
        )

        self._install_signal_handlers()
        ids_seen: set[str] = set()
        stats = {
            "tasks_done": 0,
            "tasks_error": 0,
            "api_calls": 0,
            "pages": 0,
            "ids_new": 0,
            "errors": 0,
            "rate_limited": 0,
            "saturated": 0,
            "children": 0,
            "nearby_calls": 0,
        }
        session = requests.Session()
        executed = 0

        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                while pending and not self.stop_requested:
                    wave: list[Job] = []
                    while pending and len(wave) < wave_size:
                        if limit_tasks and executed + len(wave) >= limit_tasks:
                            break
                        job = pending.popleft()
                        if job.kind == "nearby":
                            if stats["nearby_calls"] >= nearby_budget:
                                continue
                            stats["nearby_calls"] += 1
                        wave.append(job)

                    if not wave:
                        break

                    PlaceDiscoveryTask.objects.filter(
                        pk__in=[job.task_id for job in wave]
                    ).update(status="running", started_at=timezone.now())

                    futures = {
                        pool.submit(
                            _run_job,
                            job,
                            api_key=api_key,
                            session=session,
                            limiter=limiter,
                            timeout=options["timeout"],
                            retries=options["retries"],
                        ): job
                        for job in wave
                    }
                    executed += len(wave)

                    for future in as_completed(futures):
                        outcome = future.result()
                        children = self._persist(outcome, ids_seen, stats, max_depth)
                        pending.extend(children)
                        stats["children"] += len(children)
                        self._progress(outcome, stats, len(ids_seen), len(pending))
        finally:
            session.close()
            self._restore_signal_handlers()

        # Lo que quedó marcado como 'running' al cortar vuelve a pendiente.
        reopened = (
            self._scoped_tasks(area_slugs)
            .filter(status="running")
            .update(status="pending", started_at=None)
        )

        duration = time.monotonic() - started
        run.status = "interrupted" if self.stop_requested else "done"
        run.finished_at = timezone.now()
        run.tasks_done = stats["tasks_done"]
        run.tasks_error = stats["tasks_error"]
        run.api_calls = stats["api_calls"]
        run.pages = stats["pages"]
        run.ids_seen = len(ids_seen)
        run.ids_new = stats["ids_new"]
        run.errors = stats["errors"]
        run.rate_limited = stats["rate_limited"]
        run.save()

        self._print_report(run, stats, ids_seen, duration, area_slugs, reopened)

    def _persist(
        self, outcome: JobResult, ids_seen: set[str], stats: dict, max_depth: int
    ) -> list[Job]:
        """Guarda el resultado de una tarea y devuelve las tareas hijas creadas."""
        job = outcome.job
        now = timezone.now()

        if outcome.result is not None:
            stats["api_calls"] += outcome.result.api_calls
            stats["pages"] += outcome.result.pages
            stats["rate_limited"] += outcome.result.rate_limited

        if outcome.error or outcome.result is None:
            stats["tasks_error"] += 1
            stats["errors"] += 1
            PlaceDiscoveryTask.objects.filter(pk=job.task_id).update(
                status="error",
                error_message=(outcome.error or "Sin respuesta de la API")[:500],
                api_calls=outcome.result.api_calls if outcome.result else 0,
                finished_at=now,
                attempts=F("attempts") + 1,
            )
            return []

        result = outcome.result

        source = (
            TEXT_SOURCES.get(job.rank_preference, "text_search_ids")
            if job.kind == "text"
            else NEARBY_SOURCES.get(job.rank_preference, "nearby_search")
        )
        lat, lng = job.bbox.center
        nuevos, _ = register_google_place_ids(
            result.ids,
            scan_lat=lat,
            scan_lng=lng,
            included_type=job.included_type or job.category,
            area_names=[job.area_name],
            source=source,
            query=job.query or f"{job.category} ({job.rank_preference})",
        )
        ids_seen.update(result.ids)
        stats["ids_new"] += nuevos
        stats["tasks_done"] += 1
        if result.truncated:
            stats["saturated"] += 1

        PlaceDiscoveryTask.objects.filter(pk=job.task_id).update(
            status="done",
            ids_found=len(result.ids),
            ids_new=nuevos,
            api_calls=result.api_calls,
            pages=result.pages,
            saturated=result.truncated,
            finished_at=now,
            error_message="",
        )

        if not result.truncated or job.depth >= max_depth:
            return []
        return self._spawn_children(job)

    def _spawn_children(self, job: Job) -> list[Job]:
        """Parte una zona saturada en cuadrantes y los encola."""
        children: list[Job] = []
        parent_spec = job.to_spec()
        for spec in parent_spec.children():
            task, created = PlaceDiscoveryTask.objects.get_or_create(
                signature=spec.signature,
                defaults={**self._task_kwargs(spec), "parent_id": job.task_id},
            )
            if created:
                children.append(self._job_from_task(task))
        return children

    # ──────────────────────────────────────────────────────────────
    # Señales (reanudable)
    # ──────────────────────────────────────────────────────────────

    def _install_signal_handlers(self) -> None:
        self._previous_handlers = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._previous_handlers[sig] = signal.signal(sig, self._on_signal)
            except ValueError:
                # Fuera del hilo principal no se pueden instalar handlers.
                pass

    def _restore_signal_handlers(self) -> None:
        for sig, handler in getattr(self, "_previous_handlers", {}).items():
            try:
                signal.signal(sig, handler)
            except ValueError:
                pass

    def _on_signal(self, signum, frame):  # noqa: ARG002
        if self.stop_requested:
            return
        self.stop_requested = True
        self.stdout.write(
            self.style.WARNING(
                "\n⏸️  Corte solicitado: termino la tanda en curso y guardo el progreso. "
                "Vuelve a ejecutar el comando para reanudar."
            )
        )

    # ──────────────────────────────────────────────────────────────
    # Salida
    # ──────────────────────────────────────────────────────────────

    def _print_plan(self, areas, cats, ranks, specs, options) -> None:
        estimate = estimate_api_calls(specs)
        by_group: dict[str, int] = {}
        for cat in cats:
            by_group[cat.group] = by_group.get(cat.group, 0) + 1

        self.stdout.write(f"\n{SEP}")
        self.stdout.write(self.style.SUCCESS("🔎 DESCUBRIMIENTO DE PLACE IDs — PLAN"))
        self.stdout.write(f"   Áreas:              {len(areas)}")
        self.stdout.write(
            "   Categorías:         "
            + ", ".join(f"{group}={count}" for group, count in sorted(by_group.items()))
            + f" (total {len(cats)})"
        )
        self.stdout.write(f"   Ranking:            {', '.join(ranks)}")
        self.stdout.write(f"   Tareas Text Search: {estimate['text_tasks']:,}")
        self.stdout.write(
            f"   Llamadas estimadas: ~{estimate['text_calls']:,} (SKU IDs Only, $0)"
        )
        if estimate["nearby_tasks"]:
            budget = min(estimate["nearby_tasks"], options["nearby_budget"])
            self.stdout.write(
                self.style.WARNING(
                    f"   Malla Nearby:       {estimate['nearby_tasks']:,} celdas, "
                    f"tope {budget:,} llamadas (Nearby Pro: 5.000 gratis/mes, luego ~$32/1.000)"
                )
            )
        self.stdout.write(
            f"   Subdivisión:        hasta {options['max_depth']} niveles en zonas saturadas"
        )
        self.stdout.write(f"   Catálogo actual:    {GooglePlaceId.objects.count():,} place_id")

        if self.verbosity > 1:
            self.stdout.write("\n   Áreas incluidas:")
            for area in areas:
                lat, lng = area.bbox.center
                self.stdout.write(
                    f"     · {area.name} ({area.kind}) "
                    f"centro {lat:.4f},{lng:.4f} radio ~{area.bbox.radius_m:.0f} m"
                )

    def _progress(self, outcome: JobResult, stats: dict, unique: int, pending: int) -> None:
        if self.verbosity < 1:
            return
        job = outcome.job
        label = f"{job.area_name}/{job.category}"
        if job.depth:
            label += f" d{job.depth}"
        if outcome.error:
            self.stdout.write(self.style.ERROR(f"   ✗ {label}: {outcome.error}"))
            return
        if self.verbosity > 1 or (stats["tasks_done"] % 25 == 0):
            found = len(outcome.result.ids) if outcome.result else 0
            flag = " ⧉" if outcome.result and outcome.result.truncated else ""
            self.stdout.write(
                f"   ✓ [{stats['tasks_done']:,}] {label}: {found} ids{flag} · "
                f"únicos {unique:,} · nuevos {stats['ids_new']:,} · cola {pending:,}"
            )

    def _print_report(
        self, run, stats: dict, ids_seen: set[str], duration: float, area_slugs, reopened: int
    ) -> None:
        self.stdout.write(f"\n{SEP}")
        title = "📊 RESUMEN" + (" (INTERRUMPIDO)" if self.stop_requested else "")
        self.stdout.write(self.style.SUCCESS(title))
        self.stdout.write(f"   IDs únicos encontrados:  {len(ids_seen):,}")
        self.stdout.write(self.style.SUCCESS(f"   IDs nuevos en catálogo:  {stats['ids_new']:,}"))
        self.stdout.write(f"   Consultas a Google:      {stats['api_calls']:,}")
        self.stdout.write(f"   Páginas consumidas:      {stats['pages']:,}")
        self.stdout.write(f"   Tareas completadas:      {stats['tasks_done']:,}")
        self.stdout.write(f"   Zonas saturadas:         {stats['saturated']:,}")
        self.stdout.write(f"   Subtareas generadas:     {stats['children']:,}")
        self.stdout.write(f"   Errores:                 {stats['errors']:,}")
        if stats["rate_limited"]:
            self.stdout.write(
                self.style.WARNING(f"   HTTP 429 recibidos:      {stats['rate_limited']:,}")
            )
        if stats["nearby_calls"]:
            self.stdout.write(
                self.style.WARNING(f"   Llamadas Nearby (pago):  {stats['nearby_calls']:,}")
            )
        self.stdout.write(f"   Duración:                {_fmt_duration(duration)}")
        if stats["api_calls"]:
            self.stdout.write(
                f"   Ritmo:                   {stats['api_calls'] / max(duration, 1):.1f} req/s"
            )

        self._print_coverage(area_slugs)

        catalogo = GooglePlaceId.objects.count()
        publicados = Places.objects.count()
        sin_publicar = catalogo - publicados
        self.stdout.write(f"\n   📚 Catálogo GooglePlaceId: {catalogo:,}")
        self.stdout.write(f"   🌐 Publicados en Places:   {publicados:,}")
        self.stdout.write(f"   🎯 Inéditos por enriquecer: {sin_publicar:,}")

        scoped = self._scoped_tasks(area_slugs)
        restantes = scoped.filter(status="pending").count()
        errores = scoped.filter(status="error").count()
        if restantes:
            self.stdout.write(
                self.style.WARNING(
                    f"\n   ⏳ {restantes:,} tareas pendientes"
                    + (f" ({reopened:,} reabiertas al cortar)" if reopened else "")
                )
            )
            self.stdout.write("   → python manage.py discover_medellin_places   (reanuda)")
        if errores:
            self.stdout.write(
                self.style.WARNING(f"   ⚠️  {errores:,} tareas en error")
            )
            self.stdout.write(
                "   → python manage.py discover_medellin_places --retry-errors"
            )
        self.stdout.write("")

    def _print_coverage(self, area_slugs) -> None:
        """Cobertura por comuna y por categoría, leída de las tareas guardadas."""
        base = self._scoped_tasks(area_slugs)

        by_area = (
            base.values("area_name")
            .annotate(
                tareas=Count("id"),
                hechas=Count("id", filter=Q(status="done")),
                ids=Sum("ids_found"),
                nuevos=Sum("ids_new"),
                saturadas=Count("id", filter=Q(saturated=True)),
            )
            .order_by("-nuevos")
        )
        if by_area:
            self.stdout.write("\n   Cobertura por comuna/municipio:")
            self.stdout.write(
                f"   {'ÁREA':<28}{'HECHAS':>10}{'DEVUELTOS':>12}{'NUEVOS':>9}{'SATUR.':>8}"
            )
            for row in by_area:
                self.stdout.write(
                    f"   {row['area_name'][:27]:<28}"
                    f"{row['hechas']:>5}/{row['tareas']:<4}"
                    f"{(row['ids'] or 0):>12,}"
                    f"{(row['nuevos'] or 0):>9,}"
                    f"{row['saturadas']:>8,}"
                )

        by_cat = (
            base.exclude(ids_new=0)
            .values("category")
            .annotate(ids=Sum("ids_found"), nuevos=Sum("ids_new"))
            .order_by("-nuevos")[:15]
        )
        if by_cat:
            self.stdout.write("\n   Top categorías por IDs nuevos:")
            for row in by_cat:
                self.stdout.write(
                    f"   {row['category'][:34]:<35}"
                    f"{(row['ids'] or 0):>10,} ids"
                    f"{(row['nuevos'] or 0):>9,} nuevos"
                )

    def _print_status(self) -> None:
        self.stdout.write(f"\n{SEP}")
        self.stdout.write(self.style.SUCCESS("📋 ESTADO DEL DESCUBRIMIENTO"))

        total = PlaceDiscoveryTask.objects.count()
        if not total:
            self.stdout.write("   Sin plan de tareas todavía.")
            self.stdout.write("   → python manage.py discover_medellin_places --dry-run")
        else:
            by_status = {
                row["status"]: row["n"]
                for row in PlaceDiscoveryTask.objects.values("status").annotate(
                    n=Count("id")
                )
            }
            self.stdout.write(f"   Tareas totales:      {total:,}")
            for status in ("pending", "running", "done", "error"):
                self.stdout.write(f"     {status:<10} {by_status.get(status, 0):,}")
            agg = PlaceDiscoveryTask.objects.aggregate(
                ids=Sum("ids_found"), nuevos=Sum("ids_new"), calls=Sum("api_calls")
            )
            self.stdout.write(f"   IDs devueltos:       {(agg['ids'] or 0):,}")
            self.stdout.write(f"   IDs nuevos:          {(agg['nuevos'] or 0):,}")
            self.stdout.write(f"   Llamadas API:        {(agg['calls'] or 0):,}")
            self.stdout.write(
                f"   Zonas saturadas:     "
                f"{PlaceDiscoveryTask.objects.filter(saturated=True).count():,}"
            )
            self.stdout.write(
                f"   Profundidad máxima:  "
                f"{PlaceDiscoveryTask.objects.order_by('-depth').values_list('depth', flat=True).first() or 0}"
            )

        try:
            areas = discovery_areas(municipios=True)
            comunas = [area for area in areas if area.kind == "comuna"]
            municipios = [area for area in areas if area.kind == "municipio"]
            self.stdout.write(
                f"\n   Áreas disponibles:   {len(comunas)} comunas + {len(municipios)} municipios"
            )
            self.stdout.write(
                "     " + ", ".join(area.name for area in comunas[:20])
            )
            if municipios:
                self.stdout.write("     " + ", ".join(area.name for area in municipios))
        except ValueError:
            pass

        self.stdout.write(f"\n   Catálogo GooglePlaceId: {GooglePlaceId.objects.count():,}")
        self.stdout.write(f"   Places publicados:      {Places.objects.count():,}")

        ultimo = PlaceDiscoveryRun.objects.first()
        if ultimo:
            self.stdout.write(
                f"\n   Última corrida:      #{ultimo.pk} {ultimo.status} · "
                f"{ultimo.ids_new:,} nuevos · {ultimo.api_calls:,} llamadas · "
                f"{_fmt_duration(ultimo.duration_s)}"
            )
        self.stdout.write("")


# ──────────────────────────────────────────────────────────────────
# Worker: se ejecuta en hilos, sin tocar la base de datos
# ──────────────────────────────────────────────────────────────────

def _run_job(
    job: Job,
    *,
    api_key: str,
    session: requests.Session,
    limiter: RateLimiter,
    timeout: int,
    retries: int,
) -> JobResult:
    try:
        if job.kind == "text":
            result = text_search_ids(
                api_key,
                job.query,
                included_type=job.included_type or None,
                rectangle=job.bbox.as_tuple(),
                rank_preference=job.rank_preference or None,
                timeout=timeout,
                retries=retries,
                rate_limiter=limiter,
                session=session,
            )
        else:
            lat, lng = job.bbox.center
            result = nearby_search_ids(
                api_key,
                lat,
                lng,
                job.bbox.radius_m,
                included_types=NEARBY_INCLUDED_TYPES,
                rank_preference=job.rank_preference or "POPULARITY",
                timeout=timeout,
                retries=retries,
                rate_limiter=limiter,
                session=session,
            )
        return JobResult(job, result)
    except Exception as exc:  # noqa: BLE001 - el error se reporta por tarea
        # El resultado parcial trae las llamadas que sí alcanzaron a hacerse.
        return JobResult(job, getattr(exc, "search_result", None), _describe_error(exc))


def _describe_error(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if response is not None:
        detail = ""
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            detail = (response.text or "")[:200]
        return f"HTTP {response.status_code}: {detail[:300]}"
    return f"{type(exc).__name__}: {exc}"[:300]


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
