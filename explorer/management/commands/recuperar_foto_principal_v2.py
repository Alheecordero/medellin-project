"""
Recupera variantes SOLO de la primera foto de cada lugar.
VERSION OPTIMIZADA: Precarga todas las fotos en memoria.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from django.db.models import Q
from explorer.models import Foto, Places
import time


class Command(BaseCommand):
    help = 'Recupera variantes solo de la primera foto de cada lugar (v2 optimizado)'

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
            default=50,
            help='Workers paralelos (default: 50)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo verificar, no actualizar BD',
        )

    def verificar_url(self, url):
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
        self.stdout.write(self.style.SUCCESS('  RECUPERAR FOTO PRINCIPAL (V2 OPTIMIZADO)'))
        self.stdout.write('=' * 70)
        self.stdout.write('')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN'))

        # 1. Obtener lugares pendientes
        self.stdout.write('  Cargando lugares pendientes...')
        lugares_query = Places.objects.filter(
            tiene_fotos=True,
            imagenes_optimizadas=False
        ).exclude(
            Q(slug__isnull=True) | Q(slug='')
        ).values('id', 'slug')

        if limit > 0:
            lugares_query = lugares_query[:limit]

        lugares_dict = {l['id']: l['slug'] for l in lugares_query}
        lugar_ids = list(lugares_dict.keys())
        total_lugares = len(lugar_ids)
        
        self.stdout.write(f'  Lugares pendientes: {total_lugares:,}')

        # 2. Precargar TODAS las primeras fotos en una sola query
        self.stdout.write('  Precargando primeras fotos...')
        
        # Subquery para obtener el ID mínimo de foto por lugar
        from django.db.models import Min
        
        fotos_ids = Foto.objects.filter(
            lugar_id__in=lugar_ids
        ).values('lugar_id').annotate(
            min_id=Min('id')
        ).values_list('min_id', flat=True)
        
        fotos = Foto.objects.filter(id__in=fotos_ids).values(
            'id', 'lugar_id', 'imagen_miniatura', 'imagen_mediana'
        )
        
        # Crear diccionario: lugar_id -> foto_data
        fotos_por_lugar = {f['lugar_id']: f for f in fotos}
        self.stdout.write(f'  Fotos precargadas: {len(fotos_por_lugar):,}')
        self.stdout.write('')

        # Base URL de GCS
        GCS_BASE = 'https://storage.googleapis.com/vivemedellin-bucket/tourism/images'

        stats = {
            'ya_tenia': 0,
            'mini_recuperada': 0,
            'mini_no_existe': 0,
            'med_recuperada': 0,
            'med_no_existe': 0,
        }
        
        fotos_a_actualizar = []
        lugares_necesitan_regenerar = []

        # 3. Preparar datos para verificación paralela
        tareas = []
        for lugar_id in lugar_ids:
            if lugar_id not in fotos_por_lugar:
                continue
            
            foto = fotos_por_lugar[lugar_id]
            slug = lugares_dict[lugar_id]
            
            # Si ya tiene ambas, skip
            if foto['imagen_miniatura'] and foto['imagen_mediana']:
                stats['ya_tenia'] += 1
                continue
            
            tareas.append({
                'foto_id': foto['id'],
                'lugar_id': lugar_id,
                'slug': slug,
                'tiene_mini': bool(foto['imagen_miniatura']),
                'tiene_med': bool(foto['imagen_mediana']),
            })
        
        self.stdout.write(f'  Ya tenían variantes: {stats["ya_tenia"]:,}')
        self.stdout.write(f'  Tareas a verificar: {len(tareas):,}')
        self.stdout.write('')

        def verificar_tarea(tarea):
            slug = tarea['slug']
            foto_id = tarea['foto_id']
            
            resultado = {
                'foto_id': foto_id,
                'lugar_id': tarea['lugar_id'],
                'slug': slug,
                'mini_url': None,
                'med_url': None,
                'necesita_regenerar': False,
            }
            
            # Verificar miniatura
            if not tarea['tiene_mini']:
                url_mini = f'{GCS_BASE}/thumb/{slug}/{foto_id}.jpg'
                if self.verificar_url(url_mini):
                    resultado['mini_url'] = url_mini
                else:
                    resultado['necesita_regenerar'] = True
            
            # Verificar mediana
            if not tarea['tiene_med']:
                url_med = f'{GCS_BASE}/medium/{slug}/{foto_id}.jpg'
                if self.verificar_url(url_med):
                    resultado['med_url'] = url_med
                else:
                    resultado['necesita_regenerar'] = True
            
            return resultado

        # 4. Ejecutar verificaciones en paralelo
        start_time = time.time()
        procesados = 0
        total_tareas = len(tareas)

        if total_tareas == 0:
            self.stdout.write(self.style.SUCCESS('  ✅ No hay tareas pendientes!'))
            return

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(verificar_tarea, t): t for t in tareas}
            
            for future in as_completed(futures):
                procesados += 1
                r = future.result()
                
                if r['mini_url']:
                    stats['mini_recuperada'] += 1
                else:
                    stats['mini_no_existe'] += 1
                
                if r['med_url']:
                    stats['med_recuperada'] += 1
                else:
                    stats['med_no_existe'] += 1
                
                if r['mini_url'] or r['med_url']:
                    fotos_a_actualizar.append(r)
                
                if r['necesita_regenerar']:
                    lugares_necesitan_regenerar.append({
                        'lugar_id': r['lugar_id'],
                        'slug': r['slug'],
                        'foto_id': r['foto_id'],
                    })
                
                if procesados % 500 == 0 or procesados == total_tareas:
                    elapsed = time.time() - start_time
                    rate = procesados / elapsed if elapsed > 0 else 0
                    eta = (total_tareas - procesados) / rate if rate > 0 else 0
                    self.stdout.write(
                        f'  Progreso: {procesados:,}/{total_tareas:,} | '
                        f'Recuperadas: {stats["mini_recuperada"]:,} | '
                        f'Faltan: {stats["mini_no_existe"]:,} | '
                        f'ETA: {eta:.0f}s'
                    )

        # 5. Resultados
        elapsed_total = time.time() - start_time
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESULTADOS'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Tiempo total:               {elapsed_total:.1f}s')
        self.stdout.write(f'  Lugares procesados:         {total_lugares:,}')
        self.stdout.write(f'  Ya tenían variantes:        {stats["ya_tenia"]:,}')
        self.stdout.write('')
        self.stdout.write(f'  Miniaturas recuperadas:     {stats["mini_recuperada"]:,}')
        self.stdout.write(f'  Miniaturas no existen:      {stats["mini_no_existe"]:,}')
        self.stdout.write(f'  Medianas recuperadas:       {stats["med_recuperada"]:,}')
        self.stdout.write(f'  Medianas no existen:        {stats["med_no_existe"]:,}')
        self.stdout.write('')
        self.stdout.write(f'  Fotos a actualizar en BD:   {len(fotos_a_actualizar):,}')

        # 6. Actualizar BD
        if fotos_a_actualizar and not dry_run:
            self.stdout.write('')
            self.stdout.write('Actualizando BD...')
            
            actualizadas = 0
            for r in fotos_a_actualizar:
                updates = {}
                if r['mini_url']:
                    updates['imagen_miniatura'] = r['mini_url']
                if r['med_url']:
                    updates['imagen_mediana'] = r['med_url']
                
                if updates:
                    Foto.objects.filter(id=r['foto_id']).update(**updates)
                    actualizadas += 1
                    
                    # Si tiene ambas, marcar lugar como optimizado
                    if r['mini_url'] and r['med_url']:
                        Places.objects.filter(id=r['lugar_id']).update(
                            imagenes_optimizadas=True
                        )
            
            self.stdout.write(self.style.SUCCESS(f'✅ Actualizadas {actualizadas:,} fotos'))

        # 7. Resumen final
        self.stdout.write('')
        self.stdout.write('=' * 70)
        
        if lugares_necesitan_regenerar:
            self.stdout.write(self.style.WARNING(
                f'  ⚠️  {len(lugares_necesitan_regenerar):,} LUGARES NECESITAN REGENERAR'
            ))
            self.stdout.write('')
            self.stdout.write('  Ejemplos (primeros 5):')
            for l in lugares_necesitan_regenerar[:5]:
                self.stdout.write(f"    - {l['slug']} (foto ID: {l['foto_id']})")
            
            self.stdout.write('')
            self.stdout.write('  Para regenerar:')
            self.stdout.write('    python manage.py imagenes_optimizar --limit 500')
        else:
            self.stdout.write(self.style.SUCCESS(
                '  ✅ Todos los lugares tienen su foto principal!'
            ))
        
        self.stdout.write('')

