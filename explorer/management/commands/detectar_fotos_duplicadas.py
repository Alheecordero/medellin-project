"""
Detecta fotos duplicadas en la base de datos.
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q, F, Min
from explorer.models import Foto, Places
from collections import defaultdict


class Command(BaseCommand):
    help = 'Detecta fotos duplicadas en la base de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--eliminar',
            action='store_true',
            help='Eliminar duplicados (mantiene el primero)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se eliminaría sin hacerlo',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Número de ejemplos a mostrar',
        )

    def handle(self, *args, **options):
        eliminar = options['eliminar']
        dry_run = options['dry_run']
        limit = options['limit']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  DETECCIÓN DE FOTOS DUPLICADAS'))
        self.stdout.write('=' * 70)
        self.stdout.write('')

        total_fotos = Foto.objects.count()
        self.stdout.write(f'Total de fotos en BD: {total_fotos:,}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 1. DUPLICADOS EXACTOS POR URL DE IMAGEN
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('1️⃣  DUPLICADOS POR URL EXACTA (imagen)'))
        self.stdout.write('-' * 50)

        # URLs duplicadas
        urls_duplicadas = Foto.objects.values('imagen').annotate(
            count=Count('id')
        ).filter(count__gt=1).order_by('-count')

        total_urls_dup = urls_duplicadas.count()
        fotos_en_duplicados = sum(d['count'] for d in urls_duplicadas)
        fotos_extra = fotos_en_duplicados - total_urls_dup  # Las que sobran

        self.stdout.write(f'  URLs únicas con duplicados: {total_urls_dup:,}')
        self.stdout.write(f'  Fotos en grupos duplicados: {fotos_en_duplicados:,}')
        self.stdout.write(f'  Fotos extra (a eliminar):   {fotos_extra:,}')
        self.stdout.write('')

        if total_urls_dup > 0:
            self.stdout.write(f'  Ejemplos (primeros {min(limit, total_urls_dup)}):')
            for dup in urls_duplicadas[:limit]:
                url_short = dup['imagen'][:60] + '...' if len(dup['imagen']) > 60 else dup['imagen']
                self.stdout.write(f'    [{dup["count"]}x] {url_short}')
                
                # Mostrar IDs y lugares
                fotos = Foto.objects.filter(imagen=dup['imagen']).select_related('lugar')[:5]
                for f in fotos:
                    lugar_name = f.lugar.slug if f.lugar else 'sin-lugar'
                    self.stdout.write(f'         ID:{f.id} -> {lugar_name}')
            self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 2. DUPLICADOS POR LUGAR + URL
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('2️⃣  DUPLICADOS POR LUGAR + URL'))
        self.stdout.write('-' * 50)

        duplicados_lugar_url = Foto.objects.values('lugar_id', 'imagen').annotate(
            count=Count('id')
        ).filter(count__gt=1).order_by('-count')

        total_dup_lugar = duplicados_lugar_url.count()
        
        self.stdout.write(f'  Combinaciones lugar+URL duplicadas: {total_dup_lugar:,}')
        
        if total_dup_lugar > 0:
            self.stdout.write(f'  Ejemplos (primeros {min(limit, total_dup_lugar)}):')
            for dup in duplicados_lugar_url[:limit]:
                lugar = Places.objects.filter(id=dup['lugar_id']).first()
                lugar_name = lugar.slug if lugar else f'ID:{dup["lugar_id"]}'
                url_short = dup['imagen'][:40] + '...' if len(dup['imagen']) > 40 else dup['imagen']
                self.stdout.write(f'    [{dup["count"]}x] {lugar_name}: {url_short}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 3. ANÁLISIS DE PATRONES DE URLs
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('3️⃣  ANÁLISIS DE PATRONES DE URLs'))
        self.stdout.write('-' * 50)

        # Contar por prefijo de bucket
        patrones = defaultdict(int)
        
        for foto in Foto.objects.values_list('imagen', flat=True).iterator():
            if foto:
                if 'storage.googleapis.com' in foto:
                    parts = foto.split('/')
                    if len(parts) >= 5:
                        patron = '/'.join(parts[3:6])
                        patrones[patron] += 1
                elif foto.startswith('/media/'):
                    patrones['/media/ (local)'] += 1
                else:
                    patrones['otro'] += 1

        self.stdout.write('  Distribución por patrón de URL:')
        for patron, count in sorted(patrones.items(), key=lambda x: -x[1])[:15]:
            self.stdout.write(f'    {count:,}: {patron}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 4. LUGARES CON MUCHAS FOTOS (POSIBLES DUPLICADOS)
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('4️⃣  LUGARES CON MUCHAS FOTOS'))
        self.stdout.write('-' * 50)

        lugares_muchas_fotos = Places.objects.annotate(
            num_fotos=Count('fotos')
        ).filter(num_fotos__gt=20).order_by('-num_fotos')[:20]

        self.stdout.write('  Top 20 lugares con más fotos:')
        for lugar in lugares_muchas_fotos:
            self.stdout.write(f'    {lugar.num_fotos:3} fotos: {lugar.slug}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 5. FOTOS HUÉRFANAS (sin lugar válido)
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('5️⃣  FOTOS HUÉRFANAS'))
        self.stdout.write('-' * 50)

        fotos_sin_lugar = Foto.objects.filter(lugar__isnull=True).count()
        self.stdout.write(f'  Fotos sin lugar asociado: {fotos_sin_lugar:,}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 6. INCONSISTENCIAS EN URLs DE VARIANTES
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.HTTP_INFO('6️⃣  INCONSISTENCIAS EN VARIANTES'))
        self.stdout.write('-' * 50)

        # Fotos donde miniatura = mediana (posible error)
        mini_igual_mediana = Foto.objects.exclude(
            Q(imagen_miniatura__isnull=True) | Q(imagen_mediana__isnull=True)
        ).filter(imagen_miniatura=F('imagen_mediana')).count()
        
        # Fotos donde original = miniatura
        original_igual_mini = Foto.objects.exclude(
            Q(imagen_miniatura__isnull=True)
        ).filter(imagen=F('imagen_miniatura')).count()

        # Fotos donde original = mediana
        original_igual_mediana = Foto.objects.exclude(
            Q(imagen_mediana__isnull=True)
        ).filter(imagen=F('imagen_mediana')).count()

        self.stdout.write(f'  Miniatura = Mediana:       {mini_igual_mediana:,}')
        self.stdout.write(f'  Original = Miniatura:      {original_igual_mini:,}')
        self.stdout.write(f'  Original = Mediana:        {original_igual_mediana:,}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # 7. ELIMINACIÓN DE DUPLICADOS (OPCIONAL)
        # ═══════════════════════════════════════════════════════════════
        if eliminar or dry_run:
            self.stdout.write('=' * 70)
            self.stdout.write(self.style.WARNING('  ELIMINACIÓN DE DUPLICADOS'))
            self.stdout.write('=' * 70)

            if dry_run:
                self.stdout.write(self.style.WARNING('  MODO DRY-RUN: No se eliminarán fotos'))
            
            # Encontrar duplicados por lugar + URL
            duplicados = Foto.objects.values('lugar_id', 'imagen').annotate(
                count=Count('id'),
                min_id=Min('id')
            ).filter(count__gt=1)

            total_a_eliminar = 0
            ids_a_eliminar = []

            for dup in duplicados:
                # Obtener todos los IDs excepto el primero (min_id)
                fotos_dup = Foto.objects.filter(
                    lugar_id=dup['lugar_id'],
                    imagen=dup['imagen']
                ).exclude(id=dup['min_id']).values_list('id', flat=True)
                
                ids_a_eliminar.extend(fotos_dup)
                total_a_eliminar += len(fotos_dup)

            self.stdout.write(f'  Fotos duplicadas a eliminar: {total_a_eliminar:,}')

            if eliminar and not dry_run and total_a_eliminar > 0:
                # Eliminar en batches
                batch_size = 1000
                eliminadas = 0
                
                for i in range(0, len(ids_a_eliminar), batch_size):
                    batch = ids_a_eliminar[i:i+batch_size]
                    deleted, _ = Foto.objects.filter(id__in=batch).delete()
                    eliminadas += deleted
                    self.stdout.write(f'    Eliminadas: {eliminadas:,}/{total_a_eliminar:,}')
                
                self.stdout.write(self.style.SUCCESS(f'  ✅ Eliminadas {eliminadas:,} fotos duplicadas'))
            elif dry_run:
                self.stdout.write(f'  Se eliminarían {total_a_eliminar:,} fotos')
                if ids_a_eliminar:
                    self.stdout.write(f'  Primeros 10 IDs: {ids_a_eliminar[:10]}')

        # ═══════════════════════════════════════════════════════════════
        # RESUMEN
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESUMEN'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Total fotos:                    {total_fotos:,}')
        self.stdout.write(f'  URLs duplicadas:                {total_urls_dup:,}')
        self.stdout.write(f'  Fotos extra (duplicadas):       {fotos_extra:,}')
        self.stdout.write(f'  Duplicados por lugar+URL:       {total_dup_lugar:,}')
        
        if fotos_extra > 0:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('  ⚠️  Para eliminar duplicados ejecuta:'))
            self.stdout.write('      python manage.py detectar_fotos_duplicadas --eliminar --dry-run')
            self.stdout.write('      python manage.py detectar_fotos_duplicadas --eliminar')
        
        self.stdout.write('')

