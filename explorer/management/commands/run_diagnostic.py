# explorer/management/commands/run_diagnostic.py
from django.core.management.base import BaseCommand
from explorer.models import Places

class Command(BaseCommand):
    help = 'Corre un diagnóstico para verificar las URLs de las imágenes.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- INICIANDO DIAGNÓSTICO DE IMÁGENES ---'))
        
        lugar = Places.objects.filter(fotos__isnull=False).first()
        
        if not lugar:
            self.stdout.write(self.style.ERROR('DIAGNÓSTICO FALLIDO: No se encontró ningún lugar con fotos asociadas en la base de datos.'))
            self.stdout.write(self.style.WARNING('Por favor, ejecuta primero el script para procesar los JSONs y poblar la base de datos.'))
            return

        self.stdout.write(f'Lugar de prueba encontrado: "{lugar.nombre}" (ID: {lugar.id})')
        
        primera_foto = lugar.fotos.first()
        
        if not primera_foto:
            self.stdout.write(self.style.ERROR(f'DIAGNÓSTICO FALLIDO: El lugar "{lugar.nombre}" parece tener fotos, pero no se pudo obtener la primera.'))
            return
            
        self.stdout.write(f'  -> Foto de prueba encontrada (ID: {primera_foto.id})')
        self.stdout.write(f'  -> Valor del campo "imagen" en la BD: {primera_foto.imagen}')
        
        try:
            url_generada = primera_foto.imagen.url
            self.stdout.write(self.style.SUCCESS(f'  -> URL generada por Django: {url_generada}'))
            if not url_generada:
                self.stdout.write(self.style.ERROR('DIAGNÓSTICO FALLIDO: La URL está VACÍA. El problema está en la configuración de `storages` o `settings.py`.'))
            elif 'storage.googleapis.com' not in url_generada:
                self.stdout.write(self.style.ERROR(f'DIAGNÓSTICO FALLIDO: La URL no es de Google Cloud Storage. Es una ruta local: "{url_generada}". El problema está en la configuración de `settings.py` (probablemente `USE_GCS` es False).'))
            else:
                 self.stdout.write(self.style.SUCCESS('DIAGNÓSTICO EXITOSO: La configuración parece correcta. La URL de GCS se está generando bien.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'DIAGNÓSTICO FALLIDO: Ocurrió un error al intentar acceder a `.url`: {e}'))

        self.stdout.write(self.style.SUCCESS('--- DIAGNÓSTICO FINALIZADO ---')) 