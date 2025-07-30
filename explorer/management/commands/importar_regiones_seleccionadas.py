from django.core.management.base import BaseCommand
from django.db import connection, transaction
from explorer.models import RegionOSM

class Command(BaseCommand):
    help = 'Importa regiones OSM específicas de Medellín, Envigado, Itagüí, Rionegro y Guatapé desde planet_osm_polygon'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se importaría sin hacer cambios reales',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== Importación Selectiva de Regiones OSM ==="))
        
        # Ciudades objetivo
        ciudades_objetivo = {
            'Medellín': ['%medellín%', '%medellin%', '%comuna%'],
            'Envigado': ['%envigado%'],
            'Itagüí': ['%itagüí%', '%itagui%'],
            'Rionegro': ['%rionegro%'],
            'Guatapé': ['%guatapé%', '%guatape%']
        }
        
        with connection.cursor() as cursor:
            # Verificar que la tabla planet_osm_polygon existe
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'planet_osm_polygon'
            """)
            
            if cursor.fetchone()[0] == 0:
                self.stdout.write(self.style.ERROR("❌ La tabla planet_osm_polygon no existe"))
                return
            
            total_encontrados = 0
            regiones_por_ciudad = {}
            
            for ciudad, patrones in ciudades_objetivo.items():
                self.stdout.write(f"\n🔍 Buscando regiones de {ciudad}...")
                
                # Construir la consulta SQL con los patrones de la ciudad
                patrones_sql = "', '".join(patrones)
                sql_buscar = f"""
                    SELECT osm_id, name, admin_level, way_area, way
                    FROM planet_osm_polygon 
                    WHERE name IS NOT NULL 
                    AND LOWER(name) LIKE ANY(ARRAY['{patrones_sql}'])
                    ORDER BY name
                """
                
                cursor.execute(sql_buscar)
                resultados = cursor.fetchall()
                
                regiones_por_ciudad[ciudad] = resultados
                total_encontrados += len(resultados)
                
                self.stdout.write(f"   ✅ Encontradas {len(resultados)} regiones")
                
                # Mostrar primeras 5 regiones encontradas
                for i, (osm_id, name, admin_level, way_area, geom) in enumerate(resultados[:5]):
                    self.stdout.write(f"      • {name} (OSM: {osm_id}, Admin: {admin_level})")
                
                if len(resultados) > 5:
                    self.stdout.write(f"      ... y {len(resultados) - 5} más")
            
            self.stdout.write(f"\n📊 Total de regiones encontradas: {total_encontrados}")
            
            if options['dry_run']:
                self.stdout.write(self.style.WARNING("\n=== MODO DRY-RUN ==="))
                self.stdout.write("Las regiones encontradas se importarían a la nueva tabla RegionOSM")
                self.stdout.write("Ejecuta sin --dry-run para realizar la importación")
                return
            
            if total_encontrados == 0:
                self.stdout.write(self.style.WARNING("❌ No se encontraron regiones para importar"))
                return
            
            # Confirmar importación
            confirm = input(f"\n¿Importar {total_encontrados} regiones? (escribe 'SI' para confirmar): ")
            if confirm != 'SI':
                self.stdout.write(self.style.ERROR("❌ Importación cancelada"))
                return
            
            self.stdout.write(self.style.SUCCESS("🚀 Iniciando importación..."))
            
            # Limpiar tabla actual
            RegionOSM.objects.all().delete()
            self.stdout.write("   🗑️  Tabla RegionOSM limpiada")
            
            with transaction.atomic():
                importados = 0
                
                for ciudad, resultados in regiones_por_ciudad.items():
                    self.stdout.write(f"\n📥 Importando regiones de {ciudad}...")
                    
                    for osm_id, name, admin_level, way_area, geom_wkb in resultados:
                        try:
                            # Crear el registro
                            region = RegionOSM.objects.create(
                                osm_id=osm_id,
                                name=name,
                                admin_level=admin_level,
                                way_area=way_area,
                                geom=geom_wkb,
                                ciudad=ciudad
                            )
                            importados += 1
                            
                            if importados % 10 == 0:
                                self.stdout.write(f"   📋 Importados: {importados}/{total_encontrados}")
                        
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"      ❌ Error importando {name}: {e}"))
                
                self.stdout.write(f"\n✅ IMPORTACIÓN COMPLETADA")
                self.stdout.write(f"📊 Regiones importadas: {importados}")
                
                # Mostrar resumen por ciudad
                self.stdout.write(f"\n📋 Resumen por ciudad:")
                for ciudad in ciudades_objetivo.keys():
                    count = RegionOSM.objects.filter(ciudad=ciudad).count()
                    self.stdout.write(f"   🏘️  {ciudad}: {count} regiones")
                
                # Mostrar algunas regiones importadas
                self.stdout.write(f"\n🗺️  Primeras regiones importadas:")
                for region in RegionOSM.objects.all()[:10]:
                    self.stdout.write(f"   • {region.name} ({region.ciudad}) - OSM: {region.osm_id}")
                
                total_final = RegionOSM.objects.count()
                if total_final > 10:
                    self.stdout.write(f"   ... y {total_final - 10} más") 