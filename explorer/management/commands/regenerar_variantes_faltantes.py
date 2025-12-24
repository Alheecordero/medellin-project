"""
Regenera SOLO las variantes que no existen en GCS.
Verifica cuáles URLs devuelven 404 y las regenera desde la original.
"""
import requests
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from explorer.models import Foto, Places
import time


class Command(BaseCommand):
    help = 'Regenera variantes que no existen en GCS (verificando con HEAD request)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=500,
            help='Número de fotos a procesar',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=10,
            help='Workers paralelos para verificar URLs',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo verificar, no regenerar',
        )

    def url_exists(self, url):
        """Verifica si una URL existe"""
        try:
            r = requests.head(url, timeout=5, allow_redirects=True)
            return r.status_code == 200
        except:
            return False

    def handle(self, *args, **options):
        limit = options['limit']
        workers = options['workers']
        dry_run = options['dry_run']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  REGENERAR VARIANTES FALTANTES'))
        self.stdout.write('=' * 70)
        self.stdout.write('')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN'))
        self.stdout.write('')

        # Obtener fotos con variantes (que tienen URLs pero pueden no existir en GCS)
        self.stdout.write('  Cargando fotos con variantes...')
        fotos = list(Foto.objects.filter(
            imagen_miniatura__isnull=False
        ).exclude(
            imagen_miniatura=''
        ).select_related('lugar')[:limit])

        total = len(fotos)
        self.stdout.write(f'  Fotos a verificar: {total:,}')
        self.stdout.write('')

        # Verificar cuáles no existen
        faltantes = []
        verificadas = 0

        self.stdout.write('  Verificando existencia en GCS...')
        start_time = time.time()

        def verificar_foto(foto):
            mini_ok = self.url_exists(foto.imagen_miniatura) if foto.imagen_miniatura else False
            med_ok = self.url_exists(foto.imagen_mediana) if foto.imagen_mediana else False
            return {
                'foto': foto,
                'mini_ok': mini_ok,
                'med_ok': med_ok,
                'necesita_regenerar': not mini_ok or not med_ok
            }

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(verificar_foto, f): f for f in fotos}
            
            for future in as_completed(futures):
                verificadas += 1
                r = future.result()
                
                if r['necesita_regenerar']:
                    faltantes.append(r['foto'])
                
                if verificadas % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = verificadas / elapsed if elapsed > 0 else 0
                    eta = (total - verificadas) / rate if rate > 0 else 0
                    self.stdout.write(
                        f'    Verificadas: {verificadas:,}/{total:,} | '
                        f'Faltantes: {len(faltantes):,} | '
                        f'ETA: {eta:.0f}s'
                    )

        self.stdout.write('')
        self.stdout.write(f'  Total verificadas: {total:,}')
        self.stdout.write(f'  Variantes faltantes: {len(faltantes):,}')
        self.stdout.write('')

        if not faltantes:
            self.stdout.write(self.style.SUCCESS('  ✅ Todas las variantes existen en GCS!'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('  DRY-RUN: No se regenerarán'))
            self.stdout.write('')
            self.stdout.write('  Ejemplos de fotos a regenerar:')
            for f in faltantes[:5]:
                self.stdout.write(f'    ID:{f.id} -> {f.lugar.slug if f.lugar else "?"}')
            return

        # Regenerar las faltantes
        self.stdout.write('  Regenerando variantes faltantes...')
        self.stdout.write('')
        
        regeneradas = 0
        errores = 0

        for i, foto in enumerate(faltantes):
            try:
                # Descargar original
                img_url = foto.imagen
                if not img_url:
                    errores += 1
                    continue

                resp = requests.get(img_url, timeout=30)
                resp.raise_for_status()

                original = Image.open(BytesIO(resp.content))
                img = self._ensure_rgb(original)

                # Generar variantes
                medium_bytes = self._resize_and_serialize(img, target_width=800)
                thumb_bytes = self._resize_and_serialize(img, target_width=220)

                # Guardar en GCS
                place_slug = foto.lugar.slug if foto.lugar else str(foto.lugar_id)
                foto_id = foto.id

                medium_path = f"tourism/images/medium/{place_slug}/{foto_id}.jpg"
                thumb_path = f"tourism/images/thumb/{place_slug}/{foto_id}.jpg"

                # Guardar
                medium_name = default_storage.save(
                    medium_path,
                    ContentFile(medium_bytes.getvalue()),
                )
                thumb_name = default_storage.save(
                    thumb_path,
                    ContentFile(thumb_bytes.getvalue()),
                )

                # URLs
                medium_url = default_storage.url(medium_name)
                thumb_url = default_storage.url(thumb_name)

                # Actualizar BD
                Foto.objects.filter(pk=foto.pk).update(
                    imagen_mediana=medium_url,
                    imagen_miniatura=thumb_url,
                )

                regeneradas += 1

                if (i + 1) % 50 == 0:
                    self.stdout.write(f'    Progreso: {i+1}/{len(faltantes)} | Regeneradas: {regeneradas}')

            except Exception as e:
                errores += 1
                self.stdout.write(self.style.ERROR(f'    Error foto {foto.id}: {str(e)[:50]}'))

        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  COMPLETADO'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Regeneradas: {regeneradas:,}')
        self.stdout.write(f'  Errores: {errores:,}')
        self.stdout.write('')

    @staticmethod
    def _ensure_rgb(img):
        if img.mode in ("RGBA", "LA", "P"):
            base = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            alpha = img.split()[-1] if img.mode in ("RGBA", "LA") else None
            base.paste(img, mask=alpha)
            return base
        if img.mode != "RGB":
            return img.convert("RGB")
        return img

    def _resize_and_serialize(self, img, target_width, quality=85):
        if img.width > target_width:
            ratio = target_width / float(img.width)
            new_height = int(img.height * ratio)
            img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
        
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)
        return buffer

