"""
Planificación del barrido de descubrimiento de Google Place IDs.

Divide el territorio en áreas (comunas de Medellín y municipios vecinos, tomadas
de RegionOSM) y las cruza con categorías de búsqueda para generar tareas
idempotentes. Cada tarea es un rectángulo + una consulta; si Google la trunca,
el rectángulo se parte en cuadrantes y se vuelve a consultar.

No hace llamadas HTTP ni escribe en la base: solo produce `TaskSpec`.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace

from explorer.utils.google_places import meters_to_deg_lat, meters_to_deg_lng
from explorer.utils.vive_areas import (
    CUISINE_SEARCH_TYPES,
    GENERIC_SEARCH_QUERIES,
    SCAN_AREAS,
    VIVE_SEARCH_TYPES,
)

CATEGORY_GROUPS = ("base", "cocina", "generico")
DEFAULT_CITY = "Medellín"
COMUNA_ADMIN_LEVEL = "8"
MUNICIPIO_ADMIN_LEVEL = "6"

# Cuadrantes de una tarea saturada: 2×2 sobre el rectángulo.
SUBDIVISION_FACTOR = 2


@dataclass(frozen=True)
class BBox:
    """Rectángulo lat/lng en EPSG:4326."""

    lat_min: float
    lng_min: float
    lat_max: float
    lng_max: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.lat_min + self.lat_max) / 2, (self.lng_min + self.lng_max) / 2)

    @property
    def radius_m(self) -> float:
        """Radio del círculo que encierra el rectángulo (media diagonal)."""
        lat, _ = self.center
        dlat_m = (self.lat_max - self.lat_min) / 2 * 111_320.0
        dlng_m = (self.lng_max - self.lng_min) / 2 * 111_320.0 * math.cos(math.radians(lat))
        return math.hypot(dlat_m, dlng_m)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.lat_min, self.lng_min, self.lat_max, self.lng_max)

    def quadrants(self) -> list["BBox"]:
        mid_lat = (self.lat_min + self.lat_max) / 2
        mid_lng = (self.lng_min + self.lng_max) / 2
        return [
            BBox(self.lat_min, self.lng_min, mid_lat, mid_lng),
            BBox(self.lat_min, mid_lng, mid_lat, self.lng_max),
            BBox(mid_lat, self.lng_min, self.lat_max, mid_lng),
            BBox(mid_lat, mid_lng, self.lat_max, self.lng_max),
        ]

    def grid(self, cell_radius_m: float) -> list["BBox"]:
        """Malla de celdas cuyo círculo circunscrito mide `cell_radius_m`."""
        lat, _ = self.center
        # Lado de la celda tal que su media diagonal sea el radio pedido.
        side_m = max(50.0, cell_radius_m * math.sqrt(2))
        step_lat = meters_to_deg_lat(side_m)
        step_lng = meters_to_deg_lng(side_m, lat)

        cells: list[BBox] = []
        y = self.lat_min
        while y < self.lat_max:
            x = self.lng_min
            while x < self.lng_max:
                cells.append(
                    BBox(y, x, min(y + step_lat, self.lat_max), min(x + step_lng, self.lng_max))
                )
                x += step_lng
            y += step_lat
        return cells


@dataclass(frozen=True)
class DiscoveryArea:
    """Comuna, barrio o municipio sobre el que se planifica el barrido."""

    name: str
    slug: str
    kind: str
    bbox: BBox
    osm_id: int | None = None
    geom: object | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class Category:
    """Categoría de búsqueda: texto de consulta + includedType de Google."""

    label: str
    included_type: str
    group: str


@dataclass(frozen=True)
class TaskSpec:
    """Unidad de trabajo: una consulta sobre un rectángulo."""

    kind: str
    area_name: str
    area_slug: str
    area_kind: str
    category: str
    included_type: str
    query: str
    rank_preference: str
    bbox: BBox
    depth: int = 0

    @property
    def signature(self) -> str:
        raw = "|".join(
            [
                self.kind,
                self.area_slug,
                self.included_type,
                self.query,
                self.rank_preference,
                f"{self.bbox.lat_min:.6f}",
                f"{self.bbox.lng_min:.6f}",
                f"{self.bbox.lat_max:.6f}",
                f"{self.bbox.lng_max:.6f}",
            ]
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def children(self) -> list["TaskSpec"]:
        """Cuadrantes de esta tarea, para cuando Google trunca los resultados."""
        return [
            replace(self, bbox=quad, depth=self.depth + 1) for quad in self.bbox.quadrants()
        ]


def bbox_from_geometry(geom) -> BBox:
    """BBox a partir de una geometría GEOS (usa su extent)."""
    lng_min, lat_min, lng_max, lat_max = geom.extent
    return BBox(lat_min, lng_min, lat_max, lng_max)


def bbox_from_scan_area(bounds: dict) -> BBox:
    return BBox(
        bounds["lat_min"], bounds["lng_min"], bounds["lat_max"], bounds["lng_max"]
    )


def discovery_areas(
    *,
    comunas: bool = True,
    municipios: bool = False,
    only: tuple[str, ...] | list[str] = (),
    ciudad: str = DEFAULT_CITY,
) -> list[DiscoveryArea]:
    """
    Áreas del barrido tomadas de RegionOSM (comunas admin_level=8 de Medellín y
    municipios admin_level=6). Si no hay regiones cargadas cae a SCAN_AREAS.

    `only` filtra por nombre o slug, sin distinguir mayúsculas.
    """
    from explorer.models import RegionOSM

    wanted_levels: list[str] = []
    if comunas:
        wanted_levels.append(COMUNA_ADMIN_LEVEL)
    if municipios:
        wanted_levels.append(MUNICIPIO_ADMIN_LEVEL)

    areas: list[DiscoveryArea] = []
    if wanted_levels:
        qs = RegionOSM.objects.filter(
            admin_level__in=wanted_levels, geom_4326__isnull=False
        ).order_by("name")
        if comunas and not municipios and ciudad:
            qs = qs.filter(ciudad=ciudad)
        for region in qs:
            if not region.name:
                continue
            kind = "comuna" if region.admin_level == COMUNA_ADMIN_LEVEL else "municipio"
            areas.append(
                DiscoveryArea(
                    name=region.name,
                    slug=region.slug or f"osm-{region.osm_id}",
                    kind=kind,
                    bbox=bbox_from_geometry(region.geom_4326),
                    osm_id=region.osm_id,
                    geom=region.geom_4326,
                )
            )

    if not areas:
        # Sin RegionOSM usable: los bounding boxes estáticos cubren lo mismo.
        for name, bounds in SCAN_AREAS.items():
            areas.append(
                DiscoveryArea(
                    name=name,
                    slug=_slug(name),
                    kind="bbox",
                    bbox=bbox_from_scan_area(bounds),
                )
            )

    if only:
        wanted = {value.strip().lower() for value in only if value.strip()}
        areas = [
            area
            for area in areas
            if area.name.lower() in wanted or area.slug.lower() in wanted
        ]
        if not areas:
            raise ValueError(
                f"Ninguna área coincide con {sorted(wanted)}. "
                "Usa --status para ver las disponibles."
            )
    return areas


def categories(groups: tuple[str, ...] | list[str] = CATEGORY_GROUPS) -> list[Category]:
    """Categorías de búsqueda por grupo: base, cocina y genérico."""
    selected: list[Category] = []
    groups = tuple(groups)

    if "base" in groups:
        for label, included_type in VIVE_SEARCH_TYPES:
            selected.append(Category(label, included_type, "base"))
    if "cocina" in groups:
        for label, included_type in CUISINE_SEARCH_TYPES:
            selected.append(Category(label, included_type, "cocina"))
    if "generico" in groups:
        for label in GENERIC_SEARCH_QUERIES:
            selected.append(Category(label, "", "generico"))

    # Un mismo includedType puede repetirse con distinto texto (ej. bar/rooftop):
    # eso es deseado, pero no queremos la misma pareja dos veces.
    seen: set[tuple[str, str]] = set()
    unique: list[Category] = []
    for cat in selected:
        key = (cat.label, cat.included_type)
        if key not in seen:
            seen.add(key)
            unique.append(cat)
    return unique


def build_query(category: Category, area: DiscoveryArea) -> str:
    """
    Consulta de texto anclada al área.

    Nombrar la zona es lo que permite pasar del techo de 60 resultados por
    consulta: cada comuna devuelve su propio conjunto.
    """
    if area.kind == "comuna":
        return f"{category.label} en {area.name}, {DEFAULT_CITY}"[:200]
    return f"{category.label} en {area.name}, Antioquia"[:200]


def plan_text_tasks(
    areas: list[DiscoveryArea],
    cats: list[Category],
    ranks: tuple[str, ...] | list[str] = ("RELEVANCE", "DISTANCE"),
) -> list[TaskSpec]:
    """Una tarea Text Search por área × categoría × orden de ranking."""
    specs: list[TaskSpec] = []
    for area in areas:
        for cat in cats:
            query = build_query(cat, area)
            for rank in ranks:
                specs.append(
                    TaskSpec(
                        kind="text",
                        area_name=area.name,
                        area_slug=area.slug,
                        area_kind=area.kind,
                        category=cat.label,
                        included_type=cat.included_type,
                        query=query,
                        rank_preference=rank,
                        bbox=area.bbox,
                    )
                )
    return specs


def plan_nearby_tasks(
    areas: list[DiscoveryArea],
    cell_radius_m: float = 400.0,
    rank_preference: str = "POPULARITY",
) -> list[TaskSpec]:
    """
    Malla de círculos que cubre cada área, para complementar Text Search.

    Las celdas que no tocan el polígono de la comuna se descartan, así no se
    pagan llamadas sobre zonas fuera del área.
    """
    specs: list[TaskSpec] = []
    for area in areas:
        for cell in area.bbox.grid(cell_radius_m):
            if area.geom is not None and not _cell_touches(area.geom, cell):
                continue
            specs.append(
                TaskSpec(
                    kind="nearby",
                    area_name=area.name,
                    area_slug=area.slug,
                    area_kind=area.kind,
                    category="malla",
                    included_type="",
                    query="",
                    rank_preference=rank_preference,
                    bbox=cell,
                )
            )
    return specs


def _cell_touches(geom, cell: BBox) -> bool:
    from django.contrib.gis.geos import Polygon

    rect = Polygon.from_bbox((cell.lng_min, cell.lat_min, cell.lng_max, cell.lat_max))
    rect.srid = 4326
    try:
        return geom.intersects(rect)
    except Exception:
        return True


def _slug(value: str) -> str:
    from django.utils.text import slugify

    return slugify(value) or "area"


def estimate_api_calls(specs: list[TaskSpec], pages_per_text_task: int = 2) -> dict[str, int]:
    """
    Llamadas estimadas por tipo de búsqueda.

    `pages_per_text_task` es un promedio: una consulta con pocos resultados gasta
    una página, una saturada gasta las 3 que permite la API.
    """
    text = sum(1 for spec in specs if spec.kind == "text")
    nearby = sum(1 for spec in specs if spec.kind == "nearby")
    return {
        "text_tasks": text,
        "text_calls": text * pages_per_text_task,
        "nearby_tasks": nearby,
        "nearby_calls": nearby,
    }
