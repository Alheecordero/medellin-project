"""
Restaura URLs de variantes DIRECTAMENTE sin verificar.
Asume que las variantes existen basándose en el patrón conocido.
Las que no existan usarán fallback a la imagen original.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q, Min
from explorer.models import Foto, Places


class Command(BaseCommand):
    help = 'Restaura URLs de variantes directamente (sin verificar HTTP)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Número de lugares a procesar (0 = todos)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESTAURAR URLs DIRECTAMENTE'))
        self.stdout.write('=' * 70)
        self.stdout.write('')
        self.stdout.write('  Sin verificación HTTP - Asume que las variantes existen')
        self.stdout.write('  Las que no existan usarán fallback a imagen original')
        self.stdout.write('')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN'))
            self.stdout.write('')

        # Base URL de GCS
        GCS_BASE = 'https://storage.googleapis.com/vivemedellin-bucket/tourism/images'

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

        # 2. Obtener primeras fotos
        self.stdout.write('  Obteniendo primeras fotos...')
        
        fotos_ids = Foto.objects.filter(
            lugar_id__in=lugar_ids
        ).values('lugar_id').annotate(
            min_id=Min('id')
        ).values_list('min_id', flat=True)
        
        fotos = list(Foto.objects.filter(id__in=fotos_ids).values(
            'id', 'lugar_id', 'imagen_miniatura', 'imagen_mediana'
        ))
        
        self.stdout.write(f'  Fotos encontradas: {len(fotos):,}')
        self.stdout.write('')

        # 3. Preparar actualizaciones
        ya_tienen = 0
        a_actualizar = []
        
        for foto in fotos:
            # Si ya tiene ambas, skip
            if foto['imagen_miniatura'] and foto['imagen_mediana']:
                ya_tienen += 1
                continue
            
            slug = lugares_dict.get(foto['lugar_id'])
            if not slug:
                continue
            
            foto_id = foto['id']
            
            # Construir URLs
            url_mini = f'{GCS_BASE}/thumb/{slug}/{foto_id}.jpg'
            url_med = f'{GCS_BASE}/medium/{slug}/{foto_id}.jpg'
            
            a_actualizar.append({
                'foto_id': foto_id,
                'lugar_id': foto['lugar_id'],
                'imagen_miniatura': url_mini if not foto['imagen_miniatura'] else None,
                'imagen_mediana': url_med if not foto['imagen_mediana'] else None,
            })
        
        self.stdout.write(f'  Ya tenían variantes: {ya_tienen:,}')
        self.stdout.write(f'  Fotos a actualizar:  {len(a_actualizar):,}')
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('  DRY-RUN: No se harán cambios'))
            self.stdout.write('')
            self.stdout.write('  Ejemplos de URLs que se asignarían:')
            for item in a_actualizar[:5]:
                self.stdout.write(f'    Foto {item["foto_id"]}:')
                if item['imagen_miniatura']:
                    self.stdout.write(f'      mini: {item["imagen_miniatura"][:60]}...')
                if item['imagen_mediana']:
                    self.stdout.write(f'      med:  {item["imagen_mediana"][:60]}...')
            return

        # 4. Actualizar BD en batch
        self.stdout.write('  Actualizando BD...')
        
        actualizadas = 0
        batch_size = 500
        
        for i in range(0, len(a_actualizar), batch_size):
            batch = a_actualizar[i:i+batch_size]
            
            for item in batch:
                updates = {}
                if item['imagen_miniatura']:
                    updates['imagen_miniatura'] = item['imagen_miniatura']
                if item['imagen_mediana']:
                    updates['imagen_mediana'] = item['imagen_mediana']
                
                if updates:
                    Foto.objects.filter(id=item['foto_id']).update(**updates)
                    actualizadas += 1
            
            # Marcar lugares como optimizados
            lugar_ids_batch = [item['lugar_id'] for item in batch]
            Places.objects.filter(id__in=lugar_ids_batch).update(imagenes_optimizadas=True)
            
            self.stdout.write(f'    Progreso: {min(i+batch_size, len(a_actualizar)):,}/{len(a_actualizar):,}')

        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS(f'  ✅ COMPLETADO'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'  Fotos actualizadas:      {actualizadas:,}')
        self.stdout.write(f'  Lugares marcados:        {len(a_actualizar):,}')
        self.stdout.write('')
        self.stdout.write('  Las URLs que no existan en GCS usarán fallback')
        self.stdout.write('  a la imagen original automáticamente.')
        self.stdout.write('')

