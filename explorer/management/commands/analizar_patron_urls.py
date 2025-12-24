"""
Analiza patrones de URLs para identificar lotes problemáticos SIN hacer HTTP requests.
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Min, Max, Q
from django.db.models.functions import Substr, Length
from explorer.models import Foto, Places
from collections import defaultdict
import re


class Command(BaseCommand):
    help = 'Analiza patrones de URLs para identificar lotes problemáticos'

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  ANÁLISIS DE PATRONES DE URLs'))
        self.stdout.write('=' * 70)
        self.stdout.write('')

        total_fotos = Foto.objects.count()
        self.stdout.write(f'Total fotos: {total_fotos:,}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 1. DISTRIBUCIÓN POR RANGO DE IDs
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('1️⃣  DISTRIBUCIÓN POR RANGO DE IDs'))
        self.stdout.write('-' * 50)

        # Dividir en rangos de 5000
        rangos = []
        for start in range(0, 50000, 5000):
            end = start + 5000
            count = Foto.objects.filter(id__gte=start, id__lt=end).count()
            if count > 0:
                # Obtener info de fecha
                fecha_info = Foto.objects.filter(id__gte=start, id__lt=end).aggregate(
                    min_fecha=Min('fecha_subida'),
                    max_fecha=Max('fecha_subida')
                )
                rangos.append({
                    'rango': f'{start}-{end}',
                    'count': count,
                    'min_fecha': fecha_info['min_fecha'],
                    'max_fecha': fecha_info['max_fecha'],
                })

        for r in rangos:
            fecha_str = ''
            if r['min_fecha']:
                fecha_str = f" | {r['min_fecha'].strftime('%Y-%m-%d')} a {r['max_fecha'].strftime('%Y-%m-%d') if r['max_fecha'] else '?'}"
            self.stdout.write(f"  IDs {r['rango']}: {r['count']:,} fotos{fecha_str}")

        # ═══════════════════════════════════════════════════════════════
        # 2. ANÁLISIS DE ESTRUCTURA DE URLs MINIATURA
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('2️⃣  PATRONES DE URLs MINIATURA'))
        self.stdout.write('-' * 50)

        patrones_mini = defaultdict(lambda: {'count': 0, 'ids': [], 'ejemplos': []})
        
        for foto in Foto.objects.exclude(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).values('id', 'imagen_miniatura')[:10000]:
            url = foto['imagen_miniatura']
            
            # Extraer patrón
            if '/tourism/images/thumb/' in url:
                patron = 'tourism/images/thumb/{slug}/{id}.jpg'
            elif '/tourism/images/mini/' in url:
                patron = 'tourism/images/mini/{slug}/{id}.jpg'
            elif '/images/ChIJ' in url:
                patron = 'images/{place_id}/XX.jpg (viejo)'
            else:
                # Extraer estructura genérica
                match = re.search(r'vivemedellin-bucket/([^/]+/[^/]+)', url)
                patron = match.group(1) if match else 'otro'
            
            patrones_mini[patron]['count'] += 1
            if len(patrones_mini[patron]['ids']) < 5:
                patrones_mini[patron]['ids'].append(foto['id'])
            if len(patrones_mini[patron]['ejemplos']) < 2:
                patrones_mini[patron]['ejemplos'].append(url)

        for patron, info in sorted(patrones_mini.items(), key=lambda x: -x[1]['count']):
            self.stdout.write(f"  {info['count']:,}: {patron}")
            for ej in info['ejemplos']:
                self.stdout.write(f"       {ej[:70]}...")

        # ═══════════════════════════════════════════════════════════════
        # 3. COMPARAR ESTRUCTURA ORIGINAL vs MINIATURA
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('3️⃣  COMPARACIÓN ORIGINAL vs MINIATURA'))
        self.stdout.write('-' * 50)

        # Fotos donde la miniatura NO sigue el patrón esperado
        inconsistentes = 0
        consistentes = 0
        sin_slug_match = []

        for foto in Foto.objects.select_related('lugar').exclude(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        )[:5000]:
            if foto.lugar and foto.lugar.slug:
                slug = foto.lugar.slug
                if slug in foto.imagen_miniatura:
                    consistentes += 1
                else:
                    inconsistentes += 1
                    if len(sin_slug_match) < 10:
                        sin_slug_match.append({
                            'id': foto.id,
                            'slug': slug,
                            'mini': foto.imagen_miniatura,
                        })

        self.stdout.write(f"  URLs con slug del lugar:     {consistentes:,}")
        self.stdout.write(f"  URLs SIN slug del lugar:     {inconsistentes:,}")
        
        if sin_slug_match:
            self.stdout.write('')
            self.stdout.write('  Ejemplos de inconsistencias:')
            for s in sin_slug_match[:5]:
                self.stdout.write(f"    ID:{s['id']} | Slug esperado: {s['slug']}")
                self.stdout.write(f"      URL: {s['mini'][:60]}...")

        # ═══════════════════════════════════════════════════════════════
        # 4. FOTOS SIN VARIANTES
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('4️⃣  FOTOS SIN VARIANTES'))
        self.stdout.write('-' * 50)

        sin_mini = Foto.objects.filter(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).count()
        
        sin_med = Foto.objects.filter(
            Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
        ).count()

        self.stdout.write(f"  Sin miniatura:   {sin_mini:,}")
        self.stdout.write(f"  Sin mediana:     {sin_med:,}")

        # ═══════════════════════════════════════════════════════════════
        # 5. ANÁLISIS POR LUGAR
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('5️⃣  LUGARES CON FOTOS SIN OPTIMIZAR'))
        self.stdout.write('-' * 50)

        lugares_pendientes = Places.objects.filter(
            tiene_fotos=True,
            imagenes_optimizadas=False
        ).count()

        lugares_optimizados = Places.objects.filter(
            tiene_fotos=True,
            imagenes_optimizadas=True
        ).count()

        self.stdout.write(f"  Lugares optimizados:     {lugares_optimizados:,}")
        self.stdout.write(f"  Lugares pendientes:      {lugares_pendientes:,}")

        # ═══════════════════════════════════════════════════════════════
        # 6. HIPÓTESIS DEL PROBLEMA
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('  HIPÓTESIS DEL PROBLEMA'))
        self.stdout.write('=' * 70)

        # Contar fotos por estructura de URL
        con_tourism = Foto.objects.filter(imagen_miniatura__contains='/tourism/').count()
        sin_tourism = Foto.objects.exclude(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).exclude(imagen_miniatura__contains='/tourism/').count()

        self.stdout.write(f'  URLs con /tourism/:      {con_tourism:,}')
        self.stdout.write(f'  URLs SIN /tourism/:      {sin_tourism:,}')
        self.stdout.write('')

        if inconsistentes > consistentes * 0.1:  # >10% inconsistentes
            self.stdout.write(self.style.ERROR('  ⚠️  PROBLEMA DETECTADO:'))
            self.stdout.write('     Muchas URLs de miniatura no coinciden con el slug del lugar.')
            self.stdout.write('     Posible causa: se generaron con un patrón incorrecto.')
            self.stdout.write('')
            self.stdout.write('  SOLUCIÓN RECOMENDADA:')
            self.stdout.write('     1. Limpiar imagen_miniatura e imagen_mediana de todas las fotos')
            self.stdout.write('     2. Marcar lugares como imagenes_optimizadas=False')
            self.stdout.write('     3. Regenerar todas las variantes con imagenes_optimizar')

        self.stdout.write('')

