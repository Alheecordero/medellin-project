"""Revisión editorial de las guías: lugares fuera de zona, sedes dudosas, paradas ocultas,
recomendaciones genéricas, datos sin fuente y guías sin revisión. Solo lee.

  python manage.py revisar_guias
  python manage.py revisar_guias --slug noche-en-laureles-y-la-70
  python manage.py revisar_guias --publicadas
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand

from explorer.models import CuratedGuide
from explorer.utils.guias import revisar_guia


class Command(BaseCommand):
    help = "Lista los avisos editoriales de cada guía. No cambia nada."

    def add_arguments(self, parser):
        parser.add_argument("--slug", action="append", help="Solo esta guía (se puede repetir)")
        parser.add_argument("--publicadas", action="store_true", help="Solo las publicadas")

    def handle(self, *args, **options):
        guias = CuratedGuide.objects.select_related("zona").order_by("-publicado", "orden", "slug")
        if options["slug"]:
            guias = guias.filter(slug__in=options["slug"])
        if options["publicadas"]:
            guias = guias.filter(publicado=True)
        total = Counter()
        for guia in guias:
            avisos = revisar_guia(guia)
            estado = "publicada" if guia.publicado else "borrador"
            self.stdout.write(f"\n{guia.slug} ({estado}, {guia.get_formato_display().lower()}): {len(avisos)} avisos")
            for aviso in avisos:
                self.stdout.write(f"  {aviso}")
                total[aviso.codigo] += 1
        self.stdout.write("\n" + ", ".join(f"{codigo}: {n}" for codigo, n in total.most_common()) if total else "\nsin avisos")
