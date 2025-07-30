from django.core.management.base import BaseCommand
from explorer.models import Places
import os

class Command(BaseCommand):
    help = 'Actualiza las rutas de los archivos JSON en la BD para que coincidan con los subidos a GCS.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra las rutas que se actualizarían sin guardar los cambios',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.SUCCESS("🚀 Iniciando actualización de rutas de JSON en la base de datos..."))
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  MODO DRY-RUN: No se harán cambios reales en la base de datos."))

        try:
            lugares = Places.objects.all()
            total_lugares = lugares.count()
            self.stdout.write(f"✅ Conexión con la BD exitosa. Se procesarán {total_lugares} lugares.")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error conectando con la base de datos: {e}"))
            return

        lugares_a_actualizar = []
        
        # Carpeta destino en GCS
        gcs_destination_folder = 'places_json_per_id/'

        for lugar in lugares:
            # Construir el nombre de archivo esperado
            json_filename = f"{lugar.place_id}_{lugar.slug}.json"
            
            # Construir la nueva ruta/URL de GCS
            # Ojo: El FileField de Django espera una ruta relativa al bucket, no una URL completa.
            nueva_ruta_gcs = os.path.join(gcs_destination_folder, json_filename)

            # Si la ruta actual ya es la correcta, no la procesamos
            if lugar.google_api_json and lugar.google_api_json.name == nueva_ruta_gcs:
                continue

            if dry_run:
                ruta_antigua = lugar.google_api_json.name if lugar.google_api_json else "N/A"
                self.stdout.write(f"  📄 {ruta_antigua} -> {nueva_ruta_gcs}")

            lugar.google_api_json.name = nueva_ruta_gcs
            lugares_a_actualizar.append(lugar)

        if not lugares_a_actualizar:
            self.stdout.write(self.style.SUCCESS("\n🎉 No se encontraron rutas de JSON para actualizar. ¡Todo parece estar al día!"))
            return

        self.stdout.write(f"\n📊 Se actualizarán {len(lugares_a_actualizar)} rutas de JSON en la base de datos.")

        if not dry_run:
            self.stdout.write("⏳ Realizando actualización masiva (bulk_update)...")
            try:
                # Actualizamos solo el campo 'google_api_json'
                Places.objects.bulk_update(lugares_a_actualizar, ['google_api_json'])
                self.stdout.write(self.style.SUCCESS("✅ ¡Actualización masiva completada!"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error durante el bulk_update: {e}"))
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS("🎉 PROCESO DE ACTUALIZACIÓN DE RUTAS JSON COMPLETADO"))
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Recuerda: esto fue solo una simulación"))
        self.stdout.write(f"{'='*60}") 