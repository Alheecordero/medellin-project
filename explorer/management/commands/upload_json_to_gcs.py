from django.core.management.base import BaseCommand
from google.cloud import storage
import os

class Command(BaseCommand):
    help = 'Sube todos los archivos JSON locales de la carpeta api_json a GCS.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra los archivos que se subirían sin subirlos realmente',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.SUCCESS("🚀 Iniciando la subida de archivos JSON a Google Cloud Storage..."))
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  MODO DRY-RUN: No se subirán archivos reales."))

        # --- Configuración de rutas ---
        local_json_dir = 'api_json'
        gcs_destination_folder = 'places_json_per_id/'

        if not os.path.isdir(local_json_dir):
            self.stdout.write(self.style.ERROR(f"❌ El directorio local '{local_json_dir}' no existe. Abortando."))
            return

        # --- Conexión a GCS ---
        try:
            client = storage.Client()
            bucket = client.bucket('vivemedellin-bucket')
            self.stdout.write("✅ Conexión con GCS exitosa.")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error conectando con GCS: {e}"))
            return

        # --- Obtener lista de archivos locales ---
        local_files = [f for f in os.listdir(local_json_dir) if f.endswith('.json')]
        if not local_files:
            self.stdout.write(self.style.WARNING(f"No se encontraron archivos .json en '{local_json_dir}'."))
            return
            
        self.stdout.write(f"🔍 Encontrados {len(local_files)} archivos JSON para procesar.")
        
        subidos = 0
        omitidos = 0
        errores = 0

        # --- Proceso de subida ---
        for i, filename in enumerate(local_files, 1):
            local_path = os.path.join(local_json_dir, filename)
            gcs_path = f"{gcs_destination_folder}{filename}"
            
            self.stdout.write(f"\n--- Procesando {i}/{len(local_files)}: {filename} ---")
            
            try:
                blob = bucket.blob(gcs_path)

                if blob.exists():
                    self.stdout.write("✅ Ya existe en el bucket. Omitiendo.")
                    omitidos += 1
                    continue

                self.stdout.write(f"📤 Subiendo a {gcs_path}...")
                
                if not dry_run:
                    blob.upload_from_filename(local_path)
                    self.stdout.write(self.style.SUCCESS("   ¡Subido con éxito!"))
                
                subidos += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Error al subir: {e}"))
                errores += 1

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS("🎉 PROCESO DE SUBIDA COMPLETADO"))
        self.stdout.write(f"📤 Archivos subidos: {subidos}")
        self.stdout.write(f"✅ Omitidos (ya existían): {omitidos}")
        self.stdout.write(f"❌ Errores: {errores}")
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Recuerda: esto fue solo una simulación"))
        self.stdout.write(f"{'='*60}") 