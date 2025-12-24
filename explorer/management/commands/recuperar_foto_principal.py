"""
Recupera/genera variantes SOLO de la primera foto de cada lugar.
Para las cards solo necesitamos 1 miniatura y 1 mediana por lugar.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from django.db.models import Q, Min
from explorer.models import Foto, Places
import time


class Command(BaseCommand):
    help = 'Recupera variantes solo de la primera foto de cada lugar'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Número de lugares a procesar (0 = todos)',
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
        self.stdout.write(self.style.SUCCESS('  RECUPERAR FOTO PRINCIPAL DE CADA LUGAR'))
        self.stdout.write('=' * 70)
        self.stdout.write('')
        self.stdout.write('  Solo procesamos 1 foto por lugar (para las cards)')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN'))
        self.stdout.write('')

        # Lugares pendientes de optimizar
        lugares_query = Places.objects.filter(
            tiene_fotos=True,
            imagenes_optimizadas=False
        ).exclude(
            Q(slug__isnull=True) | Q(slug='')
        )

        if limit > 0:
            lugares_query = lugares_query[:limit]

        lugares = list(lugares_query.values('id', 'slug'))
        total_lugares = len(lugares)
        
        self.stdout.write(f'Lugares a procesar: {total_lugares:,}')
        self.stdout.write('')

        # Base URL de GCS
        GCS_BASE = 'https://storage.googleapis.com/vivemedellin-bucket/tourism/images'

        stats = {
            'mini_recuperada': 0,
            'mini_no_existe': 0,
            'med_recuperada': 0,
            'med_no_existe': 0,
            'ya_tenia': 0,
        }
        
        fotos_a_actualizar = []
        lugares_necesitan_regenerar = []

        def procesar_lugar(lugar):
            slug = lugar['slug']
            lugar_id = lugar['id']
            
            # Obtener la primera foto del lugar
            primera_foto = Foto.objects.filter(lugar_id=lugar_id).order_by('id').first()
            
            if not primera_foto:
                return None
            
            resultado = {
                'foto_id': primera_foto.id,
                'lugar_id': lugar_id,
                'slug': slug,
                'mini_url': None,
                'med_url': None,
                'ya_tiene_mini': bool(primera_foto.imagen_miniatura),
                'ya_tiene_med': bool(primera_foto.imagen_mediana),
                'necesita_regenerar': False,
            }
            
            # Si ya tiene ambas, no hacer nada
            if primera_foto.imagen_miniatura and primera_foto.imagen_mediana:
                resultado['ya_tenia'] = True
                return resultado
            
            # Construir URLs esperadas
            url_mini = f'{GCS_BASE}/thumb/{slug}/{primera_foto.id}.jpg'
            url_med = f'{GCS_BASE}/medium/{slug}/{primera_foto.id}.jpg'
            
            # Verificar miniatura
            if not primera_foto.imagen_miniatura:
                if self.verificar_url(url_mini):
                    resultado['mini_url'] = url_mini
                else:
                    resultado['necesita_regenerar'] = True
            
            # Verificar mediana
            if not primera_foto.imagen_mediana:
                if self.verificar_url(url_med):
                    resultado['med_url'] = url_med
                else:
                    resultado['necesita_regenerar'] = True
            
            return resultado

        start_time = time.time()
        procesados = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(procesar_lugar, l): l for l in lugares}
            
            for future in as_completed(futures):
                procesados += 1
                r = future.result()
                
                if r is None:
                    continue
                
                if r.get('ya_tenia'):
                    stats['ya_tenia'] += 1
                    continue
                
                if r['mini_url']:
                    stats['mini_recuperada'] += 1
                elif not r['ya_tiene_mini']:
                    stats['mini_no_existe'] += 1
                
                if r['med_url']:
                    stats['med_recuperada'] += 1
                elif not r['ya_tiene_med']:
                    stats['med_no_existe'] += 1
                
                if r['mini_url'] or r['med_url']:
                    fotos_a_actualizar.append(r)
                
                if r['necesita_regenerar']:
                    lugares_necesitan_regenerar.append({
                        'lugar_id': r['lugar_id'],
                        'slug': r['slug'],
                        'foto_id': r['foto_id'],
                    })
                
                if procesados % 500 == 0:
                    elapsed = time.time() - start_time
                    rate = procesados / elapsed if elapsed > 0 else 0
                    eta = (total_lugares - procesados) / rate if rate > 0 else 0
                    self.stdout.write(
                        f'  Progreso: {procesados:,}/{total_lugares:,} | '
                        f'Recuperadas: {stats["mini_recuperada"]:,} | '
                        f'Faltan: {len(lugares_necesitan_regenerar):,} | '
                        f'ETA: {eta:.0f}s'
                    )

        # Resultados
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESULTADOS'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Lugares procesados:         {total_lugares:,}')
        self.stdout.write(f'  Ya tenían variantes:        {stats["ya_tenia"]:,}')
        self.stdout.write('')
        self.stdout.write(f'  Miniaturas recuperadas:     {stats["mini_recuperada"]:,}')
        self.stdout.write(f'  Miniaturas no existen:      {stats["mini_no_existe"]:,}')
        self.stdout.write(f'  Medianas recuperadas:       {stats["med_recuperada"]:,}')
        self.stdout.write(f'  Medianas no existen:        {stats["med_no_existe"]:,}')
        self.stdout.write('')
        self.stdout.write(f'  Fotos a actualizar en BD:   {len(fotos_a_actualizar):,}')
        self.stdout.write(self.style.WARNING(
            f'  Lugares que necesitan regenerar: {len(lugares_necesitan_regenerar):,}'
        ))

        # Actualizar BD
        if fotos_a_actualizar and not dry_run:
            self.stdout.write('')
            self.stdout.write('Actualizando BD...')
            
            actualizadas = 0
            for r in fotos_a_actualizar:
                updated_fields = []
                
                if r['mini_url']:
                    Foto.objects.filter(id=r['foto_id']).update(
                        imagen_miniatura=r['mini_url']
                    )
                    updated_fields.append('miniatura')
                
                if r['med_url']:
                    Foto.objects.filter(id=r['foto_id']).update(
                        imagen_mediana=r['med_url']
                    )
                    updated_fields.append('mediana')
                
                if updated_fields:
                    actualizadas += 1
                    
                    # Si tiene ambas, marcar lugar como optimizado
                    foto = Foto.objects.get(id=r['foto_id'])
                    if foto.imagen_miniatura and foto.imagen_mediana:
                        Places.objects.filter(id=r['lugar_id']).update(
                            imagenes_optimizadas=True
                        )
            
            self.stdout.write(self.style.SUCCESS(f'✅ Actualizadas {actualizadas:,} fotos'))

        # Mostrar lugares que faltan
        self.stdout.write('')
        self.stdout.write('=' * 70)
        
        if lugares_necesitan_regenerar:
            self.stdout.write(self.style.WARNING(
                f'  ⚠️  {len(lugares_necesitan_regenerar):,} LUGARES NECESITAN REGENERAR'
            ))
            self.stdout.write('')
            self.stdout.write('  Ejemplos (primeros 10):')
            for l in lugares_necesitan_regenerar[:10]:
                self.stdout.write(f"    - {l['slug']} (foto ID: {l['foto_id']})")
            
            self.stdout.write('')
            self.stdout.write('  Para regenerar las faltantes:')
            self.stdout.write('    python manage.py imagenes_optimizar --limit 500')
        else:
            self.stdout.write(self.style.SUCCESS(
                '  ✅ Todos los lugares tienen su foto principal con variantes!'
            ))
        
        self.stdout.write('')

