"""
Diagnóstico completo de URLs en BD vs existencia real en GCS.
Identifica patrones de URLs rotas y propone soluciones.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from explorer.models import Foto, Places
from collections import defaultdict
import re
import time


class Command(BaseCommand):
    help = 'Diagnostica discrepancias entre URLs en BD y archivos en GCS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sample',
            type=int,
            default=100,
            help='Número de fotos a verificar por categoría',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=20,
            help='Workers paralelos',
        )

    def verificar_url(self, url):
        """Verifica si una URL existe"""
        if not url or not url.startswith('http'):
            return None
        try:
            r = requests.head(url, timeout=10, allow_redirects=True)
            return r.status_code
        except:
            return 0

    def handle(self, *args, **options):
        sample = options['sample']
        workers = options['workers']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  DIAGNÓSTICO DE URLs BD vs GCS'))
        self.stdout.write('=' * 70)
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 1. ANÁLISIS DE ESTRUCTURA DE URLs
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('1️⃣  ANÁLISIS DE ESTRUCTURA DE URLs'))
        self.stdout.write('-' * 50)

        # Analizar patrones de URLs
        patrones_original = defaultdict(int)
        patrones_mini = defaultdict(int)
        patrones_med = defaultdict(int)
        
        ejemplos = {'original': [], 'miniatura': [], 'mediana': []}

        for foto in Foto.objects.all()[:5000]:
            # Original
            if foto.imagen:
                if 'storage.googleapis.com' in foto.imagen:
                    # Extraer estructura: bucket/carpeta/subcarpeta
                    match = re.search(r'googleapis\.com/([^/]+)/([^/]+)/([^/]+)', foto.imagen)
                    if match:
                        patron = f'{match.group(1)}/{match.group(2)}/{match.group(3)[:20]}...'
                        patrones_original[patron] += 1
                        if len(ejemplos['original']) < 3:
                            ejemplos['original'].append(foto.imagen)
                else:
                    patrones_original['NO-GCS'] += 1

            # Miniatura
            if foto.imagen_miniatura:
                if 'storage.googleapis.com' in foto.imagen_miniatura:
                    match = re.search(r'googleapis\.com/([^/]+)/([^/]+)/([^/]+)', foto.imagen_miniatura)
                    if match:
                        patron = f'{match.group(1)}/{match.group(2)}/{match.group(3)[:20]}...'
                        patrones_mini[patron] += 1
                        if len(ejemplos['miniatura']) < 3:
                            ejemplos['miniatura'].append(foto.imagen_miniatura)
                else:
                    patrones_mini['NO-GCS'] += 1

            # Mediana
            if foto.imagen_mediana:
                if 'storage.googleapis.com' in foto.imagen_mediana:
                    match = re.search(r'googleapis\.com/([^/]+)/([^/]+)/([^/]+)', foto.imagen_mediana)
                    if match:
                        patron = f'{match.group(1)}/{match.group(2)}/{match.group(3)[:20]}...'
                        patrones_med[patron] += 1
                        if len(ejemplos['mediana']) < 3:
                            ejemplos['mediana'].append(foto.imagen_mediana)
                else:
                    patrones_med['NO-GCS'] += 1

        self.stdout.write('\n  PATRONES EN CAMPO "imagen" (original):')
        for patron, count in sorted(patrones_original.items(), key=lambda x: -x[1])[:10]:
            self.stdout.write(f'    {count:,}: {patron}')

        self.stdout.write('\n  PATRONES EN CAMPO "imagen_miniatura":')
        for patron, count in sorted(patrones_mini.items(), key=lambda x: -x[1])[:10]:
            self.stdout.write(f'    {count:,}: {patron}')

        self.stdout.write('\n  PATRONES EN CAMPO "imagen_mediana":')
        for patron, count in sorted(patrones_med.items(), key=lambda x: -x[1])[:10]:
            self.stdout.write(f'    {count:,}: {patron}')

        self.stdout.write('\n  EJEMPLOS DE URLs:')
        for tipo, urls in ejemplos.items():
            self.stdout.write(f'\n    {tipo.upper()}:')
            for url in urls:
                self.stdout.write(f'      {url}')

        # ═══════════════════════════════════════════════════════════════
        # 2. VERIFICACIÓN DE EXISTENCIA EN GCS
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('2️⃣  VERIFICACIÓN DE EXISTENCIA EN GCS'))
        self.stdout.write('-' * 50)
        self.stdout.write(f'  Verificando muestra de {sample} fotos...')

        # Tomar muestra aleatoria
        fotos_sample = list(Foto.objects.order_by('?')[:sample].values(
            'id', 'imagen', 'imagen_miniatura', 'imagen_mediana', 'lugar_id'
        ))

        resultados = {
            'original': {'ok': 0, 'error': 0, 'vacia': 0, 'errores': []},
            'miniatura': {'ok': 0, 'error': 0, 'vacia': 0, 'errores': []},
            'mediana': {'ok': 0, 'error': 0, 'vacia': 0, 'errores': []},
        }

        def verificar_foto(foto):
            return {
                'id': foto['id'],
                'original': self.verificar_url(foto['imagen']),
                'miniatura': self.verificar_url(foto['imagen_miniatura']),
                'mediana': self.verificar_url(foto['imagen_mediana']),
                'urls': {
                    'original': foto['imagen'],
                    'miniatura': foto['imagen_miniatura'],
                    'mediana': foto['imagen_mediana'],
                }
            }

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(verificar_foto, f) for f in fotos_sample]
            
            for future in as_completed(futures):
                r = future.result()
                
                for tipo in ['original', 'miniatura', 'mediana']:
                    status = r[tipo]
                    if status is None:
                        resultados[tipo]['vacia'] += 1
                    elif status == 200:
                        resultados[tipo]['ok'] += 1
                    else:
                        resultados[tipo]['error'] += 1
                        if len(resultados[tipo]['errores']) < 5:
                            resultados[tipo]['errores'].append({
                                'id': r['id'],
                                'status': status,
                                'url': r['urls'][tipo]
                            })

        self.stdout.write('')
        for tipo in ['original', 'miniatura', 'mediana']:
            r = resultados[tipo]
            total_verificadas = r['ok'] + r['error']
            pct_ok = (r['ok'] / total_verificadas * 100) if total_verificadas > 0 else 0
            pct_error = (r['error'] / total_verificadas * 100) if total_verificadas > 0 else 0
            
            self.stdout.write(f'  {tipo.upper()}:')
            self.stdout.write(f'    ✅ Existen:    {r["ok"]:,} ({pct_ok:.1f}%)')
            self.stdout.write(f'    ❌ No existen: {r["error"]:,} ({pct_error:.1f}%)')
            self.stdout.write(f'    ⬜ Vacías:     {r["vacia"]:,}')
            
            if r['errores']:
                self.stdout.write(f'    Ejemplos de errores:')
                for err in r['errores'][:3]:
                    self.stdout.write(f'      ID:{err["id"]} [{err["status"]}] {err["url"][:60]}...')
            self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 3. DIAGNÓSTICO Y RECOMENDACIONES
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('3️⃣  DIAGNÓSTICO'))
        self.stdout.write('-' * 50)

        total_errores = sum(resultados[t]['error'] for t in ['original', 'miniatura', 'mediana'])
        total_ok = sum(resultados[t]['ok'] for t in ['original', 'miniatura', 'mediana'])

        if total_errores > total_ok:
            self.stdout.write(self.style.ERROR('  ❌ PROBLEMA GRAVE: La mayoría de URLs no existen en GCS'))
            self.stdout.write('')
            self.stdout.write('  POSIBLES CAUSAS:')
            self.stdout.write('    1. Las imágenes nunca se subieron al bucket')
            self.stdout.write('    2. Se subieron a una ruta diferente')
            self.stdout.write('    3. El bucket cambió de nombre')
            self.stdout.write('    4. Las URLs en BD tienen formato incorrecto')
            self.stdout.write('')
        elif total_errores > 0:
            self.stdout.write(self.style.WARNING(f'  ⚠️  Hay {total_errores} URLs rotas en la muestra'))
        else:
            self.stdout.write(self.style.SUCCESS('  ✅ Todas las URLs verificadas existen'))

        # ═══════════════════════════════════════════════════════════════
        # 4. SOLUCIONES PROPUESTAS
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('4️⃣  SOLUCIONES PROPUESTAS'))
        self.stdout.write('-' * 50)

        if total_errores > 0:
            self.stdout.write('')
            self.stdout.write('  OPCIÓN A: Limpiar URLs inexistentes')
            self.stdout.write('    - Poner NULL en imagen_miniatura/imagen_mediana donde no existan')
            self.stdout.write('    - Regenerar las variantes después')
            self.stdout.write('')
            self.stdout.write('  OPCIÓN B: Regenerar todas las variantes')
            self.stdout.write('    - Usar la imagen original para crear miniatura/mediana')
            self.stdout.write('    - Subir a GCS con estructura correcta')
            self.stdout.write('')
            self.stdout.write('  OPCIÓN C: Corregir URLs (si el patrón es predecible)')
            self.stdout.write('    - Actualizar URLs en BD para que apunten a la ruta correcta')
            self.stdout.write('')
            
            # Verificar si las originales existen
            if resultados['original']['ok'] > resultados['original']['error']:
                self.stdout.write(self.style.SUCCESS('  💡 Las imágenes ORIGINALES sí existen.'))
                self.stdout.write('     Puedes regenerar miniatura/mediana desde las originales.')
            else:
                self.stdout.write(self.style.ERROR('  ⚠️  Las imágenes ORIGINALES tampoco existen.'))
                self.stdout.write('     Necesitas recuperar las imágenes de Google Places API.')

        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  FIN DEL DIAGNÓSTICO'))
        self.stdout.write('=' * 70)

