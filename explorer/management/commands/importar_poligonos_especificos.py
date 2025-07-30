from django.core.management.base import BaseCommand
from django.db import connection, transaction
from explorer.models import RegionOSM

class Command(BaseCommand):
    help = 'Importa polígonos específicos usando OSM IDs exactos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se importaría sin hacer cambios reales',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== Importación de Polígonos Específicos ==="))
        
        # OSM IDs específicos proporcionados
        osm_ids_especificos = [
            -1350599, -3947503, -1343279, -1307284, -1307270, -1307277,
            -7680678, -7680807, -7680859, -11937925,
            -7676068, -7676069, -7680798, -7680904, -7680903,
            -7673972, -7673973, -7680403, -7673971, -7677386,
            -7680799, -7680490
        ]
        
        self.stdout.write(f"📋 OSM IDs a buscar: {len(osm_ids_especificos)} polígonos")
        
        with connection.cursor() as cursor:
            # Verificar que la tabla existe
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'planet_osm_polygon'
            """)
            
            if cursor.fetchone()[0] == 0:
                self.stdout.write(self.style.ERROR("❌ La tabla planet_osm_polygon no existe"))
                return
            
            # Buscar los polígonos específicos
            osm_ids_str = ', '.join(map(str, osm_ids_especificos))
            sql_buscar = f"""
                SELECT osm_id, name, admin_level, way_area, way
                FROM planet_osm_polygon 
                WHERE osm_id IN ({osm_ids_str})
                ORDER BY name
            """
            
            cursor.execute(sql_buscar)
            poligonos_encontrados = cursor.fetchall()
            
            self.stdout.write(f"✅ Encontrados {len(poligonos_encontrados)} de {len(osm_ids_especificos)} polígonos")
            
            if len(poligonos_encontrados) < len(osm_ids_especificos):
                encontrados_ids = [p[0] for p in poligonos_encontrados]
                faltantes = [osm_id for osm_id in osm_ids_especificos if osm_id not in encontrados_ids]
                self.stdout.write(self.style.WARNING(f"⚠️  No encontrados: {faltantes}"))
            
            if options['dry_run']:
                self.stdout.write(self.style.WARNING("\n=== MODO DRY-RUN ==="))
                self.stdout.write("Polígonos que se importarían:")
                
                for osm_id, name, admin_level, way_area, geom in poligonos_encontrados:
                    area_km2 = (way_area / 1000000) if way_area else 0
                    ciudad = self.determinar_ciudad(name, osm_id)
                    self.stdout.write(f"   🏘️  {name or 'Sin nombre'} (OSM: {osm_id}) - {ciudad} - {area_km2:.2f} km²")
                
                self.stdout.write("\nEjecuta sin --dry-run para realizar la importación")
                return
            
            if not poligonos_encontrados:
                self.stdout.write(self.style.WARNING("❌ No se encontraron polígonos para importar"))
                return
            
            # Confirmar importación
            confirm = input(f"\n¿Importar {len(poligonos_encontrados)} polígonos? (escribe 'SI' para confirmar): ")
            if confirm != 'SI':
                self.stdout.write(self.style.ERROR("❌ Importación cancelada"))
                return
            
            self.stdout.write(self.style.SUCCESS("🚀 Iniciando importación..."))
            
            # Limpiar tabla actual
            RegionOSM.objects.all().delete()
            self.stdout.write("   🗑️  Tabla RegionOSM limpiada")
            
            with transaction.atomic():
                importados = 0
                
                for osm_id, name, admin_level, way_area, geom_wkb in poligonos_encontrados:
                    try:
                        ciudad = self.determinar_ciudad(name, osm_id)
                        
                        # Crear el objeto con la geometría original en 4326
                        region = RegionOSM.objects.create(
                            osm_id=osm_id,
                            name=name or f"Región OSM {osm_id}",
                            admin_level=admin_level,
                            way_area=way_area,
                            geom_4326=geom_wkb,  # Los datos originales están en 4326
                            ciudad=ciudad
                        )
                        
                        # Generar automáticamente la geometría en 3857
                        region.ensure_both_geoms()
                        region.save()
                        importados += 1
                        area_km2 = (way_area / 1000000) if way_area else 0
                        self.stdout.write(f"   ✅ {region.name} ({ciudad}) - {area_km2:.2f} km²")
                        
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"   ❌ Error importando OSM {osm_id}: {e}"))
                
                self.stdout.write(f"\n✅ IMPORTACIÓN COMPLETADA")
                self.stdout.write(f"📊 Polígonos importados: {importados}")
                
                # Mostrar resumen por ciudad
                self.stdout.write(f"\n📋 Resumen por ciudad:")
                for ciudad in ['Medellín', 'Itagüí', 'Rionegro', 'Sabaneta', 'Envigado', 'Guatapé']:
                    count = RegionOSM.objects.filter(ciudad=ciudad).count()
                    if count > 0:
                        self.stdout.write(f"   🏘️  {ciudad}: {count} polígonos")
                
                total_final = RegionOSM.objects.count()
                self.stdout.write(f"\n🗺️  Total en la base de datos: {total_final} polígonos")

    def determinar_ciudad(self, name, osm_id):
        """Determina la ciudad basándose en el nombre y/o OSM ID"""
        if not name:
            name = ""
        
        name_lower = name.lower()
        
        # OSM IDs conocidos de Medellín (comunas)
        medellin_ids = [
            -7680678, -7680807, -7680859, -11937925,
            -7676068, -7676069, -7680798, -7680904, -7680903,
            -7673972, -7673973, -7680403, -7673971, -7677386,
            -7680799, -7680490
        ]
        
        if osm_id in medellin_ids:
            return "Medellín"
        elif 'comuna' in name_lower or 'medellín' in name_lower or 'medellin' in name_lower:
            return "Medellín"
        elif 'envigado' in name_lower or osm_id == -1307277:
            return "Envigado"
        elif 'itagüí' in name_lower or 'itagui' in name_lower or osm_id == -1343279:
            return "Itagüí"
        elif 'sabaneta' in name_lower or osm_id == -1307270:
            return "Sabaneta"
        elif 'rionegro' in name_lower or osm_id == -3947503:
            return "Rionegro"
        elif osm_id == -1307284:  # La Estrella
            return "La Estrella"
        elif 'guatapé' in name_lower or 'guatape' in name_lower or osm_id == -1350599:
            return "Guatapé"
        else:
            return "Otra" 