import os
import json
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib.gis.geos import Point, MultiPoint
from explorer.models import Places, Foto, ZonaCubierta

def descargar_imagen(photo_reference, api_key):
    base_url = f"https://places.googleapis.com/v1/{photo_reference}/media"
    try:
        response = requests.get(base_url, params={"maxWidthPx": 800, "key": api_key}, allow_redirects=False)
        if response.status_code in [301, 302]:
            imagen_url = response.headers.get("Location")
            if imagen_url:
                img_response = requests.get(imagen_url)
                if img_response.status_code == 200:
                    return img_response.content
    except Exception as e:
        print(f"❌ Error al descargar imagen: {e}")
    return None

def importar_lugares_desde_json(json_path):
    try:
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error al abrir el archivo JSON: {e}")
        return

    # ✅ Manejar JSON como dict {"places": [...]} o lista directamente
    if isinstance(data, dict):
        lugares = data.get("places", [])
    elif isinstance(data, list):
        lugares = data
    else:
        print("⚠️ El formato del JSON no es válido.")
        return

    if not isinstance(lugares, list) or not lugares:
        print("⚠️ No se encontraron lugares en el archivo o no es una lista válida.")
        return

    api_key = settings.GOOGLE_API_KEY
    puntos_para_zona = []
    creados = 0
    actualizados = 0
    fotos_guardadas = 0

    for lugar in lugares:
        try:
            # 🚫 Ignorar lugares sin fotos
            if not lugar.get("photos"):
                print(f"🚫 Ignorado: {lugar.get('displayName', {}).get('text', 'Sin nombre')} (sin fotos)")
                continue

            lat = lugar["location"]["latitude"]
            lng = lugar["location"]["longitude"]
            point = Point(float(lng), float(lat))

            reviews_limpias = []
            for r in lugar.get("reviews", []):
                texto = r.get("text")
                if isinstance(texto, dict):
                    texto = texto.get("text")
                reviews_limpias.append({
                    "author_name": r.get("authorName"),
                    "rating": r.get("rating"),
                    "text": texto,
                    "relative_time_description": r.get("relativePublishTimeDescription")
                })

            lugar_obj, creado = Places.objects.get_or_create(
                place_id=lugar["id"],
                defaults={
                    "nombre": lugar.get("displayName", {}).get("text", "Sin nombre"),
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

            if creado:
                puntos_para_zona.append(point)
                creados += 1
                print(f"✅ Lugar creado: {lugar_obj.nombre}")
            else:
                lugar_obj.reviews = reviews_limpias
                lugar_obj.save()
                actualizados += 1
                print(f"♻️ Lugar actualizado: {lugar_obj.nombre}")

            if Foto.objects.filter(lugar=lugar_obj).exists():
                print(f"⚠️ {lugar_obj.nombre} ya tiene fotos. No se guardarán nuevas fotos.")
                continue

            for index, foto in enumerate(lugar.get("photos", [])[:5]):
                photo_reference = foto.get("name")
                if not photo_reference:
                    continue
                imagen_bytes = descargar_imagen(photo_reference, api_key)
                if imagen_bytes:
                    nombre_archivo = f"{lugar_obj.place_id}_{index}.jpg"
                    foto_obj = Foto(lugar=lugar_obj, descripcion=f"Foto {index + 1}")
                    foto_obj.imagen.save(nombre_archivo, ContentFile(imagen_bytes), save=True)
                    fotos_guardadas += 1
                    print(f"🖼️ Foto {index+1} guardada para {lugar_obj.nombre}")
                else:
                    print(f"⚠️ No se pudo descargar la foto {index+1} de {lugar_obj.nombre}")

        except Exception as e:
            print(f"❌ Error procesando lugar: {lugar.get('id', 'SIN_ID')} - {e}")

    if puntos_para_zona:
        try:
            multipoint = MultiPoint(puntos_para_zona)
            poligono = multipoint.convex_hull
            zona = ZonaCubierta.objects.create(
                nombre=f"Zona desde archivo - {os.path.basename(json_path)}",
                poligono=poligono
            )
            print(f"🟦 Zona cubierta creada: {zona.nombre}")
        except Exception as e:
            print(f"❌ Error al crear zona convex hull: {e}")
    else:
        print("⚠️ No hay suficientes puntos nuevos para crear una zona.")

    print("\n📋 RESUMEN FINAL")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"🆕 Lugares creados:      {creados}")
    print(f"🔁 Lugares actualizados: {actualizados}")
    print(f"🖼️ Fotos guardadas:      {fotos_guardadas}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
