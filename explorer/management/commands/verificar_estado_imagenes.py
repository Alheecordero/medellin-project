"""
Verifica el estado completo de las imágenes:
- URLs en BD vs existencia en GCS
- Estadísticas de variantes
- Muestra ejemplos de URLs correctas/incorrectas
"""
from django.core.management.base import BaseCommand
from django.db.models import Q, Count, Min
from explorer.models import Places, Foto
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import time


class Command(BaseCommand):
    help = 'Verifica el estado completo de las imágenes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sample',
            type=int,
            default=500,
            help='Muestra aleatoria a verificar (default: 500)',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=20,
            help='Workers paralelos (default: 20)',
        )

    def verificar_url(self, url):
        """Verifica si una URL existe en GCS"""
        if not url:
            return False, None
        try:
            r = requests.head(url, timeout=5, allow_redirects=True)
            return r.status_code == 200, r.status_code
        except Exception as e:
            return False, str(e)

    def handle(self, *args, **options):
        sample_size = options['sample']
        workers = options['workers']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  VERIFICACIÓN COMPLETA DE IMÁGENES'))
        self.stdout.write('=' * 70)
        self.stdout.write('')

        # 1. Estadísticas generales de BD
        self.stdout.write('1️⃣  ESTADÍSTICAS DE BASE DE DATOS')
        self.stdout.write('-' * 70)
        
        total_fotos = Foto.objects.count()
        fotos_con_mini = Foto.objects.exclude(imagen_miniatura__isnull=True).exclude(imagen_miniatura='').count()
        fotos_con_med = Foto.objects.exclude(imagen_mediana__isnull=True).exclude(imagen_mediana='').count()
        fotos_con_orig = Foto.objects.exclude(imagen__isnull=True).exclude(imagen='').count()
        
        lugares_con_fotos = Places.objects.filter(tiene_fotos=True).count()
        lugares_optimizados = Places.objects.filter(imagenes_optimizadas=True, tiene_fotos=True).count()
        
        self.stdout.write(f'  Fotos totales:              {total_fotos:,}')
        self.stdout.write(f'  Fotos con imagen_original:  {fotos_con_orig:,} ({fotos_con_orig*100/total_fotos:.1f}%)')
        self.stdout.write(f'  Fotos con imagen_miniatura: {fotos_con_mini:,} ({fotos_con_mini*100/total_fotos:.1f}%)')
        self.stdout.write(f'  Fotos con imagen_mediana:     {fotos_con_med:,} ({fotos_con_med*100/total_fotos:.1f}%)')
        self.stdout.write('')
        self.stdout.write(f'  Lugares con fotos:          {lugares_con_fotos:,}')
        self.stdout.write(f'  Lugares optimizados:        {lugares_optimizados:,} ({lugares_optimizados*100/lugares_con_fotos:.1f}%)')
        self.stdout.write('')

        # 2. Obtener muestra aleatoria para verificación
        self.stdout.write('2️⃣  VERIFICACIÓN DE EXISTENCIA EN GCS')
        self.stdout.write('-' * 70)
        self.stdout.write(f'  Verificando muestra aleatoria de {sample_size} fotos...')
        self.stdout.write('')

        # Obtener primeras fotos de lugares aleatorios
        lugares = Places.objects.filter(
            tiene_fotos=True
        ).exclude(
            Q(slug__isnull=True) | Q(slug='')
        ).annotate(
            first_foto_id=Min('fotos__id')
        ).filter(
            first_foto_id__isnull=False
        ).order_by('?')[:sample_size]

        foto_ids = [l.first_foto_id for l in lugares]
        fotos = {f.id: f for f in Foto.objects.filter(id__in=foto_ids)}

        muestras = []
        for lugar in lugares:
            foto = fotos.get(lugar.first_foto_id)
            if foto:
                muestras.append({
                    'lugar_slug': lugar.slug,
                    'foto_id': foto.id,
                    'url_orig': foto.imagen or '',
                    'url_mini': foto.imagen_miniatura or '',
                    'url_med': foto.imagen_mediana or '',
                })

        # Verificar en paralelo
        resultados = {
            'orig_ok': 0,
            'orig_error': 0,
            'mini_ok': 0,
            'mini_error': 0,
            'med_ok': 0,
            'med_error': 0,
            'ejemplos_error': []
        }

        def verificar_muestra(data):
            orig_ok, orig_status = self.verificar_url(data['url_orig'])
            mini_ok, mini_status = self.verificar_url(data['url_mini'])
            med_ok, med_status = self.verificar_url(data['url_med'])
            
            return {
                'data': data,
                'orig_ok': orig_ok,
                'orig_status': orig_status,
                'mini_ok': mini_ok,
                'mini_status': mini_status,
                'med_ok': med_ok,
                'med_status': med_status,
            }

        verificados = 0
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(verificar_muestra, m): m for m in muestras}
            
            for future in as_completed(futures):
                verificados += 1
                result = verificar_muestra(futures[future])
                
                if result['orig_ok']:
                    resultados['orig_ok'] += 1
                else:
                    resultados['orig_error'] += 1
                    if len(resultados['ejemplos_error']) < 5:
                        resultados['ejemplos_error'].append({
                            'tipo': 'original',
                            'slug': result['data']['lugar_slug'],
                            'url': result['data']['url_orig'][:80] + '...' if len(result['data']['url_orig']) > 80 else result['data']['url_orig'],
                            'status': result['orig_status']
                        })
                
                if result['mini_ok']:
                    resultados['mini_ok'] += 1
                elif result['data']['url_mini']:
                    resultados['mini_error'] += 1
                    if len(resultados['ejemplos_error']) < 10:
                        resultados['ejemplos_error'].append({
                            'tipo': 'miniatura',
                            'slug': result['data']['lugar_slug'],
                            'url': result['data']['url_mini'][:80] + '...' if len(result['data']['url_mini']) > 80 else result['data']['url_mini'],
                            'status': result['mini_status']
                        })
                
                if result['med_ok']:
                    resultados['med_ok'] += 1
                elif result['data']['url_med']:
                    resultados['med_error'] += 1
                    if len(resultados['ejemplos_error']) < 10:
                        resultados['ejemplos_error'].append({
                            'tipo': 'mediana',
                            'slug': result['data']['lugar_slug'],
                            'url': result['data']['url_med'][:80] + '...' if len(result['data']['url_med']) > 80 else result['data']['url_med'],
                            'status': result['med_status']
                        })
                
                if verificados % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = verificados / elapsed if elapsed > 0 else 0
                    self.stdout.write(
                        f'    Verificados: {verificados:,}/{len(muestras):,} | '
                        f'{rate:.1f}/s'
                    )

        self.stdout.write('')
        self.stdout.write('  Resultados de verificación:')
        self.stdout.write('')
        
        total_verificados = len(muestras)
        self.stdout.write(f'  ORIGINALES:')
        self.stdout.write(f'    ✅ Existen: {resultados["orig_ok"]:,} ({resultados["orig_ok"]*100/total_verificados:.1f}%)')
        self.stdout.write(f'    ❌ No existen: {resultados["orig_error"]:,} ({resultados["orig_error"]*100/total_verificados:.1f}%)')
        self.stdout.write('')
        
        mini_con_url = sum(1 for m in muestras if m['url_mini'])
        med_con_url = sum(1 for m in muestras if m['url_med'])
        
        self.stdout.write(f'  MINIATURAS (de {mini_con_url:,} con URL):')
        self.stdout.write(f'    ✅ Existen: {resultados["mini_ok"]:,} ({resultados["mini_ok"]*100/mini_con_url:.1f}% si hay URL)')
        self.stdout.write(f'    ❌ No existen: {resultados["mini_error"]:,} ({resultados["mini_error"]*100/mini_con_url:.1f}% si hay URL)')
        self.stdout.write('')
        
        self.stdout.write(f'  MEDIANAS (de {med_con_url:,} con URL):')
        self.stdout.write(f'    ✅ Existen: {resultados["med_ok"]:,} ({resultados["med_ok"]*100/med_con_url:.1f}% si hay URL)')
        self.stdout.write(f'    ❌ No existen: {resultados["med_error"]:,} ({resultados["med_error"]*100/med_con_url:.1f}% si hay URL)')
        self.stdout.write('')

        # 3. Ejemplos de errores
        if resultados['ejemplos_error']:
            self.stdout.write('3️⃣  EJEMPLOS DE URLs CON ERRORES')
            self.stdout.write('-' * 70)
            for i, error in enumerate(resultados['ejemplos_error'][:10], 1):
                self.stdout.write(f'  {i}. [{error["tipo"].upper()}] {error["slug"]}')
                self.stdout.write(f'     URL: {error["url"]}')
                self.stdout.write(f'     Status: {error["status"]}')
                self.stdout.write('')
        else:
            self.stdout.write('3️⃣  EJEMPLOS DE URLs CON ERRORES')
            self.stdout.write('-' * 70)
            self.stdout.write(self.style.SUCCESS('  ✅ No se encontraron errores en la muestra'))
            self.stdout.write('')

        # 4. Resumen final
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESUMEN FINAL'))
        self.stdout.write('=' * 70)
        
        total_ok = resultados['orig_ok'] + resultados['mini_ok'] + resultados['med_ok']
        total_errors = resultados['orig_error'] + resultados['mini_error'] + resultados['med_error']
        total_checks = total_ok + total_errors
        
        if total_checks > 0:
            porcentaje_ok = (total_ok / total_checks) * 100
            self.stdout.write(f'  URLs verificadas: {total_checks:,}')
            self.stdout.write(f'  URLs OK:          {total_ok:,} ({porcentaje_ok:.1f}%)')
            self.stdout.write(f'  URLs con error:   {total_errors:,} ({100-porcentaje_ok:.1f}%)')
            self.stdout.write('')
            
            if porcentaje_ok >= 95:
                self.stdout.write(self.style.SUCCESS('  ✅ Estado: EXCELENTE'))
            elif porcentaje_ok >= 90:
                self.stdout.write(self.style.WARNING('  ⚠️  Estado: BUENO (algunos errores menores)'))
            else:
                self.stdout.write(self.style.ERROR('  ❌ Estado: REQUIERE ATENCIÓN'))
        else:
            self.stdout.write(self.style.ERROR('  ❌ No se pudieron verificar URLs'))
        
        self.stdout.write('')

