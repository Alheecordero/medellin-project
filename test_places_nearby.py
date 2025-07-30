#!/usr/bin/env python3
"""
Script simple para probar Google Places Nearby API 
y guardar el JSON de respuesta para análisis
"""

import requests
import json
import random
from datetime import datetime
import os

# Configuración
GOOGLE_API_KEY = "AIzaSyAyepBu9y5XMYUWsfkxClZ1W2kcLdvIfow"
API_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Coordenadas de Medellín (con pequeñas variaciones aleatorias)
MEDELLIN_CENTER = {
    "lat": 6.2442,
    "lng": -75.5812
}

def generate_random_coordinates():
    """Generar coordenadas aleatorias cerca de Medellín"""
    # Agregar variación aleatoria de ±0.05 grados (aprox ±5km)
    lat = MEDELLIN_CENTER["lat"] + random.uniform(-0.05, 0.05)
    lng = MEDELLIN_CENTER["lng"] + random.uniform(-0.05, 0.05)
    return lat, lng

def call_places_nearby_api(lat, lng, radius=2000):
    """Llamar a la API de Google Places Nearby"""
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "*"  # Obtener todos los campos disponibles
    }
    
    # Cuerpo de la petición
    data = {
        "includedTypes": [
            "restaurant", "cafe", "tourist_attraction", 
            "store", "shopping_mall", "bank", "hospital",
            "gas_station", "pharmacy", "school"
        ],  # Tipos específicos de lugares
        "maxResultCount": 20,    # Máximo 20 resultados
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": lat,
                    "longitude": lng
                },
                "radius": radius
            }
        }
    }
    
    try:
        print(f"🔍 Llamando API con coordenadas: {lat:.6f}, {lng:.6f}")
        print(f"📡 Radio de búsqueda: {radius}m")
        
        response = requests.post(API_URL, headers=headers, json=data)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error en API: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return None

def save_json_response(data, lat, lng):
    """Guardar la respuesta JSON en un archivo"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"places_nearby_response_{timestamp}.json"
    
    # Agregar metadatos al JSON
    response_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "coordinates": {"lat": lat, "lng": lng},
            "api_url": API_URL,
            "total_places": len(data.get("places", [])) if data else 0
        },
        "api_response": data
    }
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 JSON guardado en: {filename}")
        return filename
        
    except Exception as e:
        print(f"❌ Error guardando archivo: {e}")
        return None

def analyze_response(data):
    """Análisis básico de la respuesta"""
    
    if not data or "places" not in data:
        print("❌ No hay datos de lugares en la respuesta")
        return
    
    places = data["places"]
    print(f"\n📊 ANÁLISIS BÁSICO:")
    print(f"   Total lugares encontrados: {len(places)}")
    
    if places:
        print(f"\n🏢 PRIMEROS 5 LUGARES:")
        for i, place in enumerate(places[:5], 1):
            name = place.get("displayName", {}).get("text", "Sin nombre")
            types = place.get("types", [])
            rating = place.get("rating", "Sin rating")
            print(f"   {i}. {name}")
            print(f"      Tipos: {', '.join(types[:3])}")
            print(f"      Rating: {rating}")
            print()

def main():
    """Función principal"""
    
    print("🚀 INICIANDO PRUEBA DE GOOGLE PLACES NEARBY API")
    print("=" * 50)
    
    # Generar coordenadas aleatorias
    lat, lng = generate_random_coordinates()
    
    # Llamar a la API
    response_data = call_places_nearby_api(lat, lng)
    
    if response_data:
        # Guardar JSON
        filename = save_json_response(response_data, lat, lng)
        
        # Análisis básico
        analyze_response(response_data)
        
        print(f"\n✅ PRUEBA COMPLETADA")
        print(f"📁 Archivo guardado: {filename}")
        
    else:
        print("\n❌ PRUEBA FALLIDA - No se pudo obtener datos de la API")

if __name__ == "__main__":
    main() 