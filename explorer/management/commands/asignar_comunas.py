from django.core.management.base import BaseCommand
from django.db import connection
from explorer.models import Places

class Command(BaseCommand):
    help = 'Asigna comunas a los lugares basándose en su ubicación geográfica usando datos OSM'

    # OSM IDs de las 16 comunas de Medellín (del views.py)
    OSM_IDS_MEDELLIN = [
        -7680678, -7680807, -7680859, -11937925,
        -7676068, -7676069, -7680798, -7680904, -7680903,
        -7673972, -7673973, -7680403, -7673971, -7677386,
        -7680799, -7680490
    ]

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("--- Iniciando asignación de comunas ---"))
        
        # Verificar que tenemos las 16 comunas de Medellín
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM planet_osm_polygon 
                WHERE osm_id = ANY(%s)
            """, [self.OSM_IDS_MEDELLIN])
            comunas_count = cursor.fetchone()[0]
            
        if comunas_count != 16:
            self.stdout.write(self.style.ERROR(f"Solo se encontraron {comunas_count} de 16 comunas esperadas"))
            return
            
        self.stdout.write(f"✅ Encontradas las 16 comunas de Medellín en los datos OSM")
        
        # Obtener lugares sin comuna asignada
        lugares_sin_comuna = Places.objects.filter(comuna_osm_id__isnull=True)
        total_lugares = lugares_sin_comuna.count()
        
        if total_lugares == 0:
            self.stdout.write(self.style.SUCCESS("Todos los lugares ya tienen comuna asignada"))
            return
            
        self.stdout.write(f"Procesando {total_lugares} lugares sin comuna...")
        
        lugares_actualizados = 0
        lugares_sin_asignar = 0
        
        for lugar in lugares_sin_comuna:
            if lugar.ubicacion:
                # Buscar la comuna que contiene este punto
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT name, osm_id 
                        FROM planet_osm_polygon 
                        WHERE osm_id = ANY(%s)
                        AND ST_Contains(way, ST_Transform(ST_GeomFromText(%s, 4326), 3857))
                        LIMIT 1
                    """, [self.OSM_IDS_MEDELLIN, lugar.ubicacion.wkt])
                    
                    resultado = cursor.fetchone()
                    
                if resultado:
                    comuna_nombre, osm_id = resultado
                    
                    lugar.comuna_osm_id = osm_id
                    lugar.save(update_fields=['comuna_osm_id'])
                    lugares_actualizados += 1
                    
                    self.stdout.write(f"✅ {lugar.nombre} → {comuna_nombre}")
                else:
                    lugares_sin_asignar += 1
                    self.stdout.write(f"❌ {lugar.nombre} → No se encontró comuna")
            else:
                lugares_sin_asignar += 1
                self.stdout.write(f"⚠️  {lugar.nombre} → Sin ubicación")
        
        # Resumen final
        self.stdout.write(self.style.SUCCESS("\n--- Resumen ---"))
        self.stdout.write(f"✅ Lugares actualizados: {lugares_actualizados}")
        self.stdout.write(f"❌ Lugares sin asignar: {lugares_sin_asignar}")
        self.stdout.write(f"📊 Total procesados: {total_lugares}")
        
        # Mostrar distribución por comuna
        self.stdout.write(self.style.SUCCESS("\n--- Distribución por Comuna ---"))
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT p.name, COUNT(*) as cantidad
                FROM explorer_places ep
                JOIN planet_osm_polygon p ON ep.comuna_osm_id = p.osm_id
                WHERE ep.comuna_osm_id IS NOT NULL
                GROUP BY p.name
                ORDER BY cantidad DESC
            """)
            
            for comuna, cantidad in cursor.fetchall():
                self.stdout.write(f"📍 {comuna}: {cantidad} lugares")
        
        self.stdout.write(self.style.SUCCESS("\n--- Proceso completado ---")) 