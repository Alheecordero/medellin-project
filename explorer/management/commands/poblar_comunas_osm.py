from django.core.management.base import BaseCommand
from django.db import connection
from explorer.models import RegionOSM

class Command(BaseCommand):
    help = 'Pobla la tabla RegionOSM con los datos de las 16 comunas de Medellín'

    # OSM IDs de las 16 comunas de Medellín
    OSM_IDS_MEDELLIN = [
        -7680678, -7680807, -7680859, -11937925,
        -7676068, -7676069, -7680798, -7680904, -7680903,
        -7673972, -7673973, -7680403, -7673971, -7677386,
        -7680799, -7680490
    ]

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("--- Poblando tabla RegionOSM con comunas ---"))
        
        # Obtener datos de las comunas desde OSM
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT osm_id, name, admin_level, way_area
                FROM planet_osm_polygon 
                WHERE osm_id = ANY(%s)
                ORDER BY name
            """, [self.OSM_IDS_MEDELLIN])
            
            comunas_osm = cursor.fetchall()
        
        if not comunas_osm:
            self.stdout.write(self.style.ERROR("No se encontraron datos de comunas en OSM"))
            return
            
        self.stdout.write(f"Encontradas {len(comunas_osm)} comunas en OSM")
        
        creadas = 0
        actualizadas = 0
        
        for osm_id, name, admin_level, way_area in comunas_osm:
            # Crear o actualizar el registro
            region, created = RegionOSM.objects.update_or_create(
                osm_id=osm_id,
                defaults={
                    'name': name,
                    'admin_level': admin_level,
                    'way_area': way_area
                }
            )
            
            if created:
                creadas += 1
                self.stdout.write(f"✅ Creada: {name} (ID: {osm_id})")
            else:
                actualizadas += 1
                self.stdout.write(f"🔄 Actualizada: {name} (ID: {osm_id})")
        
        # Resumen
        self.stdout.write(self.style.SUCCESS(f"\n--- Resumen ---"))
        self.stdout.write(f"✅ Comunas creadas: {creadas}")
        self.stdout.write(f"🔄 Comunas actualizadas: {actualizadas}")
        self.stdout.write(f"📊 Total procesadas: {len(comunas_osm)}")
        
        # Verificar que las comunas estén disponibles para los lugares
        lugares_con_comuna = RegionOSM.objects.filter(
            osm_id__in=[place.comuna_osm_id for place in __import__('explorer.models', fromlist=['Places']).Places.objects.filter(comuna_osm_id__isnull=False)]
        ).count()
        
        self.stdout.write(f"🏠 Lugares con comuna disponible: {lugares_con_comuna}")
        self.stdout.write(self.style.SUCCESS("--- Proceso completado ---")) 