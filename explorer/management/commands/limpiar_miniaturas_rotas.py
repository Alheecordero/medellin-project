"""
Limpia URLs de miniaturas que no existen en GCS.
Esto permite que el fallback a imagen original funcione correctamente.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from explorer.models import Foto


class Command(BaseCommand):
    help = "Limpia URLs de miniaturas/medianas que no existen en GCS"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Fotos a verificar por lote",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=10,
            help="Workers paralelos para verificación HTTP",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo mostrar, no modificar la BD",
        )
        parser.add_argument(
            "--fix-thumb",
            action="store_true",
            default=True,
            help="Limpiar miniaturas rotas (default: True)",
        )
        parser.add_argument(
            "--fix-medium",
            action="store_true",
            default=True,
            help="Limpiar medianas rotas (default: True)",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        workers = options["workers"]
        dry_run = options["dry_run"]
        fix_thumb = options["fix_thumb"]
        fix_medium = options["fix_medium"]

        self.stdout.write(f"Verificando miniaturas con {workers} workers...")

        # Obtener fotos con URLs de miniatura
        fotos_qs = Foto.objects.filter(
            imagen_miniatura__startswith='https://'
        ).values_list('id', 'imagen_miniatura', 'imagen_mediana')

        total = fotos_qs.count()
        self.stdout.write(f"Total fotos a verificar: {total}")

        broken_thumb_ids = []
        broken_medium_ids = []
        checked = 0

        def check_url(foto_data):
            fid, thumb_url, medium_url = foto_data
            results = {'id': fid, 'thumb_broken': False, 'medium_broken': False}
            
            # Verificar miniatura
            if thumb_url and fix_thumb:
                try:
                    r = requests.head(thumb_url, timeout=5)
                    if r.status_code != 200:
                        results['thumb_broken'] = True
                except:
                    results['thumb_broken'] = True

            # Verificar mediana
            if medium_url and fix_medium:
                try:
                    r = requests.head(medium_url, timeout=5)
                    if r.status_code != 200:
                        results['medium_broken'] = True
                except:
                    results['medium_broken'] = True

            return results

        # Procesar en lotes
        for offset in range(0, total, batch_size):
            batch = list(fotos_qs[offset:offset + batch_size])
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(check_url, f): f for f in batch}
                
                for future in as_completed(futures):
                    result = future.result()
                    if result['thumb_broken']:
                        broken_thumb_ids.append(result['id'])
                    if result['medium_broken']:
                        broken_medium_ids.append(result['id'])
                    checked += 1

            self.stdout.write(f"  Verificados: {checked}/{total} | Thumbs rotas: {len(broken_thumb_ids)} | Medianas rotas: {len(broken_medium_ids)}")

        self.stdout.write("")
        self.stdout.write(f"Resumen:")
        self.stdout.write(f"  - Miniaturas rotas: {len(broken_thumb_ids)}")
        self.stdout.write(f"  - Medianas rotas: {len(broken_medium_ids)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN: No se modificó la BD"))
            return

        # Limpiar miniaturas rotas
        if broken_thumb_ids and fix_thumb:
            updated = Foto.objects.filter(id__in=broken_thumb_ids).update(imagen_miniatura='')
            self.stdout.write(self.style.SUCCESS(f"✓ Limpiadas {updated} URLs de miniatura"))

        # Limpiar medianas rotas
        if broken_medium_ids and fix_medium:
            updated = Foto.objects.filter(id__in=broken_medium_ids).update(imagen_mediana='')
            self.stdout.write(self.style.SUCCESS(f"✓ Limpiadas {updated} URLs de mediana"))

        self.stdout.write(self.style.SUCCESS("✓ Limpieza completada"))


