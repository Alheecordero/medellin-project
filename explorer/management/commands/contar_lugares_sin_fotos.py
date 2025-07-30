from django.core.management.base import BaseCommand
from explorer.models import Places
from django.db.models import Count

class Command(BaseCommand):
    help = 'Cuenta el total de lugares y cuántos de ellos no tienen fotos asociadas.'

    def handle(self, *args, **options):
        total_lugares = Places.objects.count()

        if total_lugares == 0:
            self.stdout.write(self.style.WARNING("No hay lugares en la base de datos."))
            return

        # Contar lugares que no tienen fotos.
        # Anotamos cada lugar con el número de fotos y luego filtramos los que tienen 0.
        lugares_sin_fotos = Places.objects.annotate(
            num_fotos=Count('fotos')
        ).filter(num_fotos=0).count()

        lugares_con_fotos = total_lugares - lugares_sin_fotos

        # Calcular el porcentaje
        if total_lugares > 0:
            porcentaje_sin_fotos = (lugares_sin_fotos / total_lugares) * 100
        else:
            porcentaje_sin_fotos = 0

        # Imprimir los resultados
        self.stdout.write(self.style.SUCCESS("📊 Estadísticas de Fotos en la Base de Datos 📊"))
        self.stdout.write("="*50)
        self.stdout.write(f"Total de lugares guardados: {self.style.NOTICE(total_lugares)}")
        self.stdout.write(f"Lugares con al menos una foto: {self.style.SUCCESS(lugares_con_fotos)}")
        self.stdout.write(f"Lugares sin fotos: {self.style.WARNING(str(lugares_sin_fotos))}")
        self.stdout.write(f"Porcentaje de lugares sin fotos: {porcentaje_sin_fotos:.2f}%")
        self.stdout.write("="*50) 