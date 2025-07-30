from django.core.management.base import BaseCommand
from django.db.models import Count, Q, F
from explorer.models import Places
from django.db import transaction

class Command(BaseCommand):
    help = 'Actualiza el campo tiene_fotos en todos los lugares y marca los que no tienen fotos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra los cambios que se harían sin aplicarlos',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Obtener lugares con y sin fotos usando una subconsulta
        # Usamos all_objects para ver todos los lugares, no solo los que tienen fotos
        lugares = Places.all_objects.annotate(
            num_fotos=Count('fotos')
        )
        
        # Contadores para el reporte
        total_lugares = lugares.count()
        lugares_sin_fotos = lugares.filter(num_fotos=0)
        lugares_con_fotos = lugares.filter(num_fotos__gt=0)
        
        # Mostrar estadísticas iniciales
        self.stdout.write(self.style.SUCCESS(f'Total de lugares: {total_lugares}'))
        self.stdout.write(self.style.WARNING(f'Lugares sin fotos: {lugares_sin_fotos.count()}'))
        self.stdout.write(self.style.SUCCESS(f'Lugares con fotos: {lugares_con_fotos.count()}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Modo dry-run: No se aplicarán cambios'))
            return
        
        try:
            with transaction.atomic():
                # Actualizar lugares con fotos
                lugares_con_fotos.update(tiene_fotos=True)
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Marcados {lugares_con_fotos.count()} lugares como tiene_fotos=True'
                ))
                
                # Actualizar lugares sin fotos
                lugares_sin_fotos.update(tiene_fotos=False)
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Marcados {lugares_sin_fotos.count()} lugares como tiene_fotos=False'
                ))
                
                # Mostrar algunos ejemplos de lugares sin fotos
                self.stdout.write('\nEjemplos de lugares sin fotos:')
                for lugar in lugares_sin_fotos[:5]:
                    self.stdout.write(self.style.WARNING(
                        f'- {lugar.nombre} (ID: {lugar.id}, Rating: {lugar.rating})'
                    ))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error al actualizar lugares: {str(e)}'))
            return
        
        self.stdout.write(self.style.SUCCESS('¡Actualización completada con éxito!')) 