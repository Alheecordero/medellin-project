from django.core.management.base import BaseCommand
from explorer.models import Places, RegionOSM

class Command(BaseCommand):
    help = 'Asigna una RegionOSM a cada lugar basado en su ubicación geográfica.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra las asignaciones que se harían sin guardar cambios.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Reasigna regiones incluso para lugares que ya tienen una asignada.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(self.style.SUCCESS("🚀 Iniciando asignación de regiones a lugares..."))
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  MODO DRY-RUN: No se harán cambios reales en la base de datos."))

        if force:
            self.stdout.write(self.style.WARNING("⚡ MODO FORZADO: Se reasignarán todas las regiones."))
            places_to_process = Places.objects.filter(ubicacion__isnull=False)
        else:
            # Procesar solo los que no tienen una región asignada
            places_to_process = Places.objects.filter(ubicacion__isnull=False, comuna_osm_id__isnull=True)

        total_places = places_to_process.count()
        if total_places == 0:
            self.stdout.write(self.style.SUCCESS("✅ No hay lugares nuevos que procesar."))
            return
            
        self.stdout.write(f"🔍 Encontrados {total_places} lugares para procesar.")

        places_to_update = []
        no_encontrados = 0
        
        # Usar iterator() para manejar grandes cantidades de datos sin agotar la memoria
        # Se añade chunk_size=2000 debido al prefetch_related por defecto en el manager
        for i, place in enumerate(places_to_process.iterator(chunk_size=2000)):
            if (i + 1) % 500 == 0:
                self.stdout.write(f"  ... procesando lugar {i+1}/{total_places}")

            try:
                # La consulta espacial que hace la magia. PostGIS está optimizado para esto.
                region = RegionOSM.objects.filter(geom_4326__contains=place.ubicacion).first()
                
                if region:
                    if place.comuna_osm_id != region.osm_id:
                        place.comuna_osm_id = region.osm_id
                        places_to_update.append(place)
                else:
                    no_encontrados += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error procesando {place.nombre} (ID: {place.id}): {e}"))


        self.stdout.write(f"\n✅ Proceso de búsqueda finalizado.")

        if not places_to_update:
            self.stdout.write(self.style.SUCCESS("🎉 No se encontraron nuevas asignaciones para hacer. ¡Todo parece estar al día!"))
            if no_encontrados > 0:
                 self.stdout.write(self.style.WARNING(f"🤷 Ojo: {no_encontrados} lugares no cayeron dentro de ninguna región."))
            return

        self.stdout.write(f"\n📊 Se actualizarán {len(places_to_update)} lugares en la base de datos.")

        if not dry_run:
            self.stdout.write("⏳ Realizando actualización masiva (bulk_update)...")
            try:
                Places.objects.bulk_update(places_to_update, ['comuna_osm_id'])
                self.stdout.write(self.style.SUCCESS("✅ ¡Actualización masiva completada!"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error durante el bulk_update: {e}"))
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS("🎉 PROCESO DE ASIGNACIÓN COMPLETADO"))
        self.stdout.write(f"✅ Lugares actualizados: {len(places_to_update)}")
        self.stdout.write(f"🤷 Lugares sin región encontrada: {no_encontrados}")
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Recuerda: esto fue solo una simulación"))
        self.stdout.write(f"{'='*60}") 