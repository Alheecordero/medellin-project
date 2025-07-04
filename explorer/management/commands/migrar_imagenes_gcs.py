import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files import File
from explorer.models import Places

class Command(BaseCommand):
    help = "Migra imágenes locales al bucket de Google Cloud Storage"

    def handle(self, *args, **kwargs):
        lugares = Places.objects.exclude(imagen='')  # Solo los que tienen imagen

        for lugar in lugares:
            local_path = os.path.join(settings.MEDIA_ROOT, lugar.imagen.name)
            if os.path.exists(local_path):
                self.stdout.write(f"Subiendo {lugar.imagen.name}...")
                with open(local_path, 'rb') as f:
                    lugar.imagen.save(os.path.basename(lugar.imagen.name), File(f), save=True)
            else:
                self.stdout.write(self.style.WARNING(f"No se encontró: {local_path}"))
