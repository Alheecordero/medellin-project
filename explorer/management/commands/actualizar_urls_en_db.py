from django.core.management.base import BaseCommand
from django.db.models import Count
from explorer.models import Places, Foto

class Command(BaseCommand):
    help = 'PASO 2: Actualiza las URLs en la BD de AWS para que coincidan con los nombres estéticos creados en GCS.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra las URLs que se actualizarían sin guardar cambios',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.SUCCESS("🚀 INICIANDO PASO 2: Actualización de URLs en la base de datos..."))
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  MODO DRY-RUN: No se harán cambios reales en la base de datos."))

        try:
            # Anotamos lugares que tienen al menos una foto para procesar
            lugares = Places.objects.annotate(num_fotos=Count('fotos')).filter(num_fotos__gt=0)
            total_lugares = lugares.count()
            self.stdout.write(f"✅ Conexión con la BD exitosa. Se procesarán {total_lugares} lugares con fotos.")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error conectando con la base de datos: {e}"))
            return

        fotos_a_actualizar = []
        
        for lugar in lugares:
            # Obtener todas las fotos de este lugar, ordenadas por la más antigua primero
            fotos_del_lugar = Foto.objects.filter(lugar=lugar).order_by('id')
            
            for idx, foto in enumerate(fotos_del_lugar, 1):
                nueva_url = f"https://storage.googleapis.com/vivemedellin-bucket/images/{lugar.place_id}/{idx:02d}.jpg"
                
                # Si la URL actual ya es la correcta, no la procesamos
                if foto.imagen == nueva_url:
                    continue

                if dry_run:
                    self.stdout.write(f"  📸 {foto.imagen} -> {nueva_url}")

                foto.imagen = nueva_url
                fotos_a_actualizar.append(foto)

        if not fotos_a_actualizar:
            self.stdout.write(self.style.SUCCESS("\n🎉 No se encontraron URLs para actualizar. ¡Todo parece estar al día!"))
            return

        self.stdout.write(f"\n📊 Se actualizarán {len(fotos_a_actualizar)} URLs en la base de datos.")

        if not dry_run:
            self.stdout.write("⏳ Realizando actualización masiva (bulk_update)...")
            try:
                Foto.objects.bulk_update(fotos_a_actualizar, ['imagen'])
                self.stdout.write(self.style.SUCCESS("✅ ¡Actualización masiva completada!"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error durante el bulk_update: {e}"))
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS("🎉 PROCESO DE ACTUALIZACIÓN DE BD COMPLETADO"))
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  Recuerda: esto fue solo una simulación"))
        self.stdout.write(f"{'='*60}") 