import os
import json
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib.gis.geos import Point
from explorer.models import Places, Foto

def descargar_imagen(photo_reference, api_key):
    """
    Descarga la imagen a partir de una referencia de foto de Google Places.
    """
    base_url = f"https://places.googleapis.com/v1/{photo_reference}/media"
    response = requests.get(base_url, params={"maxWidthPx": 800, "key": api_key}, allow_redirects=False)

    if response.status_code in [301, 302]:
        imagen_url = response.headers.get("Location")
        if imagen_url:
            img_response = requests.get(imagen_url)
            if img_response.status_code == 200:
                return img_response.content
    return None

def importar_lugares_desde_json(json_path):
    """
    Importa lugares desde un archivo JSON de la API de Google Places,
    guarda todas las fotos y normaliza reseñas.
    """
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    lugares = data.get("places", [])
    api_key = settings.GOOGLE_API_KEY

    for lugar in lugares:
        try:
            point = Point(
                float(lugar["location"]["longitude"]),
                float(lugar["location"]["latitude"])
            )

            # Normalizar reseñas
            reviews_crudas = lugar.get("reviews", [])
            reviews_limpias = []
            for r in reviews_crudas:
                review_texto = r.get("text")
                if isinstance(review_texto, dict):
                    review_texto = review_texto.get("text")
                reviews_limpias.append({
                    "author_name": r.get("authorName"),
                    "rating": r.get("rating"),
                    "text": review_texto,
                    "relative_time_description": r.get("relativePublishTimeDescription")
                })

            lugar_obj, created = Places.objects.get_or_create(
                place_id=lugar["id"],
                defaults={
                    "nombre": lugar["displayName"]["text"],
                    "tipo": lugar.get("types", [None])[0],
                    "direccion": lugar.get("formattedAddress"),
                    "telefono": lugar.get("nationalPhoneNumber"),
                    "sitio_web": lugar.get("websiteUri"),
                    "rating": lugar.get("rating"),
                    "total_reviews": lugar.get("userRatingCount"),
                    "precio": lugar.get("priceLevel"),
                    "ubicacion": point,
                    "horario_texto": "\n".join(lugar.get("regularOpeningHours", {}).get("weekdayDescriptions", [])),
                    "abierto_ahora": lugar.get("currentOpeningHours", {}).get("openNow"),
                    "photo_reference": None,
                    "reviews": reviews_limpias
                }
            )

            # Guardar todas las fotos
            if lugar.get("photos"):
                for index, photo in enumerate(lugar["photos"]):
                    photo_reference = photo.get("name")
                    if not photo_reference:
                        continue

                    imagen_bytes = descargar_imagen(photo_reference, api_key)
                    if imagen_bytes:
                        nombre_archivo = f"{lugar_obj.place_id}_{index}.jpg"
                        foto_obj = Foto(
                            lugar=lugar_obj,
                            descripcion=f"Foto {index + 1}"
                        )
                        foto_obj.imagen.save(nombre_archivo, ContentFile(imagen_bytes), save=True)
                        print(f"🖼️ Foto {index+1} guardada para {lugar_obj.nombre}")
                    else:
                        print(f"⚠️ No se pudo descargar la imagen {index+1} para {lugar_obj.nombre}")

            if not created:
                lugar_obj.reviews = reviews_limpias
                lugar_obj.save()
                print(f"ℹ️ Actualizado: {lugar_obj.nombre}")
            else:
                print(f"✅ Guardado nuevo lugar: {lugar_obj.nombre}")

        except Exception as e:
            print(f"❌ Error con lugar: {lugar.get('id', 'SIN_ID')} - {e}")
