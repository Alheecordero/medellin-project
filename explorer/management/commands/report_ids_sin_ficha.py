"""
Reporte permanente de Google Place IDs del catálogo que aún no tienen ficha
en Places (sin nombre, fotos ni Place Details).

Uso:
  python manage.py report_ids_sin_ficha
  python manage.py report_ids_sin_ficha --por-area
  python manage.py report_ids_sin_ficha --export data/ids_sin_ficha.txt
  python manage.py report_ids_sin_ficha --area "Envigado" --export /tmp/env.txt
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from explorer.models import GooglePlaceDetails, GooglePlaceId, Places


SEP = "═" * 60


class Command(BaseCommand):
    help = (
        "Lista y resume los GooglePlaceId que no tienen ficha en Places "
        "(cola de enriquecimiento)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--por-area",
            action="store_true",
            help="Desglose por area_names (un ID puede contar en varias zonas)",
        )
        parser.add_argument(
            "--area",
            default="",
            help="Filtrar por nombre de área (substring, case-insensitive)",
        )
        parser.add_argument(
            "--source",
            default="",
            help="Filtrar por source del catálogo (ej: text_search_relevance)",
        )
        parser.add_argument(
            "--export",
            default="",
            metavar="PATH",
            help="Exportar place_id sin ficha (uno por línea)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Máximo de IDs a exportar (0 = todos)",
        )

    def handle(self, *args, **options):
        qs = GooglePlaceId.objects.sin_ficha().order_by("-first_seen_at")
        if options["source"]:
            qs = qs.filter(source=options["source"])
        if options["area"]:
            qs = qs.filter(area_names__icontains=options["area"].strip())

        catalogo = GooglePlaceId.objects.count()
        con_ficha = GooglePlaceId.objects.con_ficha().count()
        sin_ficha = qs.count() if (options["source"] or options["area"]) else (
            catalogo - con_ficha
        )
        # Si hay filtros, sin_ficha es el filtrado; totales globales aparte
        sin_ficha_global = GooglePlaceId.objects.sin_ficha().count()
        places = Places.objects.count()
        con_details = GooglePlaceId.objects.con_details().count()
        sin_details = GooglePlaceId.objects.sin_details().count()
        details_ok = GooglePlaceDetails.objects.filter(fetch_status="ok").count()
        details_err = GooglePlaceDetails.objects.exclude(fetch_status="ok").count()

        self.stdout.write(f"\n{SEP}")
        self.stdout.write(self.style.SUCCESS("📋 IDs SIN FICHA (catálogo → Places)"))
        self.stdout.write(f"   Catálogo GooglePlaceId:  {catalogo:,}")
        self.stdout.write(f"   Places (fichas):         {places:,}")
        self.stdout.write(f"   Con ficha:               {con_ficha:,}")
        self.stdout.write(
            self.style.WARNING(f"   SIN ficha (global):      {sin_ficha_global:,}")
        )
        if options["source"] or options["area"]:
            self.stdout.write(f"   SIN ficha (filtro):      {sin_ficha:,}")
        pct = 100.0 * sin_ficha_global / catalogo if catalogo else 0
        self.stdout.write(f"   % sin enriquecer:        {pct:.1f}%")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("🗂  Staging Maps (GooglePlaceDetails)"))
        self.stdout.write(f"   Con details OK:          {con_details:,}")
        self.stdout.write(f"   Sin details OK (cola):   {sin_details:,}")
        self.stdout.write(f"   Filas details ok:        {details_ok:,}")
        self.stdout.write(f"   Filas details !ok:       {details_err:,}")
        self.stdout.write("")
        if details_ok:
            self.stdout.write("=== Details OK por familia (tipo_family) ===")
            from django.db.models import Count

            for row in (
                GooglePlaceDetails.objects.filter(fetch_status="ok")
                .values("tipo_family")
                .annotate(n=Count("id"))
                .order_by("-n")
            ):
                fam = row["tipo_family"] or "(vacío)"
                self.stdout.write(f"   {fam:20}  {row['n']:,}")
            self.stdout.write("")
            self.stdout.write("=== Top tipos Vive (tipo) ===")
            for row in (
                GooglePlaceDetails.objects.filter(fetch_status="ok")
                .values("tipo")
                .annotate(n=Count("id"))
                .order_by("-n")[:15]
            ):
                self.stdout.write(f"   {(row['tipo'] or 'otros'):30}  {row['n']:,}")
            self.stdout.write("")

        if options["por_area"]:
            self._print_por_area(options["area"])

        if options["export"]:
            path = Path(options["export"])
            path.parent.mkdir(parents=True, exist_ok=True)
            export_qs = qs
            if options["limit"] > 0:
                export_qs = export_qs[: options["limit"]]
            n = 0
            with path.open("w", encoding="utf-8") as fh:
                for place_id in export_qs.values_list("place_id", flat=True).iterator(
                    chunk_size=2000
                ):
                    fh.write(place_id + "\n")
                    n += 1
            self.stdout.write(
                self.style.SUCCESS(f"   ✓ Exportados {n:,} IDs → {path.resolve()}")
            )
        else:
            self.stdout.write(
                "   Exportar:  python manage.py report_ids_sin_ficha "
                "--export data/ids_sin_ficha.txt"
            )
            self.stdout.write(
                "   Por área:  python manage.py report_ids_sin_ficha --por-area\n"
            )

    def _print_por_area(self, area_filter: str) -> None:
        self.stdout.write("=== Sin ficha por área (area_names) ===")
        sql = """
            SELECT area, COUNT(*) AS n
            FROM (
              SELECT DISTINCT g.place_id, UNNEST(g.area_names) AS area
              FROM explorer_googleplaceid g
              WHERE (g.area_names IS NOT NULL AND cardinality(g.area_names) > 0)
                AND NOT EXISTS (
                  SELECT 1 FROM explorer_places p WHERE p.place_id = g.place_id
                )
            ) t
        """
        params: list = []
        if area_filter.strip():
            sql += " WHERE area ILIKE %s"
            params.append(f"%{area_filter.strip()}%")
        sql += " GROUP BY area ORDER BY n DESC"
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        if not rows:
            self.stdout.write("   (sin datos)")
            return
        for area, n in rows:
            self.stdout.write(f"   {area[:40]:40}  {n:,}")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) FROM explorer_googleplaceid g
                WHERE (g.area_names IS NULL OR cardinality(g.area_names) = 0)
                  AND NOT EXISTS (
                    SELECT 1 FROM explorer_places p WHERE p.place_id = g.place_id
                  )
                """
            )
            sin_area = cursor.fetchone()[0]
        self.stdout.write(f"   {'(sin area_names)':40}  {sin_area:,}")
        self.stdout.write("")
