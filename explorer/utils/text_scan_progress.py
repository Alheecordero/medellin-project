"""Progreso del scan Text Search cuando falta la columna is_text_scan_processed en BD."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

PROGRESS_FILE = Path(settings.BASE_DIR) / "data" / "text_scan_progress.txt"
_HAS_TEXT_SCAN_FIELD: bool | None = None
_INITIALGRID_DB_COLUMNS: set[str] | None = None

SCAN_DB_FIELDS = (
    "is_text_scan_processed",
    "google_ids_places",
    "text_scan_passes",
)


def initialgrid_db_columns() -> set[str]:
    """Columnas reales de Initialgrid, incluso con migraciones sin aplicar."""
    global _INITIALGRID_DB_COLUMNS
    if _INITIALGRID_DB_COLUMNS is not None:
        return _INITIALGRID_DB_COLUMNS

    from django.db import connection
    from explorer.models import Initialgrid

    try:
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(
                cursor, Initialgrid._meta.db_table
            )
        _INITIALGRID_DB_COLUMNS = {column.name for column in description}
    except Exception:
        _INITIALGRID_DB_COLUMNS = set()
    return _INITIALGRID_DB_COLUMNS


def has_db_text_scan_field() -> bool:
    """True solo si la columna existe en PostgreSQL (no basta con el modelo Django)."""
    global _HAS_TEXT_SCAN_FIELD
    if _HAS_TEXT_SCAN_FIELD is not None:
        return _HAS_TEXT_SCAN_FIELD

    _HAS_TEXT_SCAN_FIELD = "is_text_scan_processed" in initialgrid_db_columns()
    return _HAS_TEXT_SCAN_FIELD


def load_progress_ids() -> set[int]:
    if not PROGRESS_FILE.exists():
        return set()
    done: set[int] = set()
    for line in PROGRESS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.isdigit():
            done.add(int(line))
    return done


def mark_done(punto_id: int) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{punto_id}\n")


def reset_progress() -> int:
    if PROGRESS_FILE.exists():
        count = len(load_progress_ids())
        PROGRESS_FILE.unlink()
        return count
    return 0


def initialgrid_qs():
    """QuerySet seguro cuando la migración 0030 aún no está aplicada."""
    from explorer.models import Initialgrid

    qs = Initialgrid.objects.all()
    missing = [field for field in SCAN_DB_FIELDS if field not in initialgrid_db_columns()]
    if missing:
        qs = qs.defer(*missing)
    return qs


def create_grid_points_bulk(coords: list[tuple[float, float]]) -> int:
    """Inserta muchos puntos (lng, lat). Devuelve cantidad insertada."""
    if not coords:
        return 0

    from django.contrib.gis.geos import Point
    from django.db import connection
    from django.utils import timezone
    from explorer.models import Initialgrid

    now = timezone.now()

    if has_db_text_scan_field():
        objs = [
            Initialgrid(
                points=Point(lng, lat, srid=4326),
                is_processed=False,
                is_text_scan_processed=False,
            )
            for lng, lat in coords
        ]
        Initialgrid.objects.bulk_create(objs, batch_size=200)
        return len(objs)

    rows = [(Point(lng, lat, srid=4326).ewkb, False, now) for lng, lat in coords]
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO explorer_initialgrid (points, is_processed, fecha_creacion)
            VALUES (ST_GeomFromEWKB(%s), %s, %s)
            """,
            rows,
        )
    return len(rows)


def create_grid_point(lng: float, lat: float) -> None:
    create_grid_points_bulk([(lng, lat)])


def count_progress() -> int:
    return len(load_progress_ids())
