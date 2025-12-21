"""
Limpia URLs locales de miniaturas que no existen en GCS.

Pone las URLs de miniatura/medium como vacías para que:
1. El sistema use las imágenes originales como fallback
2. El comando generar_miniaturas_gcs las detecte como pendientes

Uso:
  python manage.py limpiar_urls_locales --dry-run
  python manage.py limpiar_urls_locales
"""
import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from explorer.models import Foto
import time


class Command(BaseCommand):
    help = 'Limpia URLs locales de miniaturas para regenerarlas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría sin hacer cambios',
        )

    def log(self, msg, style=None):
        if style:
            msg = style(msg)
        self.stdout.write(msg)
        self.stdout.flush()

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.log('=' * 60)
        self.log('  LIMPIEZA DE URLs LOCALES', self.style.SUCCESS)
        self.log('=' * 60)
        self.log('')
        
        # Estadísticas
        total = Foto.objects.count()
        gcs = Foto.objects.filter(imagen_miniatura__startswith='https://storage.googleapis.com').count()
        locales = Foto.objects.filter(imagen_miniatura__startswith='/media/').count()
        vacias = Foto.objects.filter(imagen_miniatura__isnull=True).count() + \
                 Foto.objects.filter(imagen_miniatura='').count()
        
        self.log('📊 ESTADO ACTUAL:')
        self.log(f'   Total fotos:        {total:,}')
        self.log(f'   ✅ En GCS:          {gcs:,} ({gcs*100/total:.1f}%)')
        self.log(f'   ⚠️  URLs locales:   {locales:,} ({locales*100/total:.1f}%) <- A LIMPIAR')
        self.log(f'   📭 Vacías/Null:     {vacias:,}')
        self.log('')
        
        if locales == 0:
            self.log('✅ No hay URLs locales que limpiar', self.style.SUCCESS)
            return
        
        if dry_run:
            self.log('🔍 MODO DRY-RUN: No se harán cambios', self.style.WARNING)
            self.log('')
            self.log(f'Se limpiarían {locales:,} URLs locales')
            self.log('')
            self.log('Ejecuta sin --dry-run para aplicar los cambios')
            return
        
        # Limpiar URLs locales
        self.log(f'🧹 Limpiando {locales:,} URLs locales...')
        
        start = time.time()
        
        try:
            with transaction.atomic():
                updated = Foto.objects.filter(
                    imagen_miniatura__startswith='/media/'
                ).update(
                    imagen_miniatura='',
                    imagen_mediana=''
                )
                
            elapsed = time.time() - start
            
            self.log('')
            self.log(f'✅ Limpiadas: {updated:,} fotos en {elapsed:.1f}s', self.style.SUCCESS)
            
        except Exception as e:
            self.log(f'❌ Error: {e}', self.style.ERROR)
            return
        
        # Estado final
        self.log('')
        nuevas_gcs = Foto.objects.filter(imagen_miniatura__startswith='https://').count()
        nuevas_vacias = Foto.objects.filter(imagen_miniatura__isnull=True).count() + \
                        Foto.objects.filter(imagen_miniatura='').count()
        
        self.log('📊 ESTADO FINAL:')
        self.log(f'   ✅ En GCS:          {nuevas_gcs:,}')
        self.log(f'   📭 Pendientes:      {nuevas_vacias:,} (para regenerar)')
        self.log('')
        self.log('ℹ️  Ahora ejecuta: python manage.py generar_miniaturas_gcs', self.style.NOTICE)
        self.log('   para regenerar las miniaturas faltantes')

