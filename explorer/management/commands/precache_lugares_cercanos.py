from django.core.management.base import BaseCommand
from django.core.cache import cache
from explorer.models import Places, Foto
from django.db.models import Prefetch
import time

class Command(BaseCommand):
    help = 'Pre-cachea lugares cercanos para mejorar performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Número de lugares a procesar'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        
        self.stdout.write(f"🚀 Pre-cacheando lugares cercanos para {limit} lugares...")
        
        # Obtener lugares con ubicación
        lugares = Places.objects.filter(
            tiene_fotos=True,
            ubicacion__isnull=False
        )[:limit]
        
        cached_count = 0
        total = lugares.count()
        
        for i, lugar in enumerate(lugares, 1):
            cache_key = f"nearby_optimized_{lugar.id}_500_3"
            
            # Solo cachear si no existe
            if cache.get(cache_key) is None:
                try:
                    # Consulta optimizada
                    result = list(Places.objects.filter(
                        tiene_fotos=True,
                        ubicacion__distance_lte=(lugar.ubicacion, 500)
                    ).exclude(
                        id=lugar.id
                    ).only(
                        'id', 'nombre', 'slug', 'tipo', 'rating', 'es_destacado', 'es_exclusivo'
                    ).prefetch_related(
                        Prefetch('fotos', queryset=Foto.objects.only('imagen')[:1], to_attr='cached_fotos')
                    ).order_by('-rating')[:3])
                    
                    cache.set(cache_key, result, 3600)  # 1 hora
                    cached_count += 1
                    
                    self.stdout.write(f"✅ {i}/{total}: {lugar.nombre} ({len(result)} cercanos)")
                    
                except Exception as e:
                    self.stdout.write(f"❌ Error en {lugar.nombre}: {e}")
            else:
                self.stdout.write(f"⏭️  {i}/{total}: {lugar.nombre} (ya cacheado)")
            
            # Pausa cada 10 para no sobrecargar
            if i % 10 == 0:
                time.sleep(0.1)
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ Pre-caché completado: {cached_count} lugares procesados")
        )
