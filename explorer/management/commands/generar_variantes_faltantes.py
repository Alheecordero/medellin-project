"""
Genera las variantes (thumb/medium) que faltan en GCS.
Verifica con HEAD request y solo procesa las que devuelven 404.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q, Min
from django.conf import settings
from explorer.models import Places, Foto
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from PIL import Image
from google.cloud import storage as gcs_storage
import requests
import time


class Command(BaseCommand):
    help = 'Genera las variantes de imagen que faltan en GCS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Número de lugares a procesar (default: 100)',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=10,
            help='Workers paralelos para verificación (default: 10)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo verificar, no generar',
        )

    def verificar_url(self, url):
        """Verifica si una URL existe en GCS"""
        if not url:
            return False
        try:
            r = requests.head(url, timeout=5, allow_redirects=True)
            return r.status_code == 200
        except:
            return False

    def descargar_imagen(self, url):
        """Descarga una imagen desde una URL"""
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                return BytesIO(r.content)
        except Exception as e:
            self.stdout.write(f'    Error descargando: {e}')
        return None

    def generar_variantes(self, imagen_bytes, thumb_size=220, medium_size=800):
        """Genera las variantes thumb y medium de una imagen"""
        try:
            img = Image.open(imagen_bytes)
            
            # Convertir a RGB si es necesario
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Generar thumbnail
            thumb = img.copy()
            thumb.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
            thumb_bytes = BytesIO()
            thumb.save(thumb_bytes, format='JPEG', quality=85, optimize=True)
            thumb_bytes.seek(0)
            
            # Generar medium
            medium = img.copy()
            medium.thumbnail((medium_size, medium_size), Image.Resampling.LANCZOS)
            medium_bytes = BytesIO()
            medium.save(medium_bytes, format='JPEG', quality=85, optimize=True)
            medium_bytes.seek(0)
            
            return thumb_bytes, medium_bytes
        except Exception as e:
            self.stdout.write(f'    Error generando variantes: {e}')
            return None, None

    def subir_a_gcs(self, bytes_io, path):
        """Sube un archivo a GCS usando el cliente directo y retorna URL completa"""
        try:
            # Usar cliente GCS directo (más confiable que django-storages)
            client = gcs_storage.Client(
                credentials=settings.GS_CREDENTIALS,
                project=settings.GS_PROJECT_ID
            )
            bucket = client.bucket(settings.GS_BUCKET_NAME)
            blob = bucket.blob(path)
            
            # Subir el archivo
            blob.upload_from_file(bytes_io, content_type='image/jpeg')
            
            # Verificar que el archivo existe
            if not blob.exists():
                self.stdout.write(f'    ⚠️  Archivo no existe después de subir: {path}')
                return None
            
            # Construir URL completa
            return f'https://storage.googleapis.com/{settings.GS_BUCKET_NAME}/{path}'
        except Exception as e:
            self.stdout.write(f'    Error subiendo a GCS: {e}')
            return None

    def handle(self, *args, **options):
        limit = options['limit']
        workers = options['workers']
        dry_run = options['dry_run']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  GENERAR VARIANTES FALTANTES'))
        self.stdout.write('=' * 70)
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN: Solo verificación'))
            self.stdout.write('')

        # Obtener lugares con fotos que están marcados como optimizados
        # pero que podrían no tener las variantes reales en GCS
        self.stdout.write('  Obteniendo lugares con primera foto...')
        
        lugares = Places.objects.filter(
            tiene_fotos=True
        ).exclude(
            Q(slug__isnull=True) | Q(slug='')
        ).annotate(
            first_foto_id=Min('fotos__id')
        ).filter(
            first_foto_id__isnull=False
        ).order_by('id')[:limit]

        # Precargar las primeras fotos
        foto_ids = [l.first_foto_id for l in lugares]
        fotos = {f.id: f for f in Foto.objects.filter(id__in=foto_ids)}
        
        lugares_data = []
        for lugar in lugares:
            foto = fotos.get(lugar.first_foto_id)
            if foto and foto.imagen_miniatura:
                lugares_data.append({
                    'lugar': lugar,
                    'foto': foto,
                    'url_mini': foto.imagen_miniatura,
                    'url_med': foto.imagen_mediana,
                    'url_orig': foto.imagen,
                })

        self.stdout.write(f'  Lugares a verificar: {len(lugares_data):,}')
        self.stdout.write('')

        # Fase 1: Verificar cuáles variantes faltan
        self.stdout.write('  FASE 1: Verificando existencia en GCS...')
        
        faltantes = []
        verificados = 0
        start_time = time.time()

        def verificar_lugar(data):
            mini_existe = self.verificar_url(data['url_mini'])
            med_existe = self.verificar_url(data['url_med'])
            return {
                **data,
                'mini_existe': mini_existe,
                'med_existe': med_existe,
                'falta_alguna': not mini_existe or not med_existe
            }

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(verificar_lugar, d): d for d in lugares_data}
            
            for future in as_completed(futures):
                verificados += 1
                result = future.result()
                
                if result['falta_alguna']:
                    faltantes.append(result)
                
                if verificados % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = verificados / elapsed if elapsed > 0 else 0
                    self.stdout.write(
                        f'    Verificados: {verificados:,}/{len(lugares_data):,} | '
                        f'Faltantes: {len(faltantes):,} | '
                        f'{rate:.1f}/s'
                    )

        self.stdout.write('')
        self.stdout.write(f'  Verificación completada:')
        self.stdout.write(f'    Total verificados: {verificados:,}')
        self.stdout.write(f'    Con variantes OK:  {verificados - len(faltantes):,}')
        self.stdout.write(self.style.WARNING(f'    Faltantes:         {len(faltantes):,}'))
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('  DRY-RUN: No se generaron variantes'))
            if faltantes:
                self.stdout.write('')
                self.stdout.write('  Ejemplos de faltantes (primeros 10):')
                for f in faltantes[:10]:
                    self.stdout.write(f"    - {f['lugar'].slug}")
            return

        if not faltantes:
            self.stdout.write(self.style.SUCCESS('  ✅ Todas las variantes existen!'))
            return

        # Fase 2: Generar las variantes faltantes
        self.stdout.write('  FASE 2: Generando variantes faltantes...')
        self.stdout.write('')

        generadas = 0
        errores = 0
        GCS_BASE = 'tourism/images'

        for i, data in enumerate(faltantes):
            lugar = data['lugar']
            foto = data['foto']
            
            self.stdout.write(f'  [{i+1}/{len(faltantes)}] {lugar.slug}')
            
            # Descargar original
            imagen_bytes = self.descargar_imagen(data['url_orig'])
            if not imagen_bytes:
                self.stdout.write(self.style.ERROR('    ✗ Error descargando original'))
                errores += 1
                continue

            # Generar variantes
            thumb_bytes, medium_bytes = self.generar_variantes(imagen_bytes)
            if not thumb_bytes or not medium_bytes:
                self.stdout.write(self.style.ERROR('    ✗ Error generando variantes'))
                errores += 1
                continue

            # Paths en GCS
            thumb_path = f'{GCS_BASE}/thumb/{lugar.slug}/{foto.id}.jpg'
            medium_path = f'{GCS_BASE}/medium/{lugar.slug}/{foto.id}.jpg'

            # Subir a GCS
            thumb_url = None
            medium_url = None

            if not data['mini_existe']:
                thumb_url = self.subir_a_gcs(thumb_bytes, thumb_path)
                if thumb_url:
                    self.stdout.write(f'    ✓ Thumb subido')

            if not data['med_existe']:
                medium_url = self.subir_a_gcs(medium_bytes, medium_path)
                if medium_url:
                    self.stdout.write(f'    ✓ Medium subido')

            # Actualizar BD
            update_fields = {}
            if thumb_url:
                update_fields['imagen_miniatura'] = thumb_url
            if medium_url:
                update_fields['imagen_mediana'] = medium_url

            if update_fields:
                Foto.objects.filter(id=foto.id).update(**update_fields)
                generadas += 1
                self.stdout.write(self.style.SUCCESS(f'    ✓ BD actualizada'))

        # Resumen
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESUMEN'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Lugares procesados:  {len(faltantes):,}')
        self.stdout.write(f'  Variantes generadas: {generadas:,}')
        self.stdout.write(f'  Errores:             {errores:,}')
        self.stdout.write('')
        
        if generadas > 0:
            self.stdout.write(self.style.SUCCESS('  ✅ Proceso completado'))
        
        self.stdout.write('')

