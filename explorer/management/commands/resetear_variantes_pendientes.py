"""
Resetea las URLs de variantes para lugares pendientes de optimizar.
Después se regeneran con imagenes_optimizar.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from explorer.models import Foto, Places


class Command(BaseCommand):
    help = 'Resetea URLs de variantes para lugares pendientes de optimizar'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se resetearía',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limitar número de lugares a procesar (0 = todos)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('  RESETEAR VARIANTES DE LUGARES PENDIENTES'))
        self.stdout.write('=' * 70)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN'))
        self.stdout.write('')

        # Contar lugares pendientes
        lugares_pendientes = Places.objects.filter(
            tiene_fotos=True,
            imagenes_optimizadas=False
        )
        
        if limit > 0:
            lugares_pendientes = lugares_pendientes[:limit]
        
        total_lugares = lugares_pendientes.count()
        self.stdout.write(f'Lugares pendientes de optimizar: {total_lugares:,}')

        # Obtener IDs de lugares pendientes
        lugares_ids = list(lugares_pendientes.values_list('id', flat=True))

        # Contar fotos afectadas
        fotos_afectadas = Foto.objects.filter(lugar_id__in=lugares_ids).count()
        self.stdout.write(f'Fotos en esos lugares: {fotos_afectadas:,}')

        # Contar fotos con variantes
        fotos_con_mini = Foto.objects.filter(
            lugar_id__in=lugares_ids
        ).exclude(
            Q(imagen_miniatura__isnull=True) | Q(imagen_miniatura='')
        ).count()
        
        fotos_con_med = Foto.objects.filter(
            lugar_id__in=lugares_ids
        ).exclude(
            Q(imagen_mediana__isnull=True) | Q(imagen_mediana='')
        ).count()

        self.stdout.write(f'Fotos con miniatura a resetear: {fotos_con_mini:,}')
        self.stdout.write(f'Fotos con mediana a resetear: {fotos_con_med:,}')
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('  DRY-RUN: No se harán cambios'))
            self.stdout.write('')
            self.stdout.write('  Para ejecutar:')
            self.stdout.write('    python manage.py resetear_variantes_pendientes')
            return

        # Resetear en batches
        self.stdout.write('Reseteando variantes...')
        
        batch_size = 1000
        total_reset = 0
        
        for i in range(0, len(lugares_ids), batch_size):
            batch_ids = lugares_ids[i:i+batch_size]
            
            updated = Foto.objects.filter(lugar_id__in=batch_ids).update(
                imagen_miniatura=None,
                imagen_mediana=None
            )
            total_reset += updated
            
            self.stdout.write(f'  Progreso: {min(i+batch_size, len(lugares_ids)):,}/{len(lugares_ids):,} lugares | {total_reset:,} fotos reseteadas')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✅ Reseteadas {total_reset:,} fotos en {total_lugares:,} lugares'))
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.HTTP_INFO('  SIGUIENTE PASO'))
        self.stdout.write('=' * 70)
        self.stdout.write('  Ahora regenera las variantes:')
        self.stdout.write('    python manage.py imagenes_optimizar --limit 500')
        self.stdout.write('')

