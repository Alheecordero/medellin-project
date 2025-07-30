from django.core.management.base import BaseCommand, CommandError
from explorer.models import Places
import json

class Command(BaseCommand):
    help = 'Muestra las reviews de un lugar específico a partir de su slug.'

    def add_arguments(self, parser):
        parser.add_argument('slug', type=str, help='El slug del lugar para el cual mostrar las reviews.')

    def handle(self, *args, **options):
        slug = options['slug']
        
        try:
            lugar = Places.objects.get(slug=slug)
        except Places.DoesNotExist:
            raise CommandError(f'El lugar con el slug "{slug}" no fue encontrado.')
            
        self.stdout.write(self.style.SUCCESS(f"Mostrando reviews para: {lugar.nombre} (Slug: {lugar.slug})"))
        
        reviews = lugar.reviews
        
        if not reviews:
            self.stdout.write(self.style.WARNING("Este lugar no tiene reviews guardadas en la base de datos."))
            return
            
        if not isinstance(reviews, list):
            self.stdout.write(self.style.ERROR("El formato de las reviews no es una lista. Mostrando datos en crudo:"))
            self.stdout.write(json.dumps(reviews, indent=2, ensure_ascii=False))
            return
            
        self.stdout.write(f"Se encontraron {len(reviews)} reviews:\n")
        
        for i, review in enumerate(reviews, 1):
            autor = review.get('authorAttribution', {}).get('displayName', 'Anónimo')
            rating = review.get('rating')
            # El texto de la review está anidado en la nueva API
            texto_dict = review.get('originalText', {})
            texto = texto_dict.get('text', 'Sin texto.') if isinstance(texto_dict, dict) else 'Formato de texto inesperado.'
            
            # Limitar el texto para que sea legible
            texto_corto = (texto[:150] + '...') if len(texto) > 150 else texto
            
            self.stdout.write(f"--- Review #{i} ---")
            self.stdout.write(f"  Autor: {self.style.NOTICE(autor)}")
            self.stdout.write(f"  Rating: {'⭐' * int(rating) if isinstance(rating, int) else rating}")
            self.stdout.write(f"  Texto: {texto_corto.strip()}")
            self.stdout.write("-" * 20)
            
        self.stdout.write(self.style.SUCCESS("\nPrueba finalizada.")) 