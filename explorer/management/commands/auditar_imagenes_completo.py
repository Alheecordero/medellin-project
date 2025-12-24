"""
Auditoría completa de imágenes: miniaturas y medianas.
Detecta inconsistencias entre la BD y el almacenamiento.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from django.db.models import Count, Q, F
from explorer.models import Places, Foto


class Command(BaseCommand):
    help = 'Audita el estado de imágenes: originales, miniaturas y medianas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verify-urls',
            action='store_true',
            help='Verificar que las URLs de imágenes existan (HEAD request)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limitar número de fotos a verificar (0 = todas)',
        )
        parser.add_argument(
            '--sample',
            type=int,
            default=10,
            help='Mostrar N ejemplos de cada categoría',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=10,
            help='Número de workers para verificación paralela',
        )

    def handle(self, *args, **options):
        verify_urls = options['verify_urls']
        limit = options['limit']
        sample = options['sample']
        workers = options['workers']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  AUDITORÍA COMPLETA DE IMÁGENES'))
        self.stdout.write('=' * 70)
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 1. ESTADÍSTICAS DE LUGARES
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('📍 ESTADÍSTICAS DE LUGARES'))
        self.stdout.write('-' * 50)
        
        total_lugares = Places.objects.count()
        lugares_con_fotos = Places.objects.filter(tiene_fotos=True).count()
        lugares_sin_fotos = Places.objects.filter(tiene_fotos=False).count()
        
        # Lugares con flag tiene_fotos pero sin fotos reales
        lugares_flag_incorrecto = Places.objects.annotate(
            num_fotos=Count('fotos')
        ).filter(tiene_fotos=True, num_fotos=0).count()
        
        self.stdout.write(f'  Total lugares:              {total_lugares:,}')
        self.stdout.write(f'  Con fotos (flag):           {lugares_con_fotos:,}')
        self.stdout.write(f'  Sin fotos (flag):           {lugares_sin_fotos:,}')
        if lugares_flag_incorrecto > 0:
            self.stdout.write(self.style.WARNING(
                f'  ⚠️  Flag incorrecto:         {lugares_flag_incorrecto:,} (tiene_fotos=True pero 0 fotos)'
            ))
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 2. ESTADÍSTICAS DE FOTOS
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('📸 ESTADÍSTICAS DE FOTOS'))
        self.stdout.write('-' * 50)
        
        total_fotos = Foto.objects.count()
        
        # Imagen original
        fotos_con_original = Foto.objects.exclude(
            Q(imagen__isnull=True) | Q(imagen='')
        ).count()
        fotos_sin_original = total_fotos - fotos_con_original
        
        # Miniatura
        fotos_con_miniatura = Foto.objects.exclude(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).count()
        fotos_sin_miniatura = total_fotos - fotos_con_miniatura
        
        # Mediana
        fotos_con_mediana = Foto.objects.exclude(
            Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
        ).count()
        fotos_sin_mediana = total_fotos - fotos_con_mediana
        
        self.stdout.write(f'  Total fotos:                {total_fotos:,}')
        self.stdout.write('')
        self.stdout.write(f'  Con imagen original:        {fotos_con_original:,} ({fotos_con_original*100/total_fotos:.1f}%)')
        self.stdout.write(f'  Sin imagen original:        {fotos_sin_original:,}')
        self.stdout.write('')
        self.stdout.write(f'  Con miniatura:              {fotos_con_miniatura:,} ({fotos_con_miniatura*100/total_fotos:.1f}%)')
        self.stdout.write(f'  Sin miniatura:              {fotos_sin_miniatura:,} ({fotos_sin_miniatura*100/total_fotos:.1f}%)')
        self.stdout.write('')
        self.stdout.write(f'  Con mediana:                {fotos_con_mediana:,} ({fotos_con_mediana*100/total_fotos:.1f}%)')
        self.stdout.write(f'  Sin mediana:                {fotos_sin_mediana:,} ({fotos_sin_mediana*100/total_fotos:.1f}%)')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 3. ANÁLISIS DE URLS
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('🔗 ANÁLISIS DE URLs'))
        self.stdout.write('-' * 50)
        
        # URLs de GCS
        gcs_prefix = 'https://storage.googleapis.com'
        
        # Originales
        originales_gcs = Foto.objects.filter(imagen__startswith=gcs_prefix).count()
        originales_local = Foto.objects.filter(imagen__startswith='/media/').count()
        originales_otras = fotos_con_original - originales_gcs - originales_local
        
        # Miniaturas
        miniaturas_gcs = Foto.objects.filter(imagen_miniatura__startswith=gcs_prefix).count()
        miniaturas_local = Foto.objects.filter(imagen_miniatura__startswith='/media/').count()
        miniaturas_otras = fotos_con_miniatura - miniaturas_gcs - miniaturas_local
        
        # Medianas
        medianas_gcs = Foto.objects.filter(imagen_mediana__startswith=gcs_prefix).count()
        medianas_local = Foto.objects.filter(imagen_mediana__startswith='/media/').count()
        medianas_otras = fotos_con_mediana - medianas_gcs - medianas_local
        
        self.stdout.write('  IMAGEN ORIGINAL:')
        self.stdout.write(f'    En GCS:                   {originales_gcs:,}')
        self.stdout.write(f'    Local (/media/):          {originales_local:,}')
        if originales_otras > 0:
            self.stdout.write(f'    Otras URLs:               {originales_otras:,}')
        self.stdout.write('')
        
        self.stdout.write('  MINIATURA:')
        self.stdout.write(f'    En GCS:                   {miniaturas_gcs:,}')
        if miniaturas_local > 0:
            self.stdout.write(self.style.WARNING(f'    Local (/media/):          {miniaturas_local:,} ⚠️'))
        if miniaturas_otras > 0:
            self.stdout.write(f'    Otras URLs:               {miniaturas_otras:,}')
        self.stdout.write('')
        
        self.stdout.write('  MEDIANA:')
        self.stdout.write(f'    En GCS:                   {medianas_gcs:,}')
        if medianas_local > 0:
            self.stdout.write(self.style.WARNING(f'    Local (/media/):          {medianas_local:,} ⚠️'))
        if medianas_otras > 0:
            self.stdout.write(f'    Otras URLs:               {medianas_otras:,}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 4. INCONSISTENCIAS
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('⚠️  INCONSISTENCIAS DETECTADAS'))
        self.stdout.write('-' * 50)
        
        # Fotos con original pero sin miniatura
        con_original_sin_miniatura = Foto.objects.exclude(
            Q(imagen__isnull=True) | Q(imagen='')
        ).filter(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).count()
        
        # Fotos con original pero sin mediana
        con_original_sin_mediana = Foto.objects.exclude(
            Q(imagen__isnull=True) | Q(imagen='')
        ).filter(
            Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
        ).count()
        
        # Fotos con miniatura pero sin mediana
        con_miniatura_sin_mediana = Foto.objects.exclude(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).filter(
            Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
        ).count()
        
        # Fotos con mediana pero sin miniatura
        con_mediana_sin_miniatura = Foto.objects.exclude(
            Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
        ).filter(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).count()
        
        self.stdout.write(f'  Con original, sin miniatura:    {con_original_sin_miniatura:,}')
        self.stdout.write(f'  Con original, sin mediana:      {con_original_sin_mediana:,}')
        self.stdout.write(f'  Con miniatura, sin mediana:     {con_miniatura_sin_mediana:,}')
        self.stdout.write(f'  Con mediana, sin miniatura:     {con_mediana_sin_miniatura:,}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 5. ANÁLISIS POR PATRÓN DE URL
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('📂 PATRONES DE URLs EN GCS'))
        self.stdout.write('-' * 50)
        
        # Patrones comunes
        patrones = {
            'tourism/images/original/': 'Original en /original/',
            'tourism/images/medium/': 'Mediana en /medium/',
            'tourism/images/thumbnail/': 'Miniatura en /thumbnail/',
            'tourism/images/mini/': 'Miniatura en /mini/',
            'vivemedellin-bucket/': 'Bucket principal',
        }
        
        for patron, descripcion in patrones.items():
            count_original = Foto.objects.filter(imagen__contains=patron).count()
            count_mini = Foto.objects.filter(imagen_miniatura__contains=patron).count()
            count_med = Foto.objects.filter(imagen_mediana__contains=patron).count()
            
            if count_original + count_mini + count_med > 0:
                self.stdout.write(f'  {descripcion}:')
                if count_original > 0:
                    self.stdout.write(f'    - En campo imagen:        {count_original:,}')
                if count_mini > 0:
                    self.stdout.write(f'    - En campo miniatura:     {count_mini:,}')
                if count_med > 0:
                    self.stdout.write(f'    - En campo mediana:       {count_med:,}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 6. EJEMPLOS DE FOTOS PROBLEMÁTICAS
        # ═══════════════════════════════════════════════════════════════
        if sample > 0:
            self.stdout.write(self.style.HTTP_INFO(f'📋 EJEMPLOS (máx {sample} por categoría)'))
            self.stdout.write('-' * 50)
            
            # Fotos sin miniatura
            if con_original_sin_miniatura > 0:
                self.stdout.write(self.style.WARNING('\n  Fotos con original pero SIN miniatura:'))
                fotos = Foto.objects.exclude(
                    Q(imagen__isnull=True) | Q(imagen='')
                ).filter(
                    Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
                ).select_related('lugar')[:sample]
                
                for foto in fotos:
                    lugar_slug = foto.lugar.slug if foto.lugar else 'sin-lugar'
                    self.stdout.write(f'    ID:{foto.id} | {lugar_slug}')
                    self.stdout.write(f'      Original: {foto.imagen[:80]}...' if len(str(foto.imagen)) > 80 else f'      Original: {foto.imagen}')
            
            # Fotos sin mediana
            if con_original_sin_mediana > 0:
                self.stdout.write(self.style.WARNING('\n  Fotos con original pero SIN mediana:'))
                fotos = Foto.objects.exclude(
                    Q(imagen__isnull=True) | Q(imagen='')
                ).filter(
                    Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
                ).select_related('lugar')[:sample]
                
                for foto in fotos:
                    lugar_slug = foto.lugar.slug if foto.lugar else 'sin-lugar'
                    self.stdout.write(f'    ID:{foto.id} | {lugar_slug}')
                    self.stdout.write(f'      Original: {foto.imagen[:80]}...' if len(str(foto.imagen)) > 80 else f'      Original: {foto.imagen}')
            
            # Fotos con URLs locales
            if miniaturas_local > 0:
                self.stdout.write(self.style.WARNING('\n  Miniaturas con URL local (/media/):'))
                fotos = Foto.objects.filter(
                    imagen_miniatura__startswith='/media/'
                ).select_related('lugar')[:sample]
                
                for foto in fotos:
                    lugar_slug = foto.lugar.slug if foto.lugar else 'sin-lugar'
                    self.stdout.write(f'    ID:{foto.id} | {lugar_slug}')
                    self.stdout.write(f'      Miniatura: {foto.imagen_miniatura}')
            
            self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 7. VERIFICACIÓN DE URLs (OPCIONAL)
        # ═══════════════════════════════════════════════════════════════
        if verify_urls:
            self.stdout.write(self.style.HTTP_INFO('🌐 VERIFICANDO URLs (HEAD requests)'))
            self.stdout.write('-' * 50)
            
            # Seleccionar fotos a verificar
            fotos_query = Foto.objects.exclude(
                Q(imagen__isnull=True) | Q(imagen='')
            ).filter(
                imagen__startswith=gcs_prefix
            )
            
            if limit > 0:
                fotos_query = fotos_query[:limit]
            
            fotos_verificar = list(fotos_query.values('id', 'imagen', 'imagen_miniatura', 'imagen_mediana'))
            total_verificar = len(fotos_verificar)
            
            self.stdout.write(f'  Verificando {total_verificar:,} fotos...')
            
            resultados = {
                'original_ok': 0,
                'original_error': 0,
                'miniatura_ok': 0,
                'miniatura_error': 0,
                'mediana_ok': 0,
                'mediana_error': 0,
            }
            errores = []
            
            def verificar_url(url):
                if not url or not url.startswith('http'):
                    return None
                try:
                    r = requests.head(url, timeout=5)
                    return r.status_code == 200
                except:
                    return False
            
            def verificar_foto(foto):
                resultado = {'id': foto['id']}
                
                # Original
                if foto['imagen']:
                    resultado['original'] = verificar_url(foto['imagen'])
                
                # Miniatura
                if foto['imagen_miniatura']:
                    resultado['miniatura'] = verificar_url(foto['imagen_miniatura'])
                
                # Mediana
                if foto['imagen_mediana']:
                    resultado['mediana'] = verificar_url(foto['imagen_mediana'])
                
                return resultado
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(verificar_foto, f): f for f in fotos_verificar}
                
                for i, future in enumerate(as_completed(futures)):
                    if (i + 1) % 500 == 0:
                        self.stdout.write(f'    Progreso: {i + 1}/{total_verificar}')
                    
                    resultado = future.result()
                    
                    if resultado.get('original') is True:
                        resultados['original_ok'] += 1
                    elif resultado.get('original') is False:
                        resultados['original_error'] += 1
                        errores.append(('original', resultado['id']))
                    
                    if resultado.get('miniatura') is True:
                        resultados['miniatura_ok'] += 1
                    elif resultado.get('miniatura') is False:
                        resultados['miniatura_error'] += 1
                        errores.append(('miniatura', resultado['id']))
                    
                    if resultado.get('mediana') is True:
                        resultados['mediana_ok'] += 1
                    elif resultado.get('mediana') is False:
                        resultados['mediana_error'] += 1
                        errores.append(('mediana', resultado['id']))
            
            self.stdout.write('')
            self.stdout.write('  RESULTADOS DE VERIFICACIÓN:')
            self.stdout.write(f'    Originales OK:    {resultados["original_ok"]:,}')
            self.stdout.write(f'    Originales Error: {resultados["original_error"]:,}')
            self.stdout.write(f'    Miniaturas OK:    {resultados["miniatura_ok"]:,}')
            self.stdout.write(f'    Miniaturas Error: {resultados["miniatura_error"]:,}')
            self.stdout.write(f'    Medianas OK:      {resultados["mediana_ok"]:,}')
            self.stdout.write(f'    Medianas Error:   {resultados["mediana_error"]:,}')
            
            if errores and sample > 0:
                self.stdout.write(self.style.ERROR(f'\n  Primeros {min(sample, len(errores))} errores:'))
                for tipo, foto_id in errores[:sample]:
                    foto = Foto.objects.get(id=foto_id)
                    url = getattr(foto, f'imagen_{tipo}' if tipo != 'original' else 'imagen')
                    self.stdout.write(f'    [{tipo}] ID:{foto_id} - {url}')
            
            self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 8. RESUMEN FINAL
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESUMEN'))
        self.stdout.write('=' * 70)
        
        completitud_mini = (fotos_con_miniatura / total_fotos * 100) if total_fotos > 0 else 0
        completitud_med = (fotos_con_mediana / total_fotos * 100) if total_fotos > 0 else 0
        
        self.stdout.write(f'  Total fotos:                    {total_fotos:,}')
        self.stdout.write(f'  Completitud miniaturas:         {completitud_mini:.1f}%')
        self.stdout.write(f'  Completitud medianas:           {completitud_med:.1f}%')
        self.stdout.write('')
        
        if con_original_sin_miniatura > 0 or con_original_sin_mediana > 0:
            self.stdout.write(self.style.WARNING('  ⚠️  ACCIÓN REQUERIDA:'))
            if con_original_sin_miniatura > 0:
                self.stdout.write(f'      - Generar {con_original_sin_miniatura:,} miniaturas faltantes')
            if con_original_sin_mediana > 0:
                self.stdout.write(f'      - Generar {con_original_sin_mediana:,} medianas faltantes')
        else:
            self.stdout.write(self.style.SUCCESS('  ✅ Todas las fotos tienen variantes generadas'))
        
        self.stdout.write('')

