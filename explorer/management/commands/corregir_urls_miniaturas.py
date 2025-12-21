"""
Comando para corregir URLs locales de miniaturas a URLs de GCS.

Convierte:
  /media/tourism/images/thumb/X/Y.jpg 
  → 
  https://storage.googleapis.com/vivemedellin-bucket/tourism/images/thumb/X/Y.jpg

Uso:
  python manage.py corregir_urls_miniaturas --dry-run  # Ver qué se haría
  python manage.py corregir_urls_miniaturas            # Ejecutar corrección
  python manage.py corregir_urls_miniaturas --verify   # Verificar que existen en GCS
"""
import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from explorer.models import Foto
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


GCS_BASE = 'https://storage.googleapis.com/vivemedellin-bucket'


class Command(BaseCommand):
    help = 'Corrige URLs locales de miniaturas a URLs de GCS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría sin hacer cambios',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verificar que el archivo existe en GCS antes de actualizar',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Tamaño del batch para commits (default: 500)',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=5,
            help='Número de workers para verificación (default: 5)',
        )

    def log(self, msg, style=None):
        """Log con flush inmediato"""
        if style:
            msg = style(msg)
        self.stdout.write(msg)
        self.stdout.flush()
        sys.stdout.flush()

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verify = options['verify']
        batch_size = options['batch_size']
        workers = options['workers']

        self.log('=' * 60)
        self.log('  CORRECCIÓN DE URLs DE MINIATURAS', self.style.SUCCESS)
        self.log('=' * 60)
        self.log('')
        
        # Estadísticas iniciales
        total_fotos = Foto.objects.count()
        ya_correctas_gcs = Foto.objects.filter(imagen_miniatura__startswith='https://storage.googleapis.com').count()
        urls_locales = Foto.objects.filter(imagen_miniatura__startswith='/media/').count()
        sin_miniatura = Foto.objects.filter(imagen_miniatura__isnull=True).count() + \
                       Foto.objects.filter(imagen_miniatura='').count()
        
        self.log('📊 ESTADO ACTUAL:', self.style.NOTICE)
        self.log(f'   Total fotos:        {total_fotos:,}')
        self.log(f'   ✅ Ya en GCS:       {ya_correctas_gcs:,} ({ya_correctas_gcs*100/total_fotos:.1f}%)')
        self.log(f'   ⚠️  URLs locales:   {urls_locales:,} ({urls_locales*100/total_fotos:.1f}%) <- A CORREGIR')
        self.log(f'   ❌ Sin miniatura:   {sin_miniatura:,}')
        self.log('')
        
        if urls_locales == 0:
            self.log('✅ No hay URLs locales que corregir. ¡Todo está en GCS!', self.style.SUCCESS)
            return
        
        if dry_run:
            self.log('🔍 MODO DRY-RUN: No se harán cambios reales', self.style.WARNING)
            self.log('')
        
        # Obtener fotos con URLs locales
        fotos_a_corregir = list(Foto.objects.filter(
            imagen_miniatura__startswith='/media/'
        ).values_list('id', 'imagen_miniatura', 'imagen_mediana'))
        
        self.log(f'📝 Procesando {len(fotos_a_corregir):,} fotos...')
        self.log('')
        
        corregidas = 0
        errores = 0
        no_existen = 0
        start_time = time.time()
        
        def convertir_url(url_local):
            """Convierte URL local a GCS"""
            if not url_local or not url_local.startswith('/media/'):
                return url_local
            return GCS_BASE + url_local.replace('/media/', '/')
        
        def verificar_existe_gcs(url):
            """Verifica si URL existe en GCS"""
            try:
                r = requests.head(url, timeout=5)
                return r.status_code == 200
            except:
                return False
        
        # Preparar datos para actualización
        actualizaciones = []
        
        for i, (foto_id, thumb_local, medium_local) in enumerate(fotos_a_corregir, 1):
            thumb_gcs = convertir_url(thumb_local)
            medium_gcs = convertir_url(medium_local)
            
            # Mostrar progreso cada 1000
            if i % 1000 == 0 or i == len(fotos_a_corregir):
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(fotos_a_corregir) - i) / rate if rate > 0 else 0
                self.log(f'   [{i:,}/{len(fotos_a_corregir):,}] {i*100/len(fotos_a_corregir):.1f}% - {rate:.0f}/s - ETA: {eta:.0f}s')
            
            # Mostrar ejemplos cada 5000
            if i <= 3 or i % 5000 == 0:
                self.log(f'   📌 Ejemplo #{i}:')
                self.log(f'      Local:  {thumb_local[:60]}...')
                self.log(f'      → GCS:  {thumb_gcs[:60]}...')
            
            actualizaciones.append({
                'id': foto_id,
                'imagen_miniatura': thumb_gcs,
                'imagen_mediana': medium_gcs
            })
        
        self.log('')
        
        # Verificar muestras si se requiere
        if verify:
            self.log('🔍 Verificando muestra de URLs en GCS...', self.style.NOTICE)
            
            # Tomar muestra aleatoria
            import random
            muestra = random.sample(actualizaciones, min(50, len(actualizaciones)))
            
            existentes = 0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(verificar_existe_gcs, a['imagen_miniatura']): a for a in muestra}
                for future in as_completed(futures):
                    if future.result():
                        existentes += 1
            
            porcentaje_existente = existentes * 100 / len(muestra)
            self.log(f'   Muestra verificada: {existentes}/{len(muestra)} ({porcentaje_existente:.1f}%) existen en GCS')
            
            if porcentaje_existente < 80:
                self.log('   ⚠️  Menos del 80% existe. Algunas URLs pueden fallar.', self.style.WARNING)
            else:
                self.log('   ✅ La mayoría de URLs existen en GCS', self.style.SUCCESS)
            self.log('')
        
        # Aplicar cambios
        if not dry_run:
            self.log('💾 Aplicando cambios en la base de datos...', self.style.NOTICE)
            
            try:
                with transaction.atomic():
                    for i in range(0, len(actualizaciones), batch_size):
                        batch = actualizaciones[i:i + batch_size]
                        
                        for item in batch:
                            Foto.objects.filter(id=item['id']).update(
                                imagen_miniatura=item['imagen_miniatura'],
                                imagen_mediana=item['imagen_mediana']
                            )
                        
                        corregidas += len(batch)
                        
                        if (i + batch_size) % 2000 == 0 or i + batch_size >= len(actualizaciones):
                            self.log(f'   Guardadas: {corregidas:,}/{len(actualizaciones):,}')
                
                self.log('')
                self.log('✅ Cambios aplicados exitosamente', self.style.SUCCESS)
                
            except Exception as e:
                self.log(f'❌ Error al guardar: {e}', self.style.ERROR)
                errores += 1
        else:
            corregidas = len(actualizaciones)
        
        # Resumen final
        elapsed = time.time() - start_time
        self.log('')
        self.log('=' * 60)
        self.log('  RESUMEN FINAL', self.style.SUCCESS)
        self.log('=' * 60)
        self.log(f'   Total procesadas:   {len(actualizaciones):,}')
        self.log(f'   Corregidas:         {corregidas:,}')
        self.log(f'   Errores:            {errores:,}')
        self.log(f'   Tiempo:             {elapsed:.1f}s')
        self.log('')
        
        # Verificar estado final
        if not dry_run:
            nuevas_gcs = Foto.objects.filter(imagen_miniatura__startswith='https://storage.googleapis.com').count()
            nuevas_locales = Foto.objects.filter(imagen_miniatura__startswith='/media/').count()
            
            self.log('📊 ESTADO FINAL:', self.style.NOTICE)
            self.log(f'   ✅ En GCS:          {nuevas_gcs:,} ({nuevas_gcs*100/total_fotos:.1f}%)')
            self.log(f'   ⚠️  URLs locales:   {nuevas_locales:,}')
            
            if nuevas_locales == 0:
                self.log('')
                self.log('🎉 ¡TODAS las miniaturas ahora apuntan a GCS!', self.style.SUCCESS)
        else:
            self.log('ℹ️  Ejecuta sin --dry-run para aplicar los cambios', self.style.WARNING)
