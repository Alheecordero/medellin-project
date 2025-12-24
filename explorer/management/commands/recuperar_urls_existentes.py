"""
Recupera URLs de variantes que YA existen en GCS sin regenerarlas.
Solo regenera las que realmente faltan.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from django.db.models import Q
from explorer.models import Foto, Places
import time


class Command(BaseCommand):
    help = 'Recupera URLs de variantes existentes en GCS sin regenerarlas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='Número de fotos a procesar',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=30,
            help='Workers paralelos',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo verificar, no actualizar BD',
        )

    def verificar_url(self, url):
        """Verifica si una URL existe"""
        try:
            r = requests.head(url, timeout=10, allow_redirects=True)
            return r.status_code == 200
        except:
            return False

    def handle(self, *args, **options):
        limit = options['limit']
        workers = options['workers']
        dry_run = options['dry_run']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RECUPERAR URLs EXISTENTES EN GCS'))
        self.stdout.write('=' * 70)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN'))
        self.stdout.write('')

        # Fotos sin miniatura o mediana
        fotos_query = Foto.objects.filter(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='') |
            Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
        ).select_related('lugar').exclude(
            Q(lugar__slug__isnull=True) | Q(lugar__slug='')
        )

        if limit > 0:
            fotos_query = fotos_query[:limit]

        fotos = list(fotos_query)
        total = len(fotos)
        
        self.stdout.write(f'Fotos a verificar: {total:,}')
        self.stdout.write('')

        # Base URL de GCS
        GCS_BASE = 'https://storage.googleapis.com/vivemedellin-bucket/tourism/images'

        stats = {
            'mini_recuperada': 0,
            'mini_no_existe': 0,
            'med_recuperada': 0,
            'med_no_existe': 0,
        }
        
        fotos_a_actualizar = []
        lugares_pendientes = set()

        def verificar_foto(foto):
            slug = foto.lugar.slug
            foto_id = foto.id
            
            # Construir URLs esperadas
            url_mini = f'{GCS_BASE}/thumb/{slug}/{foto_id}.jpg'
            url_med = f'{GCS_BASE}/medium/{slug}/{foto_id}.jpg'
            
            resultado = {
                'id': foto_id,
                'lugar_id': foto.lugar_id,
                'mini_url': None,
                'med_url': None,
                'necesita_regenerar': False,
            }
            
            # Verificar miniatura
            if not foto.imagen_miniatura:
                if self.verificar_url(url_mini):
                    resultado['mini_url'] = url_mini
                else:
                    resultado['necesita_regenerar'] = True
            
            # Verificar mediana
            if not foto.imagen_mediana:
                if self.verificar_url(url_med):
                    resultado['med_url'] = url_med
                else:
                    resultado['necesita_regenerar'] = True
            
            return resultado

        start_time = time.time()
        procesadas = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(verificar_foto, f): f for f in fotos}
            
            for future in as_completed(futures):
                procesadas += 1
                r = future.result()
                
                if r['mini_url']:
                    stats['mini_recuperada'] += 1
                elif not fotos_query[0].imagen_miniatura:  # Si no tenía miniatura
                    stats['mini_no_existe'] += 1
                
                if r['med_url']:
                    stats['med_recuperada'] += 1
                elif not fotos_query[0].imagen_mediana:  # Si no tenía mediana
                    stats['med_no_existe'] += 1
                
                if r['mini_url'] or r['med_url']:
                    fotos_a_actualizar.append(r)
                
                if r['necesita_regenerar']:
                    lugares_pendientes.add(r['lugar_id'])
                
                if procesadas % 200 == 0:
                    elapsed = time.time() - start_time
                    rate = procesadas / elapsed if elapsed > 0 else 0
                    eta = (total - procesadas) / rate if rate > 0 else 0
                    self.stdout.write(
                        f'  Progreso: {procesadas:,}/{total:,} | '
                        f'Recuperadas: {len(fotos_a_actualizar):,} | '
                        f'ETA: {eta:.0f}s'
                    )

        # Resultados
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESULTADOS'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Fotos verificadas:          {total:,}')
        self.stdout.write('')
        self.stdout.write(f'  Miniaturas recuperadas:     {stats["mini_recuperada"]:,}')
        self.stdout.write(f'  Miniaturas no existen:      {stats["mini_no_existe"]:,}')
        self.stdout.write(f'  Medianas recuperadas:       {stats["med_recuperada"]:,}')
        self.stdout.write(f'  Medianas no existen:        {stats["med_no_existe"]:,}')
        self.stdout.write('')
        self.stdout.write(f'  Fotos a actualizar en BD:   {len(fotos_a_actualizar):,}')
        self.stdout.write(f'  Lugares que necesitan regenerar: {len(lugares_pendientes):,}')

        # Actualizar BD
        if fotos_a_actualizar and not dry_run:
            self.stdout.write('')
            self.stdout.write('Actualizando BD...')
            
            actualizadas = 0
            for r in fotos_a_actualizar:
                foto = Foto.objects.get(id=r['id'])
                changed = False
                
                if r['mini_url'] and not foto.imagen_miniatura:
                    foto.imagen_miniatura = r['mini_url']
                    changed = True
                
                if r['med_url'] and not foto.imagen_mediana:
                    foto.imagen_mediana = r['med_url']
                    changed = True
                
                if changed:
                    foto.save(update_fields=['imagen_miniatura', 'imagen_mediana'])
                    actualizadas += 1
            
            self.stdout.write(self.style.SUCCESS(f'✅ Actualizadas {actualizadas:,} fotos'))
            
            # Marcar lugares como optimizados si todas sus fotos tienen variantes
            lugares_completos = 0
            for lugar_id in set(r['lugar_id'] for r in fotos_a_actualizar):
                fotos_lugar = Foto.objects.filter(lugar_id=lugar_id)
                todas_completas = not fotos_lugar.filter(
                    Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='') |
                    Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
                ).exists()
                
                if todas_completas:
                    Places.objects.filter(id=lugar_id).update(imagenes_optimizadas=True)
                    lugares_completos += 1
            
            self.stdout.write(f'✅ Lugares marcados como completos: {lugares_completos:,}')

        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.HTTP_INFO('  SIGUIENTE PASO'))
        self.stdout.write('=' * 70)
        
        if lugares_pendientes:
            self.stdout.write(f'  {len(lugares_pendientes):,} lugares necesitan regenerar variantes:')
            self.stdout.write('    python manage.py imagenes_optimizar --limit 500')
        else:
            self.stdout.write('  ✅ Todas las variantes fueron recuperadas!')
        
        self.stdout.write('')

