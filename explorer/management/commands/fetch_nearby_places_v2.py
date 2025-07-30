from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib.gis.geos import Point
from explorer.models import Places, Foto, ZonaCubierta, Initialgrid
from storages.backends.gcloud import GoogleCloudStorage
import requests
import json
import time
import random

class Command(BaseCommand):
    help = 'Procesa puntos de Initialgrid para buscar lugares cercanos, guardarlos y marcar zonas como cubiertas.'

    PLACES_JSON_FOLDER = 'places_json_per_id/'
    IMAGE_FOLDER = 'images/'
    MAX_PHOTOS = 5
    RADIO_BUSQUEDA = 5000.0  # Radio más pequeño para ser más preciso por punto

    def handle(self, *args, **options):
        try:
            api_key = settings.GOOGLE_API_KEY
            if not api_key:
                raise RuntimeError("GOOGLE_API_KEY está vacía en la configuración.")
        except AttributeError:
            raise RuntimeError("GOOGLE_API_KEY no encontrada en la configuración.")
            
        # Obtener todos los puntos de la grilla que no han sido procesados
        puntos_a_procesar = Initialgrid.objects.filter(is_processed=False)
        total_puntos = puntos_a_procesar.count()
        self.stdout.write(f"Encontrados {total_puntos} puntos sin procesar en Initialgrid.")

        if total_puntos == 0:
            self.stdout.write(self.style.SUCCESS("¡No hay más puntos que procesar!"))
            return

        for i, punto_grid in enumerate(puntos_a_procesar, 1):
            punto = punto_grid.points
            lat, lon = punto.y, punto.x

            self.stdout.write(f"\n--- Procesando punto {i}/{total_puntos} (ID: {punto_grid.id}) ---")
            self.stdout.write(f"Coordenadas: {lat}, {lon}")

            if ZonaCubierta.objects.filter(poligono__covers=punto).exists():
                self.stdout.write(self.style.WARNING("Este punto ya está dentro de una ZonaCubierta. Marcando como procesado."))
                punto_grid.is_processed = True
                punto_grid.save()
                continue
            
            # La lógica de búsqueda y guardado de lugares
            self.procesar_punto(api_key, punto)
            
            # Marcar el punto como procesado
            punto_grid.is_processed = True
            punto_grid.save()

            self.stdout.write(self.style.SUCCESS(f"Punto {punto_grid.id} marcado como procesado."))
            
            # Pausa para no saturar la API
            if i < total_puntos:
                pausa = random.uniform(1, 3)
                self.stdout.write(f"Pausando por {pausa:.1f} segundos...")
                time.sleep(pausa)

    def procesar_punto(self, api_key, punto):
        """Lógica para procesar un único punto geográfico."""
        lat, lon = punto.y, punto.x
        
        self.stdout.write(f"🔍 Buscando lugares en ({lat}, {lon})...")
        lugares = self.nearby_search(api_key, lat, lon, self.RADIO_BUSQUEDA)
        if not lugares:
            self.stdout.write(self.style.WARNING("❌ No se encontraron lugares para este punto."))
            return

        self.stdout.write(f"📍 Lugares encontrados por Google API: {len(lugares)}")
        
        distancias = []
        storage = GoogleCloudStorage()
        
        tipos_permitidos = ['restaurant', 'bar', 'cafe', 'night_club', 'meal_takeaway', 'food']
        
        punto_3857 = punto.transform(3857, clone=True)

        for detalles in lugares:
            place_id = detalles.get("id", "").split("/")[-1]
            if not place_id:
                continue

            location = detalles.get("location", {})
            lat_p, lon_p = location.get("latitude"), location.get("longitude")
            if not lat_p or not lon_p:
                continue

            punto_place = Point(lon_p, lat_p, srid=4326)
            punto_place_3857 = punto_place.transform(3857, clone=True)
            dist_m = punto_place_3857.distance(punto_3857)
            distancias.append(dist_m)

            if Places.objects.filter(place_id=place_id).exists():
                continue
            
            tipos_lugar = detalles.get("types", [])
            if not any(tipo in tipos_permitidos for tipo in tipos_lugar):
                continue

            nombre_lugar = detalles.get("displayName", {}).get("text", "Sin nombre")
            tipo_lugar = detalles.get("types", ["Otros"])[0]
            
            self.stdout.write(f"   ✅ Guardando: {nombre_lugar} ({tipo_lugar}) - {dist_m:.0f}m")
            
            lugar = Places.objects.create(
                place_id=place_id,
                nombre=nombre_lugar,
                tipo=tipo_lugar,
                direccion=detalles.get("formattedAddress"),
                ubicacion=punto_place,
                rating=detalles.get("rating"),
                total_reviews=detalles.get("userRatingCount"),
                abierto_ahora=detalles.get("currentOpeningHours", {}).get("openNow"),
                horario_texto="\n".join(detalles.get("currentOpeningHours", {}).get("weekdayDescriptions", [])),
                horario_json=detalles.get("currentOpeningHours"),
                sitio_web=detalles.get("websiteUri"),
                telefono=detalles.get("nationalPhoneNumber"),
                google_maps_uri=detalles.get("googleMapsUri"),
                directions_uri=detalles.get("shortFormattedAddress"),
                precio=str(detalles.get("priceLevel")),
                descripcion=detalles.get("editorialSummary", {}).get("overview"),
                reviews=detalles.get("reviews"),
                types=detalles.get("types"),
                areas_google_api=list(detalles.get("plusCode", {}).values()),
                takeout=detalles.get("takeout"),
                dine_in=detalles.get("dineIn"),
                delivery=detalles.get("delivery"),
                accepts_credit_cards=detalles.get("paymentOptions", {}).get("creditCards"),
                accepts_debit_cards=detalles.get("paymentOptions", {}).get("debitCards"),
                accepts_cash_only=detalles.get("paymentOptions", {}).get("cashOnly"),
                accepts_nfc=detalles.get("paymentOptions", {}).get("nfc"),
                wheelchair_accessible_entrance=detalles.get("accessibilityOptions", {}).get("wheelchairAccessibleEntrance"),
                wheelchair_accessible_parking=detalles.get("accessibilityOptions", {}).get("wheelchairAccessibleParking"),
                wheelchair_accessible_restroom=detalles.get("accessibilityOptions", {}).get("wheelchairAccessibleRestroom"),
                wheelchair_accessible_seating=detalles.get("accessibilityOptions", {}).get("wheelchairAccessibleSeating"),
                serves_breakfast=detalles.get("servesBreakfast"),
                serves_lunch=detalles.get("servesLunch"),
                serves_dinner=detalles.get("servesDinner"),
                serves_beer=detalles.get("servesBeer"),
                serves_wine=detalles.get("servesWine"),
                serves_brunch=detalles.get("servesBrunch"),
                serves_cocktails=detalles.get("servesCocktails"),
                serves_dessert=detalles.get("servesDessert"),
                serves_coffee=detalles.get("servesCoffee"),
                good_for_groups=detalles.get("goodForGroups"),
                good_for_children=detalles.get("goodForChildren"),
                outdoor_seating=detalles.get("outdoorSeating"),
                menu_for_children=detalles.get("menuForChildren"),
                live_music=detalles.get("liveMusic"),
                allows_dogs=detalles.get("allowsDogs"),
            )

            # Guardar el JSON en el FileField para que Django lo suba a GCS
            try:
                json_bytes = json.dumps(detalles, indent=2).encode("utf-8")
                file_name = f"{lugar.place_id}_{lugar.slug}.json"
                lugar.google_api_json.save(file_name, ContentFile(json_bytes), save=True)
                self.stdout.write(f"   📄 JSON guardado y enlazado: {lugar.google_api_json.name}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Error guardando JSON para {lugar.nombre}: {e}"))

            for foto in detalles.get("photos", [])[:self.MAX_PHOTOS]:
                self.guardar_foto(storage, api_key, lugar, foto)

        if distancias:
            radio_max = max(distancias)
            zona_3857 = punto_3857.buffer(radio_max * 1.1)
            zona = zona_3857.transform(4326, clone=True)
            
            ZonaCubierta.objects.create(
                nombre=f"zona_{lat:.5f}_{lon:.5f}", 
                poligono=zona
            )
            self.stdout.write(self.style.SUCCESS(f"🎯 Zona cubierta creada para el punto."))

    def nearby_search(self, api_key, lat, lon, radio):
        """
        Realiza búsqueda de lugares cercanos usando Google Places API (New).
        Si ocurre un error, detiene la ejecución del script.
        """
        url = 'https://places.googleapis.com/v1/places:searchNearby'
        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': api_key,
            'X-Goog-FieldMask': '*',
        }
        
        data = {
            "includedTypes": ["restaurant", "bar", "cafe", "night_club"],
            "excludedTypes": ["hotel", "lodging", "shopping_mall", "supermarket", "store", "gas_station"],
            "maxResultCount": 20,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": float(radio)
                }
            },
            "rankPreference": "DISTANCE",
            "languageCode": "es",
            "regionCode": "CO"
        }
        
        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            
            if response.status_code != 200:
                error_msg = f"La API falló con estado {response.status_code}: {response.text}"
                raise CommandError(f"Deteniendo el script. {error_msg}")
            
            response_data = response.json()
            places = response_data.get("places", [])
            
            self.stdout.write(f"✅ Respuesta de API exitosa: {len(places)} lugares recibidos")
            self.stdout.write(f"🌍 Configuración: Español (es), Colombia (CO), Ranking por DISTANCIA")
            
            return places
            
        except requests.exceptions.Timeout:
            raise CommandError("Deteniendo el script: Timeout. La API de Google Places tardó más de 30 segundos.")
        except requests.exceptions.ConnectionError:
            raise CommandError("Deteniendo el script: Error de conexión. No se pudo conectar con Google Places API.")
        except requests.exceptions.RequestException as e:
            raise CommandError(f"Deteniendo el script: Error de request. {e}")
        except ValueError as e:
            raise CommandError(f"Deteniendo el script: Error al parsear la respuesta JSON. {e}")
        except Exception as e:
            raise CommandError(f"Deteniendo el script: Error inesperado en nearby_search. {e}")

    def guardar_foto(self, storage, api_key, lugar, foto):
        name = foto.get("name")
        if not name:
            return
        uid = name.split("/")[-1]
        path = f"{self.IMAGE_FOLDER}{lugar.place_id}/{uid}.jpg"
        if not storage.exists(path):
            url = f"https://places.googleapis.com/v1/{name}/media?maxHeightPx=1200&key={api_key}"
            try:
                r = requests.get(url, timeout=20)
                r.raise_for_status()
                storage.save(path, ContentFile(r.content))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error descargando foto: {e}"))
                return
        Foto.objects.create(lugar=lugar, imagen=storage.url(path), descripcion=f"Foto de {lugar.nombre}") 