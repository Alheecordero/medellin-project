from django.core.management.base import BaseCommand
from explorer.models import Foto, Places
from django.db import transaction

class Command(BaseCommand):
    help = 'Corrige las rutas antiguas de imagenes en Places y Foto que apuntan a imagenes_poblado/'

    def handle(self, *args, **options):
        corregidos_foto = 0
        corregidos_places = 0

        with transaction.atomic():
            self.stdout.write("\n📁 Corrigiendo rutas en Foto...")
            fotos = Foto.objects.filter(imagen__startswith="imagenes_poblado/")
            for foto in fotos:
                original = foto.imagen.name
                foto.imagen.name = original.replace("imagenes_poblado/", "imagenes_medellin/")
                foto.save()
                corregidos_foto += 1

            self.stdout.write("\n🏙️ Corrigiendo rutas en Places...")
            lugares = Places.objects.filter(imagen__startswith="imagenes_poblado/")
            for lugar in lugares:
                original = lugar.imagen.name
                lugar.imagen.name = original.replace("imagenes_poblado/", "portadas_lugares/")
                lugar.save()
                corregidos_places += 1

        self.stdout.write(self.style.SUCCESS(f"\n✅ Correcciones completas:"))
        self.stdout.write(self.style.SUCCESS(f" - Fotos corregidas: {corregidos_foto}"))
        self.stdout.write(self.style.SUCCESS(f" - Portadas corregidas en Places: {corregidos_places}"))
