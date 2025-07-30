from django.core.management.base import BaseCommand
from google.cloud import storage
from collections import defaultdict

class Command(BaseCommand):
    help = 'PASO 1: Renombra todos los archivos en GCS a un formato estético. NO TOCA LA BASE DE DATOS.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra los archivos que renombraría sin hacer cambios',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.SUCCESS("🚀 INICIANDO PASO 1: Renombrado de archivos en Google Cloud Storage..."))
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  MODO DRY-RUN: No se harán cambios reales en el bucket."))

        try:
            client = storage.Client()
            bucket = client.bucket('vivemedellin-bucket')
            self.stdout.write("✅ Conexión con GCS exitosa.")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error conectando con GCS: {e}"))
            return

        # 1. Listar todos los archivos y agruparlos por place_id
        self.stdout.write("🔍 Listando todos los blobs en el prefijo 'images/'... Esto puede tardar.")
        blobs = bucket.list_blobs(prefix='images/')
        
        archivos_por_lugar = defaultdict(list)
        for blob in blobs:
            try:
                # Extraer place_id de la ruta: images/Ch.../archivo.jpg
                parts = blob.name.split('/')
                if len(parts) >= 3:
                    place_id = parts[1]
                    archivos_por_lugar[place_id].append(blob)
            except Exception:
                continue
        
        self.stdout.write(f"📊 Encontrados {len(archivos_por_lugar)} lugares con imágenes.")
        renombrados = 0
        errores = 0

        # 2. Iterar por cada lugar y renombrar sus archivos
        for i, (place_id, blob_list) in enumerate(archivos_por_lugar.items(), 1):
            self.stdout.write(f"\n--- Procesando lugar {i}/{len(archivos_por_lugar)} (ID: {place_id}) ---")

            # Filtrar solo los que necesitan ser renombrados (nombres largos)
            a_renombrar = sorted(
                [b for b in blob_list if len(b.name.split('/')[-1]) > 20],
                key=lambda b: b.time_created
            )

            if not a_renombrar:
                self.stdout.write("✅ No hay archivos con nombres largos para este lugar.")
                continue
            
            self.stdout.write(f"🔄 Se renombrarán {len(a_renombrar)} archivos.")

            for idx, blob_actual in enumerate(a_renombrar, 1):
                try:
                    nueva_ruta = f"images/{place_id}/{idx:02d}.jpg"
                    self.stdout.write(f"  📸 {blob_actual.name} -> {nueva_ruta}")

                    if dry_run:
                        continue

                    # Renombrar (copiar y borrar)
                    nuevo_blob = bucket.blob(nueva_ruta)
                    if not nuevo_blob.exists():
                        bucket.copy_blob(blob_actual, bucket, nueva_ruta)
                        blob_actual.delete()
                        renombrados += 1
                    else:
                        self.stdout.write(self.style.WARNING("    ⚠️  El nuevo nombre ya existe. Omitiendo copia y borrando original."))
                        blob_actual.delete()

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    ❌ Error renombrando {blob_actual.name}: {e}"))
                    errores += 1
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS("🎉 PROCESO DE RENOMBRADO EN GCS COMPLETADO"))
        self.stdout.write(f"🖼️  Archivos renombrados: {renombrados}")
        self.stdout.write(f"❌ Errores: {errores}")
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Recuerda: esto fue solo una simulación"))
        self.stdout.write(f"{'='*60}") 