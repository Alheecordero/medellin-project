"""
PASO 1: Escanea el grid de Medellín buscando lugares NUEVOS.
Solo usa Nearby Search con FieldMask mínimo (tarifa Basic ~$0.032/request).
Los place_id nuevos se guardan en PendingPlace para procesar después.

Uso:
  python manage.py scan_nuevos_lugares                     # Escanea puntos pendientes
  python manage.py scan_nuevos_lugares --reset-grid        # Re-escanea TODO el grid
  python manage.py scan_nuevos_lugares --limit 5           # Solo 5 puntos
  python manage.py scan_nuevos_lugares --radio 5000        # Radio personalizado
  python manage.py scan_nuevos_lugares --dry-run           # Solo muestra, no guarda
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from explorer.models import Places, Initialgrid, PendingPlace
import requests
import time
import random


# ════════════════════════════════════════════════════════════════════
# TIPOS QUE QUEREMOS: establecimientos donde vas a consumir comida/bebida
# o a salir (bares, discos). NO catering, NO mercados/ferias de compra.
# ════════════════════════════════════════════════════════════════════
INCLUDED_TYPES = [
    # Restaurantes (comida preparada en el local)
    "restaurant", "american_restaurant", "asian_restaurant",
    "barbecue_restaurant", "breakfast_restaurant", "brunch_restaurant",
    "chinese_restaurant", "fast_food_restaurant", "fine_dining_restaurant",
    "french_restaurant", "hamburger_restaurant", "indian_restaurant",
    "italian_restaurant", "japanese_restaurant", "korean_restaurant",
    "mediterranean_restaurant", "mexican_restaurant", "pizza_restaurant",
    "seafood_restaurant", "steak_house", "sushi_restaurant",
    "thai_restaurant", "vegan_restaurant", "vegetarian_restaurant",
    "sandwich_shop", "dessert_restaurant",
    # Bares y vida nocturna (donde vas a tomar/salir)
    "bar", "bar_and_grill", "wine_bar", "pub", "night_club", "karaoke",
    "lounge_bar", "cocktail_bar", "live_music_venue",
    # Cafés (donde vas a tomar algo)
    "cafe", "coffee_shop",
    # Cultura / planes
    "art_gallery", "museum", "tourist_attraction", "historical_landmark",
    # Comida/bebida en sitio: patios de comidas, panadería/heladería/dulcería
    "event_venue", "food_court", "bakery", "ice_cream_shop",
    "dessert_shop", "confectionery", "pastry_shop", "cake_shop", "candy_store",
]  # Sin "market": mercados/ferias no son establecimiento de comida preparada

# Tipos que NUNCA queremos en vivemedellin.co (máx 50 para la API en excludedTypes)
EXCLUDED_TYPES = [
    "hospital", "doctor", "dentist", "pharmacy",
    "gas_station", "car_wash", "car_repair", "parking",
    "bank", "atm", "post_office", "police",
    "school", "university", "library",
    "church", "mosque", "synagogue",
    "gym", "laundry", "hair_salon", "beauty_salon",
    "barber_shop", "spa", "wellness_center",
    "real_estate_agency", "insurance_agency",
    "lodging", "hotel", "motel",
    "shopping_mall", "supermarket", "grocery_store",
    "convenience_store", "department_store", "gift_shop",
    "clothing_store", "shoe_store", "electronics_store",
    "furniture_store", "hardware_store", "home_goods_store",
    "cultural_center", "community_center",
    "farm", "agricultural_organization",
    "movie_theater", "bowling_alley", "casino", "zoo", "aquarium", "amusement_park",
]

# Tipos adicionales a descartar solo al marcar pendientes (no se envían a la API, límite 50)
# Se usan en descartar_pendientes_inutiles para filtrar más fino
EXTRA_EXCLUDED_TYPES = [
    # Automotive
    "car_dealer", "car_rental", "electric_vehicle_charging_station",
    "parking_garage", "parking_lot", "rest_stop", "tire_shop", "truck_dealer",
    # Business
    "business_center", "corporate_office", "coworking_space",
    "manufacturer", "ranch", "supplier", "television_studio",
    # Culture (no bares/restos)
    "art_studio", "auditorium", "castle", "cultural_landmark", "fountain",
    "historical_place", "history_museum", "monument", "performing_arts_theater",
    "sculpture", "art_museum",
    # Education
    "academic_department", "educational_institution", "preschool",
    "primary_school", "research_institute", "secondary_school",
    # Entertainment / Recreation (no vida nocturna que ya tenemos)
    "adventure_sports_center", "amphitheatre", "amusement_center",
    "barbecue_area", "botanical_garden", "childrens_camp", "city_park",
    "concert_hall", "convention_center", "cycling_park", "dance_hall",
    "dog_park", "ferris_wheel", "garden", "hiking_area", "indoor_playground",
    "internet_cafe", "marina", "movie_rental", "national_park",
    "observation_deck", "opera_house", "park", "philharmonic_hall",
    "picnic_ground", "planetarium", "plaza", "visitor_center", "water_park",
    "wedding_venue", "wildlife_park", "wildlife_refuge", "vineyard",
    # Facilities
    "public_bath", "public_bathroom", "stable",
    # Government
    "city_hall", "courthouse", "embassy", "fire_station",
    "government_office", "local_government_office",
    # Health
    "chiropractor", "dental_clinic", "medical_center", "medical_clinic",
    "medical_lab", "physiotherapist", "sauna", "skin_care_clinic",
    "tanning_studio", "yoga_studio", "general_hospital", "massage", "massage_spa",
    # Housing
    "apartment_building", "apartment_complex", "condominium_complex", "housing_complex",
    # Lodging (más variantes)
    "bed_and_breakfast", "campground", "cottage", "guest_house", "hostel",
    "inn", "resort_hotel", "rv_park", "mobile_home_park",
    # Natural features (no son “lugares” de ocio)
    "beach", "lake", "nature_preserve", "river", "scenic_spot", "woods",
    # Worship
    "buddhist_temple", "hindu_temple", "place_of_worship",
    # Services (catering = servicio a eventos, no local donde vas a comer)
    "cemetery", "child_care_agency", "consultant", "courier_service",
    "electrician", "employment_agency", "florist", "catering_service",
    "funeral_home", "locksmith", "moving_company", "nail_salon",
    "painter", "pet_boarding_service", "pet_care", "plumber",
    "roofing_contractor", "storage", "tailor", "travel_agency",
    "veterinary_care", "tour_agency", "tourist_information_center",
    "lawyer", "accounting",
    # Shopping (food_store se queda fuera: heladerías/panaderías lo tienen)
    "asian_grocery_store", "auto_parts_store", "bicycle_store", "book_store",
    "butcher_shop", "cell_phone_store", "cosmetics_store", "discount_store",
    "discount_supermarket", "liquor_store", "pet_store", "sporting_goods_store",
    "thrift_store", "toy_store", "warehouse_store", "wholesaler",
    "hypermarket", "health_food_store", "home_improvement_store", "garden_center",
    "general_store", "jewelry_store",
    # Mercados/ferias: compra, no establecimiento de comida preparada en sitio
    "farmers_market",
    # Sports
    "arena", "athletic_field", "fitness_center", "golf_course",
    "ice_skating_rink", "playground", "stadium", "swimming_pool",
    "sports_club", "sports_complex", "tennis_court",
    # Transportation
    "airport", "bus_station", "bus_stop", "train_station", "subway_station",
    "light_rail_station", "transit_station", "taxi_stand", "ferry_terminal",
]

# FieldMask mínimo = tarifa Basic (BARATO)
FIELDMASK_BASIC = "places.id,places.displayName,places.location,places.types"


class Command(BaseCommand):
    help = 'PASO 1: Escanea el grid y descubre place_ids nuevos (barato).'

    def add_arguments(self, parser):
        parser.add_argument('--reset-grid', action='store_true',
                            help='Re-escanea todos los puntos del grid')
        parser.add_argument('--dry-run', action='store_true',
                            help='Solo muestra estadísticas, no guarda nada')
        parser.add_argument('--limit', type=int, default=0,
                            help='Máximo de puntos a procesar (0 = todos)')
        parser.add_argument('--radio', type=float, default=3000.0,
                            help='Radio de búsqueda en metros (default: 3000)')
        parser.add_argument('--clear-pending', action='store_true',
                            help='Limpia la tabla PendingPlace antes de escanear')

    def handle(self, *args, **options):
        api_key = getattr(settings, 'GOOGLE_API_KEY', None)
        if not api_key:
            raise CommandError("GOOGLE_API_KEY no configurada.")

        dry_run = options['dry_run']
        radio = options['radio']

        if options['clear_pending']:
            deleted = PendingPlace.objects.filter(status='pending').delete()[0]
            self.stdout.write(self.style.WARNING(f"🗑️  {deleted} pendientes eliminados"))

        if options['reset_grid']:
            updated = Initialgrid.objects.filter(is_processed=True).update(is_processed=False)
            self.stdout.write(self.style.WARNING(f"🔄 Grid reseteado: {updated} puntos"))

        # Puntos a procesar
        puntos = Initialgrid.objects.filter(is_processed=False).order_by('id')
        if options['limit'] > 0:
            puntos = puntos[:options['limit']]
        total = puntos.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("✅ No hay puntos pendientes. Usa --reset-grid para re-barrer."))
            return

        # PRE-CARGAR IDs existentes (Places + PendingPlace) en un solo SET
        self.stdout.write("📦 Cargando IDs existentes...")
        existing_ids = set(Places.objects.values_list('place_id', flat=True))
        pending_ids = set(PendingPlace.objects.values_list('place_id', flat=True))
        known_ids = existing_ids | pending_ids
        self.stdout.write(f"   {len(existing_ids):,} en Places + {len(pending_ids):,} en PendingPlace = {len(known_ids):,} conocidos")

        stats = {
            'puntos': 0, 'api_calls': 0, 'google_devolvio': 0,
            'ya_existian': 0, 'tipo_excluido': 0, 'nuevos': 0,
        }

        for i, punto_grid in enumerate(puntos, 1):
            lat, lon = punto_grid.points.y, punto_grid.points.x
            self.stdout.write(f"\n📍 [{i}/{total}] Punto ID:{punto_grid.id} ({lat:.5f}, {lon:.5f})")

            # Llamada API con FieldMask mínimo
            lugares = self._nearby_search(api_key, lat, lon, radio)
            stats['api_calls'] += 1
            stats['google_devolvio'] += len(lugares)

            nuevos_este_punto = 0
            for lugar in lugares:
                # Extraer place_id
                raw_id = lugar.get("id", "")
                place_id = raw_id.split("/")[-1] if "/" in raw_id else raw_id
                if not place_id:
                    continue

                # ¿Ya lo conocemos?
                if place_id in known_ids:
                    stats['ya_existian'] += 1
                    continue

                # Verificar tipos
                tipos = lugar.get("types", [])
                if any(t in EXCLUDED_TYPES for t in tipos):
                    stats['tipo_excluido'] += 1
                    continue

                # ¡NUEVO! Guardarlo en PendingPlace
                nombre = lugar.get("displayName", {}).get("text", "")
                location = lugar.get("location", {})
                lat_p = location.get("latitude")
                lng_p = location.get("longitude")

                if not dry_run:
                    PendingPlace.objects.get_or_create(
                        place_id=place_id,
                        defaults={
                            'nombre': nombre,
                            'tipos': tipos,
                            'lat': lat_p,
                            'lng': lng_p,
                            'status': 'pending',
                        }
                    )

                known_ids.add(place_id)  # Para no repetirlo en puntos siguientes
                stats['nuevos'] += 1
                nuevos_este_punto += 1
                self.stdout.write(f"   🆕 {nombre} ({tipos[0] if tipos else '?'})")

            self.stdout.write(f"   → Google: {len(lugares)} | Nuevos: {nuevos_este_punto}")

            # Marcar punto como procesado
            if not dry_run:
                punto_grid.is_processed = True
                punto_grid.save()
            stats['puntos'] += 1

            # Pausa entre puntos
            if i < total:
                pausa = random.uniform(1.0, 2.5)
                time.sleep(pausa)

        # ═══════════════════════════════════════════════════════
        # RESUMEN
        # ═══════════════════════════════════════════════════════
        self.stdout.write(f"\n{'═'*60}")
        self.stdout.write(self.style.SUCCESS("📊 RESUMEN DEL ESCANEO"))
        self.stdout.write(f"   Puntos procesados:  {stats['puntos']}")
        self.stdout.write(f"   Llamadas API:       {stats['api_calls']} (~${stats['api_calls'] * 0.032:.2f} USD)")
        self.stdout.write(f"   Google devolvió:    {stats['google_devolvio']}")
        self.stdout.write(f"   Ya existían:        {stats['ya_existian']}")
        self.stdout.write(f"   Tipo excluido:      {stats['tipo_excluido']}")
        self.stdout.write(self.style.SUCCESS(f"   🆕 NUEVOS DESCUBIERTOS: {stats['nuevos']}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("   ⚠️  DRY RUN — nada fue guardado"))
        else:
            pending_total = PendingPlace.objects.filter(status='pending').count()
            self.stdout.write(f"\n   📋 Total en cola PendingPlace: {pending_total}")
            self.stdout.write(f"   → Siguiente paso: python manage.py procesar_pendientes")

    def _nearby_search(self, api_key, lat, lon, radio):
        """Nearby Search con FieldMask mínimo (tarifa Basic)."""
        url = 'https://places.googleapis.com/v1/places:searchNearby'
        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': api_key,
            'X-Goog-FieldMask': FIELDMASK_BASIC,
        }
        data = {
            "includedTypes": INCLUDED_TYPES,
            "excludedTypes": EXCLUDED_TYPES,
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
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            if resp.status_code != 200:
                self.stdout.write(self.style.ERROR(f"   API Error {resp.status_code}: {resp.text[:200]}"))
                return []
            return resp.json().get("places", [])
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   Error: {e}"))
            return []
