
from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import json
from storages.backends.gcloud import GoogleCloudStorage

class Command(BaseCommand):
    help = 'Busca lugares en Google Places y guarda la respuesta JSON completa en GCS.'

    # --- PARÁMETROS DE BÚSQUEDA ---
    LATITUD = 6.2095
    LONGITUD = -75.5668
    RADIO = 5000  # en metros
    TIPOS_DE_LUGARES = ["restaurant", "bar", "night_club", "cafe"]
    
    # Para obtener todos los campos disponibles de la API, usamos "*".
    FIELDS_TO_REQUEST = "*"
    JSON_FOLDER = 'json_responses_v1/'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Iniciando la recolección de datos de Google Places..."))

        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            self.stdout.write(self.style.ERROR("La GOOGLE_API_KEY no está configurada."))
            return

        for tipo_lugar in self.TIPOS_DE_LUGARES:
            self.stdout.write(self.style.SUCCESS(f"\n--- Buscando lugares del tipo: '{tipo_lugar}' ---"))
            self.buscar_y_guardar_json(api_key, tipo_lugar)

        self.stdout.write(self.style.SUCCESS("\nProceso de recolección completado."))

    def buscar_y_guardar_json(self, api_key, tipo_lugar):
        nearby_url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.id"
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
            self.stdout.write(self.style.ERROR(f"Error en Nearby Search API: {e}"))
            return

        lugares = nearby_data.get('places', [])
        self.stdout.write(f"Se encontraron {len(lugares)} lugares potenciales.")

        for place_summary in lugares:
            place_id = place_summary.get('id', '').split('/')[-1]
            if not place_id:
                continue

            # Verificar si el JSON ya existe para no volver a descargarlo
            storage = GoogleCloudStorage()
            file_name = f"{self.JSON_FOLDER}{place_id}.json"
            if storage.exists(file_name):
                self.stdout.write(self.style.WARNING(f"  -> JSON para el ID '{place_id}' ya existe. Omitiendo."))
                continue

            self.stdout.write(f"Procesando ID: '{place_id}'...")
            
            details_url = f"https://places.googleapis.com/v1/places/{place_id}"
            details_headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": self.FIELDS_TO_REQUEST}

            try:
                details_response = requests.get(details_url, headers=details_headers)
                details_response.raise_for_status()
                details_data = details_response.json()
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"  Error obteniendo detalles para {place_id}: {e}"))
                continue
            
            self.guardar_json_en_gcs(details_data, place_id)

    def guardar_json_en_gcs(self, data, place_id):
        nombre_lugar = data.get('displayName', {}).get('text', place_id)
        self.stdout.write(f"  -> Guardando JSON para '{nombre_lugar}'...")
        storage = GoogleCloudStorage()
        file_name = f"{self.JSON_FOLDER}{place_id}.json"
        
        try:
            from django.core.files.base import ContentFile
            json_content = json.dumps(data, indent=4)
            storage.save(file_name, ContentFile(json_content.encode('utf-8')))
            self.stdout.write(self.style.SUCCESS(f"  -> JSON guardado en GCS: {file_name}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    Error al guardar el JSON en GCS: {e}")) 