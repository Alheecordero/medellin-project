from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from explorer.models import Places
from django.db import transaction

class Command(BaseCommand):
    help = 'Marca lugares como destacados basado en rating'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra los cambios que se harían sin aplicarlos'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Primero, veamos la distribución de ratings
        self.stdout.write('\nDistribución de ratings:')
        for rating in [4.0, 4.2, 4.5, 4.8]:
            # Usamos all_objects para ver todos los lugares en estadísticas
            count = Places.all_objects.filter(rating__gte=rating).count()
            self.stdout.write(f'Lugares con rating ≥ {rating}: {count}')

        # Obtener lugares que cumplen los criterios
        lugares_para_destacar = Places.objects.filter(
            rating__gt=4.5,  # Mayor a 4.5
            tiene_fotos=True  # Solo lugares con fotos
        )

        # Query separado para mostrar ejemplos
        lugares_ejemplos = lugares_para_destacar.order_by('-rating')[:10]

        # Estadísticas
        self.stdout.write('\nEstadísticas actuales:')
        # Usamos all_objects para estadísticas completas
        self.stdout.write(f'Total de lugares: {Places.all_objects.count()}')
        self.stdout.write(f'Lugares con fotos: {Places.all_objects.filter(tiene_fotos=True).count()}')
        self.stdout.write(f'Lugares que serán destacados: {lugares_para_destacar.count()}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nModo dry-run: No se aplicarán cambios'))
            self.stdout.write('\nEjemplos de lugares que serían destacados:')
            for lugar in lugares_ejemplos:
                self.stdout.write(self.style.SUCCESS(
                    f'- {lugar.nombre} (Rating: {lugar.rating})'
                ))
            return

        try:
            with transaction.atomic():
                # Reset todos los destacados
                # Usamos all_objects para resetear todos los lugares
                Places.all_objects.all().update(es_destacado=False)
                self.stdout.write(self.style.SUCCESS('✓ Reset de lugares destacados completado'))

                # Marcar los nuevos destacados
                lugares_para_destacar.update(es_destacado=True)
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Marcados {lugares_para_destacar.count()} lugares como destacados'
                ))

                # Mostrar ejemplos
                self.stdout.write('\nEjemplos de lugares destacados:')
                for lugar in lugares_ejemplos:
                    self.stdout.write(self.style.SUCCESS(
                        f'- {lugar.nombre} (Rating: {lugar.rating})'
                    ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error al actualizar lugares: {str(e)}'))
            return

        self.stdout.write(self.style.SUCCESS('\n¡Actualización completada con éxito!')) 