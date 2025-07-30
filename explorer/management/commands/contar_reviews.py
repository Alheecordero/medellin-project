from django.core.management.base import BaseCommand
from explorer.models import Places
from django.db.models import Count, Q

class Command(BaseCommand):
    help = 'Cuenta el total de lugares y cuántos de ellos tienen reviews guardadas.'

    def handle(self, *args, **options):
        # Contar el total de lugares
        total_lugares = Places.objects.count()
        
        if total_lugares == 0:
            self.stdout.write(self.style.WARNING("No hay lugares en la base de datos."))
            return
            
        # Contar lugares que tienen reviews.
        # Usamos Q para excluir tanto null como JSON vacíos ('[]' o '{}')
        lugares_con_reviews = Places.objects.filter(
            ~Q(reviews=None) & ~Q(reviews='[]') & ~Q(reviews='{}')
        ).count()
        
        # Calcular el porcentaje
        if total_lugares > 0:
            porcentaje = (lugares_con_reviews / total_lugares) * 100
        else:
            porcentaje = 0
            
        # Imprimir los resultados
        self.stdout.write(self.style.SUCCESS("📊 Estadísticas de Reviews en la Base de Datos 📊"))
        self.stdout.write("="*50)
        self.stdout.write(f"Total de lugares guardados: {self.style.NOTICE(total_lugares)}")
        self.stdout.write(f"Lugares con reviews: {self.style.SUCCESS(lugares_con_reviews)}")
        self.stdout.write(f"Porcentaje de lugares con reviews: {porcentaje:.2f}%")
        self.stdout.write("="*50) 