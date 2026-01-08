"""
Corrige URLs relativas (/media/...) a URLs completas de GCS
"""
from django.core.management.base import BaseCommand
from explorer.models import Foto
from django.core.files.storage import default_storage


class Command(BaseCommand):
    help = 'Corrige URLs relativas a URLs completas de GCS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar, no actualizar',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  CORRECCIÓN DE URLs RELATIVAS'))
        self.stdout.write('=' * 70)
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN: Solo mostrar'))
            self.stdout.write('')

        # Buscar fotos con URLs relativas
        fotos_mini = Foto.objects.filter(imagen_miniatura__startswith='/media/')
        fotos_med = Foto.objects.filter(imagen_mediana__startswith='/media/')

        total_mini = fotos_mini.count()
        total_med = fotos_med.count()

        self.stdout.write(f'  Fotos con miniatura relativa: {total_mini:,}')
        self.stdout.write(f'  Fotos con mediana relativa:   {total_med:,}')
        self.stdout.write('')

        if total_mini == 0 and total_med == 0:
            self.stdout.write(self.style.SUCCESS('  ✅ No hay URLs relativas que corregir'))
            return

        # Obtener bucket name
        bucket_name = getattr(default_storage, 'bucket_name', 'vivemedellin-bucket')

        actualizados = 0

        # Corregir miniaturas
        for foto in fotos_mini:
            if foto.imagen_miniatura.startswith('/media/'):
                # Extraer path relativo
                path = foto.imagen_miniatura.replace('/media/', '')
                nueva_url = f'https://storage.googleapis.com/{bucket_name}/{path}'
                
                if dry_run:
                    self.stdout.write(f'  [DRY-RUN] Foto {foto.id}: {foto.imagen_miniatura[:60]}... → {nueva_url[:60]}...')
                else:
                    foto.imagen_miniatura = nueva_url
                    foto.save(update_fields=['imagen_miniatura'])
                    actualizados += 1

        # Corregir medianas
        for foto in fotos_med:
            if foto.imagen_mediana.startswith('/media/'):
                # Extraer path relativo
                path = foto.imagen_mediana.replace('/media/', '')
                nueva_url = f'https://storage.googleapis.com/{bucket_name}/{path}'
                
                if dry_run:
                    self.stdout.write(f'  [DRY-RUN] Foto {foto.id}: {foto.imagen_mediana[:60]}... → {nueva_url[:60]}...')
                else:
                    foto.imagen_mediana = nueva_url
                    foto.save(update_fields=['imagen_mediana'])
                    actualizados += 1

        self.stdout.write('')
        self.stdout.write('=' * 70)
        if dry_run:
            self.stdout.write(self.style.WARNING(f'  DRY-RUN: Se corregirían {total_mini + total_med} URLs'))
        else:
            self.stdout.write(self.style.SUCCESS(f'  ✅ URLs corregidas: {actualizados:,}'))
        self.stdout.write('')

