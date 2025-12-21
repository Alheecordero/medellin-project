"""
Management command para generar miniaturas y subirlas directamente a GCS.
No guarda nada localmente, todo va directo a Google Cloud Storage.

Uso:
    python manage.py generar_miniaturas_gcs
    python manage.py generar_miniaturas_gcs --batch-size=100
    python manage.py generar_miniaturas_gcs --dry-run
"""
import io
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from explorer.models import Foto


class Command(BaseCommand):
    help = 'Genera miniaturas y las sube directamente a GCS (no guarda local)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Fotos a procesar por batch (default: 100)',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=4,
            help='Workers paralelos (default: 4)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular sin subir nada',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Límite total de fotos a procesar (0 = todas)',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        workers = options['workers']
        dry_run = options['dry_run']
        limit = options['limit']

        # Verificar configuración GCS
        bucket_name = getattr(settings, 'GS_BUCKET_NAME', None)
        if not bucket_name:
            self.stderr.write(self.style.ERROR('❌ GS_BUCKET_NAME no configurado'))
            return

        # Inicializar cliente GCS
        try:
            from google.cloud import storage as gcs_storage
            gs_credentials = getattr(settings, 'GS_CREDENTIALS', None)
            if gs_credentials:
                client = gcs_storage.Client(credentials=gs_credentials)
            else:
                client = gcs_storage.Client()
            bucket = client.bucket(bucket_name)
            self.stdout.write(self.style.SUCCESS(f'✓ Conectado a GCS bucket: {bucket_name}'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'❌ Error conectando a GCS: {e}'))
            return

        # Contar fotos sin miniaturas
        qs = Foto.objects.filter(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).exclude(
            Q(imagen__isnull=True) | Q(imagen='')
        ).order_by('id')

        total_pendientes = qs.count()
        self.stdout.write(f'\n📊 Fotos sin miniatura: {total_pendientes:,}')

        if total_pendientes == 0:
            self.stdout.write(self.style.SUCCESS('✓ Todas las fotos ya tienen miniaturas'))
            return

        if limit > 0:
            qs = qs[:limit]
            total_a_procesar = min(limit, total_pendientes)
        else:
            total_a_procesar = total_pendientes

        self.stdout.write(f'🚀 Procesando: {total_a_procesar:,} fotos (workers={workers})\n')

        # Procesar en batches
        procesadas = 0
        errores = 0
        offset = 0

        while offset < total_a_procesar:
            batch = list(qs[offset:offset + batch_size])
            if not batch:
                break

            self.stdout.write(f'\n--- Batch {offset//batch_size + 1}: fotos {offset+1}-{offset+len(batch)} ---')

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        self._procesar_foto,
                        foto,
                        bucket,
                        bucket_name,
                        dry_run
                    ): foto
                    for foto in batch
                }

                for future in as_completed(futures):
                    foto = futures[future]
                    try:
                        ok, msg = future.result()
                        if ok:
                            procesadas += 1
                            self.stdout.write(self.style.SUCCESS(f'  ✓ [{procesadas}/{total_a_procesar}] {msg}'))
                        else:
                            errores += 1
                            self.stdout.write(self.style.WARNING(f'  ⚠ {msg}'))
                    except Exception as e:
                        errores += 1
                        self.stdout.write(self.style.ERROR(f'  ✗ Foto {foto.id}: {e}'))

            offset += batch_size
            
            # Flush stdout para ver en tiempo real
            sys.stdout.flush()

        # Resumen
        self.stdout.write(f'\n{"="*50}')
        self.stdout.write(self.style.SUCCESS(f'✓ Procesadas: {procesadas:,}'))
        if errores:
            self.stdout.write(self.style.WARNING(f'⚠ Errores: {errores:,}'))
        self.stdout.write(f'{"="*50}\n')

    def _procesar_foto(self, foto, bucket, bucket_name, dry_run):
        """Procesa una foto: descarga, redimensiona, sube a GCS."""
        try:
            img_url = str(foto.imagen).strip()
            if not img_url:
                return False, f'Foto {foto.id}: URL vacía'

            # Construir URL absoluta si es necesario
            if not img_url.startswith('http'):
                img_url = f'https://storage.googleapis.com/{bucket_name}/{img_url.lstrip("/")}'

            # Descargar imagen original
            resp = requests.get(img_url, timeout=30)
            if resp.status_code != 200:
                return False, f'Foto {foto.id}: HTTP {resp.status_code}'

            # Abrir y procesar
            original = Image.open(io.BytesIO(resp.content))
            img = self._ensure_rgb(original)

            # Generar variantes
            thumb_bytes = self._resize_to_bytes(img, 220)
            medium_bytes = self._resize_to_bytes(img, 800)

            # Rutas en GCS
            lugar_slug = foto.lugar.slug if foto.lugar else 'unknown'
            base_path = f'tourism/images'
            thumb_path = f'{base_path}/thumb/{lugar_slug}/{foto.id}.jpg'
            medium_path = f'{base_path}/medium/{lugar_slug}/{foto.id}.jpg'

            if dry_run:
                return True, f'Foto {foto.id} -> {thumb_path} (dry-run)'

            # Subir a GCS sin ACL (bucket uniform access)
            thumb_blob = bucket.blob(thumb_path)
            thumb_blob.upload_from_string(
                thumb_bytes, 
                content_type='image/jpeg',
                predefined_acl=None
            )

            medium_blob = bucket.blob(medium_path)
            medium_blob.upload_from_string(
                medium_bytes, 
                content_type='image/jpeg',
                predefined_acl=None
            )

            # Actualizar BD
            thumb_url = f'https://storage.googleapis.com/{bucket_name}/{thumb_path}'
            medium_url = f'https://storage.googleapis.com/{bucket_name}/{medium_path}'

            Foto.objects.filter(pk=foto.pk).update(
                imagen_miniatura=thumb_url,
                imagen_mediana=medium_url
            )

            return True, f'Foto {foto.id}'

        except Exception as e:
            return False, f'Foto {foto.id}: {e}'

    @staticmethod
    def _ensure_rgb(img):
        """Convierte imagen a RGB."""
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            return background
        if img.mode != 'RGB':
            return img.convert('RGB')
        return img

    @staticmethod
    def _resize_to_bytes(img, target_width, quality=85):
        """Redimensiona imagen y devuelve bytes JPEG."""
        if img.width > target_width:
            ratio = target_width / img.width
            new_size = (target_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        return buffer.getvalue()

