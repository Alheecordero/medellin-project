"""
Exporta el catálogo GooglePlaceId a un archivo de texto (un ID por línea).

Uso:
  python manage.py exportar_google_place_ids data/google_place_ids.txt
"""
from django.core.management.base import BaseCommand

from explorer.models import GooglePlaceId


class Command(BaseCommand):
    help = "Exporta GooglePlaceId → archivo (sin ejecutar scan)."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str, help="Ruta del archivo de salida")

    def handle(self, *args, **options):
        filepath = options["archivo"]
        ids = GooglePlaceId.objects.order_by("place_id").values_list("place_id", flat=True)
        with open(filepath, "w", encoding="utf-8") as f:
            count = 0
            for pid in ids:
                f.write(f"{pid}\n")
                count += 1
        self.stdout.write(self.style.SUCCESS(f"📄 {count:,} place_id → {filepath}"))
