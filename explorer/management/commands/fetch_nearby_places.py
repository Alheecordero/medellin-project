
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib.gis.geos import Point
import requests
from storages.backends.gcloud import GoogleCloudStorage

from explorer.models import Places, Foto

class Command(BaseCommand):
    help = 'Busca lugares cercanos usando la API de Google Places, descarga imágenes y las guarda en GCS y la base de datos.'

    # --- PARÁMETROS DE BÚSQUEDA (modificar según necesidad) ---
    LATITUD = 6.2095
    LONGITUD = -75.5668
    RADIO = 5000  # en metros
    # --- LISTA DE TIPOS DE LUGARES A BUSCAR ---
    TIPOS_DE_LUGARES = ["restaurant", "bar", "night_club", "cafe"]
    
    # Campos que queremos obtener de la API de detalles.
    FIELDS_TO_REQUEST = "id,displayName,formattedAddress,location,rating,userRatingCount,priceLevel,regularOpeningHours,websiteUri,nationalPhoneNumber,reviews,photos"


    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Iniciando la búsqueda de lugares cercanos con la NUEVA Places API..."))

        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            self.stdout.write(self.style.ERROR("La GOOGLE_API_KEY no está configurada en settings.py"))
            return

        for tipo_lugar in self.TIPOS_DE_LUGARES:
            self.stdout.write(self.style.SUCCESS(f"\n--- Buscando lugares del tipo: '{tipo_lugar}' ---"))
            self.buscar_y_procesar_lugares(api_key, tipo_lugar)

        self.stdout.write(self.style.SUCCESS("\nProceso completado para todos los tipos de lugares."))

    def buscar_y_procesar_lugares(self, api_key, tipo_lugar):
        nearby_url = "https://places.googleapis.com/v1/places:searchNearby"
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.id,places.displayName"
        }

        payload = {
            "includedTypes": [tipo_lugar],
            "maxResultCount": 20,
            "locationRestriction": {
                "circle": { "center": { "latitude": self.LATITUD, "longitude": self.LONGITUD }, "radius": self.RADIO }
            }
        }

        try:
            response = requests.post(nearby_url, json=payload, headers=headers)
            response.raise_for_status()
            nearby_data = response.json()
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Error en la solicitud a Nearby Search API v1: {e}"))
            return

        if not nearby_data or 'places' not in nearby_data:
            self.stdout.write(self.style.WARNING(f"No se encontraron lugares o hubo un error en la respuesta: {nearby_data}"))
            return
            
        self.stdout.write(f"Se encontraron {len(nearby_data.get('places', []))} lugares.")

        for place_data in nearby_data.get('places', []):
            place_name_full = place_data.get('id') 
            place_id = place_name_full.split('/')[-1] if place_name_full else None

            if not place_id or Places.objects.filter(place_id=place_id).exists():
                if place_id: self.stdout.write(self.style.WARNING(f"El lugar '{place_data.get('displayName', {}).get('text')}' (ID: {place_id}) ya existe. Omitiendo."))
                continue

            self.stdout.write(f"Procesando '{place_data.get('displayName', {}).get('text')}'...")
            
            details_url = f"https://places.googleapis.com/v1/places/{place_id}"
            details_headers = { "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": self.FIELDS_TO_REQUEST }

            try:
                details_response = requests.get(details_url, headers=details_headers)
                details_response.raise_for_status()
                details_data = details_response.json()
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"  Error obteniendo detalles para {place_id}: {e}"))
                continue
            
            if not details_data.get('photos'):
                self.stdout.write(self.style.WARNING(f"  -> El lugar no tiene fotos. Omitiendo."))
                continue

            self.guardar_json_en_gcs(details_data, place_id)

            loc = details_data.get('location', {})
            ubicacion = Point(loc.get('longitude'), loc.get('latitude'), srid=4326) if loc else None
            horario = details_data.get('regularOpeningHours', {})
            precio_str = details_data.get('priceLevel', '').replace('PRICE_LEVEL_', '').capitalize()

            try:
                place_obj, created = Places.objects.update_or_create(
                    place_id=place_id,
                    defaults={
                        'nombre': details_data.get('displayName', {}).get('text'),
                        'tipo': details_data.get('primaryType', '-'),
                        'direccion': details_data.get('formattedAddress'),
                        'telefono': details_data.get('nationalPhoneNumber'),
                        'sitio_web': details_data.get('websiteUri'),
                        'rating': details_data.get('rating'),
                        'total_reviews': details_data.get('userRatingCount'),
                        'precio': precio_str,
                        'ubicacion': ubicacion,
                        'horario_texto': "\n".join(horario.get('weekdayDescriptions', [])),
                        'abierto_ahora': horario.get('openNow'),
                        'reviews': details_data.get('reviews', []),
                    }
                )
                self.stdout.write(self.style.SUCCESS(f"  -> Lugar '{place_obj.nombre}' guardado (datos de texto)."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    Error al guardar en la base de datos: {e}"))
                continue

            photos_to_process = details_data.get('photos', [])[:5]
            self.stdout.write(f"  -> Procesando {len(photos_to_process)} fotos...")

            main_image_path, main_photo_ref = None, None
            for i, photo in enumerate(photos_to_process):
                if saved_path := self.procesar_foto(photo, api_key, place_id, is_main=(i == 0)):
                    Foto.objects.create(lugar=place_obj, imagen=saved_path)
                    if i == 0:
                        main_image_path, main_photo_ref = saved_path, photo.get('name')
            
            if main_image_path:
                place_obj.imagen = main_image_path
                place_obj.photo_reference = main_photo_ref
                place_obj.save()
                self.stdout.write(self.style.SUCCESS(f"  -> Imagen de portada actualizada para '{place_obj.nombre}'."))

    def procesar_foto(self, photo_data, api_key, place_id, is_main):
        photo_name = photo_data.get('name')
        if not photo_name: return None
        
        self.stdout.write(f"    -> Procesando foto: {photo_name.split('/')[-1]}")
        photo_request_url = f"https://places.googleapis.com/v1/{photo_name}/media?maxHeightPx=1024&key={api_key}"
        
        try:
            photo_response = requests.get(photo_request_url, stream=True)
            photo_response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f"      - Error descargando: {e}"))
            return None

        storage = GoogleCloudStorage()
        unique_photo_id = photo_name.split('/')[-1]
        folder = "portadas_lugares" if is_main else "imagenes_medellin"
        file_path = f"{folder}/{place_id}_{unique_photo_id}.jpg"
        
        try:
            saved_path = storage.save(file_path, ContentFile(photo_response.content))
            self.stdout.write(self.style.SUCCESS(f"      - Foto subida a GCS: {saved_path}"))
            return saved_path
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"      - Error al subir a GCS: {e}"))
            return None

    def guardar_json_en_gcs(self, data, place_id):
        self.stdout.write(f"  -> Guardando respuesta JSON para {place_id}...")
        storage = GoogleCloudStorage()
        file_name = f"json_responses_v1/{place_id}.json"
        
        try:
            import json
            json_content = json.dumps(data, indent=4)
            storage.save(file_name, ContentFile(json_content.encode('utf-8')))
            self.stdout.write(self.style.SUCCESS(f"  -> JSON guardado en GCS: {file_name}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    Error al guardar el JSON en GCS: {e}")) 