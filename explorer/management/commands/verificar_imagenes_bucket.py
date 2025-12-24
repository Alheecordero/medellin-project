"""
Verifica que las URLs de imágenes en la BD realmente existan en GCS.
Detecta discrepancias entre la BD y el bucket.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from django.db.models import Q
from explorer.models import Foto
import time


class Command(BaseCommand):
    help = 'Verifica que las URLs de imágenes en la BD existan realmente en GCS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='Número de fotos a verificar (0 = todas)',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=20,
            help='Workers paralelos para verificación',
        )
        parser.add_argument(
            '--tipo',
            type=str,
            choices=['original', 'miniatura', 'mediana', 'todas'],
            default='todas',
            help='Tipo de imagen a verificar',
        )
        parser.add_argument(
            '--solo-errores',
            action='store_true',
            help='Solo mostrar fotos con errores',
        )
        parser.add_argument(
            '--exportar',
            type=str,
            default='',
            help='Exportar IDs de fotos con errores a un archivo',
        )
        parser.add_argument(
            '--offset',
            type=int,
            default=0,
            help='Offset para continuar verificación',
        )

    def verificar_url(self, url):
        """Verifica si una URL existe (HEAD request)"""
        if not url or not url.startswith('http'):
            return {'existe': False, 'status': 'URL_INVALIDA', 'url': url}
        
        try:
            r = requests.head(url, timeout=10, allow_redirects=True)
            return {
                'existe': r.status_code == 200,
                'status': r.status_code,
                'url': url
            }
        except requests.exceptions.Timeout:
            return {'existe': False, 'status': 'TIMEOUT', 'url': url}
        except requests.exceptions.ConnectionError:
            return {'existe': False, 'status': 'CONNECTION_ERROR', 'url': url}
        except Exception as e:
            return {'existe': False, 'status': f'ERROR: {str(e)[:30]}', 'url': url}

    def handle(self, *args, **options):
        limit = options['limit']
        workers = options['workers']
        tipo = options['tipo']
        solo_errores = options['solo_errores']
        exportar = options['exportar']
        offset = options['offset']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  VERIFICACIÓN DE IMÁGENES EN BUCKET'))
        self.stdout.write('=' * 70)
        self.stdout.write('')

        # Obtener fotos
        fotos_query = Foto.objects.all().order_by('id')
        
        if offset > 0:
            fotos_query = fotos_query.filter(id__gt=offset)
        
        if limit > 0:
            fotos_query = fotos_query[:limit]
        
        fotos = list(fotos_query.values(
            'id', 'imagen', 'imagen_miniatura', 'imagen_mediana', 'lugar_id'
        ))
        
        total = len(fotos)
        self.stdout.write(f'Verificando {total:,} fotos...')
        self.stdout.write(f'Tipo: {tipo}')
        self.stdout.write(f'Workers: {workers}')
        self.stdout.write('')

        # Contadores
        stats = {
            'original': {'ok': 0, 'error': 0, 'vacia': 0},
            'miniatura': {'ok': 0, 'error': 0, 'vacia': 0},
            'mediana': {'ok': 0, 'error': 0, 'vacia': 0},
        }
        
        errores = []
        
        def verificar_foto(foto):
            resultado = {'id': foto['id'], 'lugar_id': foto['lugar_id'], 'errores': []}
            
            campos = []
            if tipo in ['original', 'todas']:
                campos.append(('original', foto['imagen']))
            if tipo in ['miniatura', 'todas']:
                campos.append(('miniatura', foto['imagen_miniatura']))
            if tipo in ['mediana', 'todas']:
                campos.append(('mediana', foto['imagen_mediana']))
            
            for campo, url in campos:
                if not url:
                    resultado[campo] = {'existe': None, 'status': 'VACIA'}
                else:
                    resultado[campo] = self.verificar_url(url)
                    if not resultado[campo]['existe']:
                        resultado['errores'].append({
                            'campo': campo,
                            'url': url,
                            'status': resultado[campo]['status']
                        })
            
            return resultado

        start_time = time.time()
        procesadas = 0
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(verificar_foto, f): f for f in fotos}
            
            for future in as_completed(futures):
                procesadas += 1
                resultado = future.result()
                
                # Actualizar stats
                for campo in ['original', 'miniatura', 'mediana']:
                    if campo in resultado:
                        if resultado[campo]['status'] == 'VACIA':
                            stats[campo]['vacia'] += 1
                        elif resultado[campo]['existe']:
                            stats[campo]['ok'] += 1
                        else:
                            stats[campo]['error'] += 1
                
                # Guardar errores
                if resultado['errores']:
                    errores.append(resultado)
                
                # Progreso cada 100
                if procesadas % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = procesadas / elapsed if elapsed > 0 else 0
                    eta = (total - procesadas) / rate if rate > 0 else 0
                    self.stdout.write(
                        f'  Progreso: {procesadas:,}/{total:,} '
                        f'({procesadas*100/total:.1f}%) - '
                        f'Errores: {len(errores):,} - '
                        f'ETA: {eta:.0f}s'
                    )

        elapsed = time.time() - start_time
        
        # ═══════════════════════════════════════════════════════════════
        # RESULTADOS
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESULTADOS'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Tiempo total: {elapsed:.1f}s')
        self.stdout.write(f'  Fotos verificadas: {total:,}')
        self.stdout.write('')
        
        self.stdout.write('  IMAGEN ORIGINAL:')
        self.stdout.write(f'    ✅ OK:       {stats["original"]["ok"]:,}')
        self.stdout.write(f'    ❌ Error:    {stats["original"]["error"]:,}')
        self.stdout.write(f'    ⬜ Vacía:    {stats["original"]["vacia"]:,}')
        self.stdout.write('')
        
        self.stdout.write('  MINIATURA:')
        self.stdout.write(f'    ✅ OK:       {stats["miniatura"]["ok"]:,}')
        self.stdout.write(f'    ❌ Error:    {stats["miniatura"]["error"]:,}')
        self.stdout.write(f'    ⬜ Vacía:    {stats["miniatura"]["vacia"]:,}')
        self.stdout.write('')
        
        self.stdout.write('  MEDIANA:')
        self.stdout.write(f'    ✅ OK:       {stats["mediana"]["ok"]:,}')
        self.stdout.write(f'    ❌ Error:    {stats["mediana"]["error"]:,}')
        self.stdout.write(f'    ⬜ Vacía:    {stats["mediana"]["vacia"]:,}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # ERRORES DETALLADOS
        # ═══════════════════════════════════════════════════════════════
        if errores:
            self.stdout.write('=' * 70)
            self.stdout.write(self.style.ERROR(f'  FOTOS CON ERRORES: {len(errores):,}'))
            self.stdout.write('=' * 70)
            
            # Agrupar por tipo de error
            errores_por_tipo = {}
            for e in errores:
                for err in e['errores']:
                    key = f"{err['campo']}:{err['status']}"
                    if key not in errores_por_tipo:
                        errores_por_tipo[key] = []
                    errores_por_tipo[key].append({
                        'foto_id': e['id'],
                        'lugar_id': e['lugar_id'],
                        'url': err['url']
                    })
            
            self.stdout.write('')
            self.stdout.write('  Errores agrupados por tipo:')
            for key, items in sorted(errores_por_tipo.items(), key=lambda x: -len(x[1])):
                self.stdout.write(f'    {key}: {len(items):,}')
            
            # Mostrar ejemplos
            self.stdout.write('')
            self.stdout.write('  Ejemplos de errores (primeros 20):')
            for e in errores[:20]:
                self.stdout.write(f'    Foto ID: {e["id"]} | Lugar ID: {e["lugar_id"]}')
                for err in e['errores']:
                    url_short = err['url'][:70] + '...' if len(err['url']) > 70 else err['url']
                    self.stdout.write(f'      [{err["campo"]}] {err["status"]}: {url_short}')
            
            # Exportar si se pidió
            if exportar:
                with open(exportar, 'w') as f:
                    f.write('foto_id,lugar_id,campo,status,url\n')
                    for e in errores:
                        for err in e['errores']:
                            f.write(f'{e["id"]},{e["lugar_id"]},{err["campo"]},{err["status"]},"{err["url"]}"\n')
                self.stdout.write(self.style.SUCCESS(f'\n  Errores exportados a: {exportar}'))
        else:
            self.stdout.write(self.style.SUCCESS('\n  ✅ No se encontraron errores'))

        # ═══════════════════════════════════════════════════════════════
        # ANÁLISIS DE URLs
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.HTTP_INFO('  ANÁLISIS DE PATRONES DE URLs CON ERROR'))
        self.stdout.write('=' * 70)
        
        if errores:
            # Analizar patrones en URLs con error
            patrones = {}
            for e in errores:
                for err in e['errores']:
                    url = err['url']
                    # Extraer patrón base
                    if 'storage.googleapis.com' in url:
                        parts = url.split('/')
                        if len(parts) >= 5:
                            # bucket/carpeta/subcarpeta
                            patron = '/'.join(parts[3:6]) if len(parts) >= 6 else '/'.join(parts[3:])
                            if patron not in patrones:
                                patrones[patron] = 0
                            patrones[patron] += 1
            
            self.stdout.write('  Patrones de URLs con error:')
            for patron, count in sorted(patrones.items(), key=lambda x: -x[1])[:15]:
                self.stdout.write(f'    {count:,}: {patron}')
        
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  FIN DE VERIFICACIÓN'))
        self.stdout.write('=' * 70)

