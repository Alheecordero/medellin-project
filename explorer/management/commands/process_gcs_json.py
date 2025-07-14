
import json
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib.gis.geos import Point
import requests
from storages.backends.gcloud import GoogleCloudStorage

from explorer.models import Places, Foto
from django.db import transaction, IntegrityError
import time

class Command(BaseCommand):
    help = 'Procesa archivos JSON desde GCS, poblando la base de datos con lugares y fotos.'

    JSON_FOLDER = 'json_responses_v1/'
    IMAGE_FOLDER = 'images/'
    MAX_PHOTOS_PER_PLACE = 5

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("--- Iniciando el procesamiento de archivos JSON desde GCS ---"))
        
        storage = GoogleCloudStorage()
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            self.stdout.write(self.style.ERROR("La GOOGLE_API_KEY no está configurada."))
            return

        try:
            # Listar todos los archivos en el bucket es costoso, mejor listamos el directorio específico.
            archivos_json = storage.listdir(self.JSON_FOLDER)[1] # listdir devuelve ([directorios], [archivos])
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"No se pudieron listar los archivos de GCS en '{self.JSON_FOLDER}'. ¿La carpeta existe? Error: {e}"))
            return

        if not archivos_json:
            self.stdout.write(self.style.WARNING("No se encontraron archivos JSON para procesar."))
            return

        self.stdout.write(f"Se encontraron {len(archivos_json)} archivos JSON para procesar.")

        for nombre_archivo in archivos_json:
            ruta_completa = f"{self.JSON_FOLDER}{nombre_archivo}"
            self.procesar_archivo_json(storage, ruta_completa, api_key)
            time.sleep(0.1) # Pequeña pausa para no sobrecargar los servicios

        self.stdout.write(self.style.SUCCESS("\n--- Proceso completado ---"))

    def procesar_archivo_json(self, storage, ruta_archivo, api_key):
        place_id = ruta_archivo.split('/')[-1].replace('.json', '')
        
        if Places.objects.filter(place_id=place_id).exists():
            self.stdout.write(self.style.WARNING(f"El lugar con ID '{place_id}' ya existe en la base de datos. Omitiendo."))
            return

        self.stdout.write(self.style.HTTP_INFO(f"\nProcesando archivo: {ruta_archivo}"))

        try:
            with storage.open(ruta_archivo) as f:
                data = json.load(f)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  -> Error al leer o parsear el archivo JSON: {e}"))
            return
        
        try:
            with transaction.atomic():
                # --- Crear la instancia del Lugar ---
                lat = data.get('location', {}).get('latitude', 0)
                lng = data.get('location', {}).get('longitude', 0)
                location_point = Point(lng, lat, srid=4326)

                # Comuna y Zona deshabilitados temporalmente hasta aclarar su origen
                # comuna = Comuna.objects.filter(geom__contains=location_point).first()
                # zona = Zona.objects.filter(geom__contains=location_point).first()

                nuevo_lugar = Places.objects.create(
                    place_id=data.get('id', place_id),
                    nombre=data.get('displayName', {}).get('text', 'Sin nombre'),
                    direccion=data.get('formattedAddress', 'Sin dirección'),
                    ubicacion=location_point,
                    rating=data.get('rating', 0),
                    total_reviews=data.get('userRatingCount', 0),
                    # comuna=comuna,
                    # zona=zona,
                    sitio_web=data.get('websiteUri', ''),
                    telefono=data.get('nationalPhoneNumber', '')
                )
                self.stdout.write(self.style.SUCCESS(f"  -> Lugar '{nuevo_lugar.nombre}' creado en la base de datos."))

                # --- Procesar y guardar fotos ---
                fotos = data.get('photos', [])
                if fotos:
                    self.stdout.write(f"  -> Se encontraron {len(fotos)} fotos. Procesando hasta {self.MAX_PHOTOS_PER_PLACE}...")
                    for foto_data in fotos[:self.MAX_PHOTOS_PER_PLACE]:
                        self.procesar_y_guardar_foto(storage, foto_data, nuevo_lugar, api_key)
                else:
                    self.stdout.write(self.style.WARNING("  -> No se encontraron fotos para este lugar."))

        except IntegrityError as e:
            self.stdout.write(self.style.ERROR(f"  -> Error de integridad al guardar en la BD para el ID '{place_id}'. Es posible que ya exista. Error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  -> Ocurrió un error inesperado procesando el ID '{place_id}': {e}"))


    def procesar_y_guardar_foto(self, storage, foto_data, lugar, api_key):
        # El 'name' es el identificador único de la foto para la API
        photo_name = foto_data.get('name') 
        if not photo_name:
            return

        unique_photo_id = photo_name.split('/')[-1]
        gcs_image_path = f"{self.IMAGE_FOLDER}{lugar.place_id}/{unique_photo_id}.jpg"

        # Verificar si la imagen ya fue procesada y existe en la BD
        if Foto.objects.filter(lugar=lugar, imagen__icontains=unique_photo_id).exists():
             self.stdout.write(self.style.WARNING(f"    -> Foto {unique_photo_id} ya existe en la BD. Omitiendo."))
             return
        
        # Verificar si el archivo ya existe en GCS para no volver a descargarlo
        if not storage.exists(gcs_image_path):
            self.stdout.write(f"    -> Descargando foto: {unique_photo_id}")
            # Construir la URL para obtener la imagen
            photo_url = f"https://places.googleapis.com/v1/{photo_name}/media?maxHeightPx=1200&key={api_key}"
            
            try:
                response = requests.get(photo_url, timeout=20)
                response.raise_for_status()
                # Guardar la imagen en GCS
                storage.save(gcs_image_path, ContentFile(response.content))
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"      -> Error descargando imagen: {e}"))
                return
        else:
            self.stdout.write(self.style.WARNING(f"    -> La imagen ya existe en GCS: {gcs_image_path}. Usando existente."))
        
        # Obtener la URL pública y guardar en la BD
        public_url = storage.url(gcs_image_path)
        Foto.objects.create(
            lugar=lugar,
            imagen=public_url,
            descripcion=f"Foto de {lugar.nombre}"
        )
        self.stdout.write(self.style.SUCCESS(f"      -> Foto guardada en la base de datos con URL: {public_url}"))
        time.sleep(0.1) # Pequeña pausa para no sobrecargar la API de fotos 