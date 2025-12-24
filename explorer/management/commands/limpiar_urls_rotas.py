"""
Limpia URLs de miniatura/mediana que no existen en GCS.
Después puedes regenerarlas con imagenes_optimizar.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from django.db.models import Q
from explorer.models import Foto, Places
import time


class Command(BaseCommand):
    help = 'Limpia URLs de miniatura/mediana que devuelven 404'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se limpiaría, sin hacer cambios',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Tamaño de batch para verificación',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=30,
            help='Workers paralelos para verificación',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limitar número de fotos a procesar (0 = todas)',
        )

    def verificar_url(self, url):
        """Verifica si una URL existe (HEAD request)"""
        if not url or not url.startswith('http'):
            return None  # URL vacía o inválida
        try:
            r = requests.head(url, timeout=10, allow_redirects=True)
            return r.status_code == 200
        except:
            return False

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        workers = options['workers']
        limit = options['limit']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  LIMPIEZA DE URLs ROTAS'))
        self.stdout.write('=' * 70)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN: No se harán cambios'))
        self.stdout.write('')

        # Obtener fotos con miniatura o mediana
        fotos_query = Foto.objects.exclude(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).exclude(
            Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
        )

        if limit > 0:
            fotos_query = fotos_query[:limit]

        total_fotos = fotos_query.count()
        self.stdout.write(f'Fotos a verificar: {total_fotos:,}')
        self.stdout.write(f'Workers: {workers}')
        self.stdout.write(f'Batch size: {batch_size}')
        self.stdout.write('')

        # Contadores
        stats = {
            'verificadas': 0,
            'miniatura_ok': 0,
            'miniatura_rota': 0,
            'mediana_ok': 0,
            'mediana_rota': 0,
        }
        
        fotos_a_limpiar = []
        lugares_afectados = set()

        start_time = time.time()

        # Procesar en batches
        offset = 0
        while offset < total_fotos:
            batch = list(fotos_query[offset:offset + batch_size].values(
                'id', 'imagen_miniatura', 'imagen_mediana', 'lugar_id'
            ))
            
            if not batch:
                break

            def verificar_foto(foto):
                mini_ok = self.verificar_url(foto['imagen_miniatura'])
                med_ok = self.verificar_url(foto['imagen_mediana'])
                return {
                    'id': foto['id'],
                    'lugar_id': foto['lugar_id'],
                    'mini_ok': mini_ok,
                    'med_ok': med_ok,
                    'mini_url': foto['imagen_miniatura'],
                    'med_url': foto['imagen_mediana'],
                }

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(verificar_foto, f) for f in batch]
                
                for future in as_completed(futures):
                    r = future.result()
                    stats['verificadas'] += 1
                    
                    limpiar_mini = False
                    limpiar_med = False
                    
                    if r['mini_ok'] is True:
                        stats['miniatura_ok'] += 1
                    elif r['mini_ok'] is False:
                        stats['miniatura_rota'] += 1
                        limpiar_mini = True
                    
                    if r['med_ok'] is True:
                        stats['mediana_ok'] += 1
                    elif r['med_ok'] is False:
                        stats['mediana_rota'] += 1
                        limpiar_med = True
                    
                    if limpiar_mini or limpiar_med:
                        fotos_a_limpiar.append({
                            'id': r['id'],
                            'limpiar_mini': limpiar_mini,
                            'limpiar_med': limpiar_med,
                        })
                        lugares_afectados.add(r['lugar_id'])

            offset += batch_size
            elapsed = time.time() - start_time
            rate = stats['verificadas'] / elapsed if elapsed > 0 else 0
            eta = (total_fotos - stats['verificadas']) / rate if rate > 0 else 0
            
            self.stdout.write(
                f'  Progreso: {stats["verificadas"]:,}/{total_fotos:,} '
                f'({stats["verificadas"]*100/total_fotos:.1f}%) | '
                f'Rotas: {len(fotos_a_limpiar):,} | '
                f'ETA: {eta:.0f}s'
            )

        # ═══════════════════════════════════════════════════════════════
        # RESULTADOS
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESULTADOS'))
        self.stdout.write('=' * 70)
        
        self.stdout.write(f'  Fotos verificadas:      {stats["verificadas"]:,}')
        self.stdout.write('')
        self.stdout.write(f'  Miniaturas OK:          {stats["miniatura_ok"]:,}')
        self.stdout.write(f'  Miniaturas rotas:       {stats["miniatura_rota"]:,}')
        self.stdout.write(f'  Medianas OK:            {stats["mediana_ok"]:,}')
        self.stdout.write(f'  Medianas rotas:         {stats["mediana_rota"]:,}')
        self.stdout.write('')
        self.stdout.write(f'  Fotos a limpiar:        {len(fotos_a_limpiar):,}')
        self.stdout.write(f'  Lugares afectados:      {len(lugares_afectados):,}')

        # ═══════════════════════════════════════════════════════════════
        # LIMPIEZA
        # ═══════════════════════════════════════════════════════════════
        if fotos_a_limpiar:
            self.stdout.write('')
            self.stdout.write('=' * 70)
            
            if dry_run:
                self.stdout.write(self.style.WARNING('  DRY-RUN: Se limpiarían estas fotos:'))
                for foto in fotos_a_limpiar[:20]:
                    campos = []
                    if foto['limpiar_mini']:
                        campos.append('miniatura')
                    if foto['limpiar_med']:
                        campos.append('mediana')
                    self.stdout.write(f'    ID:{foto["id"]} -> limpiar: {", ".join(campos)}')
                if len(fotos_a_limpiar) > 20:
                    self.stdout.write(f'    ... y {len(fotos_a_limpiar) - 20} más')
            else:
                self.stdout.write(self.style.WARNING('  LIMPIANDO URLs ROTAS...'))
                
                limpiadas_mini = 0
                limpiadas_med = 0
                
                # Limpiar en batches
                for i in range(0, len(fotos_a_limpiar), 100):
                    batch = fotos_a_limpiar[i:i+100]
                    
                    ids_mini = [f['id'] for f in batch if f['limpiar_mini']]
                    ids_med = [f['id'] for f in batch if f['limpiar_med']]
                    
                    if ids_mini:
                        updated = Foto.objects.filter(id__in=ids_mini).update(
                            imagen_miniatura=None
                        )
                        limpiadas_mini += updated
                    
                    if ids_med:
                        updated = Foto.objects.filter(id__in=ids_med).update(
                            imagen_mediana=None
                        )
                        limpiadas_med += updated
                
                self.stdout.write(f'  Miniaturas limpiadas:   {limpiadas_mini:,}')
                self.stdout.write(f'  Medianas limpiadas:     {limpiadas_med:,}')
                
                # Marcar lugares como pendientes de optimización
                if lugares_afectados:
                    Places.objects.filter(id__in=lugares_afectados).update(
                        imagenes_optimizadas=False
                    )
                    self.stdout.write(f'  Lugares marcados como pendientes: {len(lugares_afectados):,}')

        # ═══════════════════════════════════════════════════════════════
        # SIGUIENTE PASO
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.HTTP_INFO('  SIGUIENTE PASO'))
        self.stdout.write('=' * 70)
        
        if dry_run:
            self.stdout.write('  Ejecuta sin --dry-run para limpiar las URLs rotas:')
            self.stdout.write('    python manage.py limpiar_urls_rotas')
        else:
            self.stdout.write('  URLs rotas limpiadas. Ahora regenera las variantes:')
            self.stdout.write('    python manage.py imagenes_optimizar --limit 1000')
        
        self.stdout.write('')

