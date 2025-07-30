from django.core.management.base import BaseCommand
from django.db.models import Q
from explorer.models import Places, RegionOSM


class Command(BaseCommand):
    help = 'Poblar el campo show_in_home para optimizar el rendimiento del HomeView'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Resetear todos los lugares a show_in_home=False antes de poblar',
        )
        parser.add_argument(
            '--max-per-region',
            type=int,
            default=3,
            help='Máximo número de lugares por región (default: 3)',
        )

    def handle(self, *args, **options):
        self.stdout.write("🚀 Iniciando población del campo show_in_home...")
        
        # Reset si se especifica
        if options['reset']:
            self.stdout.write("🧹 Reseteando todos los lugares...")
            # Usamos all_objects para resetear todos los lugares
            Places.all_objects.update(show_in_home=False)
            self.stdout.write("✅ Reset completado")
        
        max_per_region = options['max_per_region']
        total_marcados = 0
        
        # FILTRO OPTIMIZADO: Solo regiones específicas de Medellín y área metropolitana
        regiones_validas = RegionOSM.objects.filter(
            Q(admin_level='8', ciudad='Medellín') |  # Comunas de Medellín
            Q(admin_level='6')  # Municipios del área metropolitana
        ).values_list('osm_id', flat=True)
        
        # Filtrar solo regiones que tienen lugares de calidad
        regiones_con_lugares = Places.objects.filter(
            comuna_osm_id__in=regiones_validas,
            tiene_fotos=True,
            rating__gte=4.0
        ).values_list('comuna_osm_id', flat=True).distinct()
        
        # Obtener info completa de estas regiones
        regiones_info = RegionOSM.objects.filter(
            osm_id__in=regiones_con_lugares
        ).values('osm_id', 'name').order_by('name')
        
        self.stdout.write(f"📍 Procesando {len(regiones_info)} regiones válidas con lugares de calidad")
        
        # OPTIMIZACIÓN: Actualizar en lotes en lugar de uno por uno
        lugares_para_marcar = []
        
        for region in regiones_info:
            osm_id = region['osm_id']
            nombre_region = region['name']
            
            # Obtener IDs de los mejores lugares de esta región
            mejores_lugares_ids = Places.objects.filter(
                comuna_osm_id=osm_id,
                tiene_fotos=True,
                rating__gte=4.0,
                show_in_home=False  # Solo los que no están marcados
            ).order_by('-rating', '-total_reviews', 'nombre').values_list('id', flat=True)[:max_per_region]
            
            cantidad_en_region = len(mejores_lugares_ids)
            if cantidad_en_region > 0:
                lugares_para_marcar.extend(mejores_lugares_ids)
                total_marcados += cantidad_en_region
                self.stdout.write(f"✅ {nombre_region}: {cantidad_en_region} lugares seleccionados")
        
        # Actualización masiva súper eficiente
        if lugares_para_marcar:
            self.stdout.write(f"🚀 Actualizando {len(lugares_para_marcar)} lugares en lote...")
            actualizado_count = Places.objects.filter(
                id__in=lugares_para_marcar
            ).update(show_in_home=True)
            self.stdout.write(f"✅ {actualizado_count} lugares actualizados exitosamente")
        
        self.stdout.write(
            self.style.SUCCESS(
                f"🎉 ¡Completado! {total_marcados} lugares marcados para mostrar en home"
            )
        )
        
        # Estadísticas finales
        # Usamos all_objects para estadísticas completas
        total_show_in_home = Places.all_objects.filter(show_in_home=True).count()
        total_places = Places.all_objects.count()
        
        self.stdout.write(
            f"📊 Estadísticas: {total_show_in_home}/{total_places} lugares "
            f"({(total_show_in_home/total_places*100):.1f}%) marcados para home"
        ) 