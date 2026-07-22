"""
Añade uno o más lugares a la cola (PendingPlace) buscando por nombre en Google.
Sirve para incluir sitios que el escaneo de grilla no devolvió (ej. Moresko, Purple Club).

Google Nearby Search solo devuelve hasta 20 lugares por punto y solo los que coinciden
con includedTypes; algunos bares/clubs pueden estar clasificados como lounge_bar o
cocktail_bar. Este comando usa Text Search: buscas por nombre y se añaden a pendientes.

Uso:
  python manage.py agregar_lugar_por_nombre "Moresko"
  python manage.py agregar_lugar_por_nombre "Purple Club Medellin"
  python manage.py agregar_lugar_por_nombre "Moresko" --dry-run
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from explorer.models import Places, PendingPlace
from explorer.utils.google_places import extract_place_id, text_search_ids_only
import requests


# Medellín centro (para sesgar la búsqueda)
MEDELLIN_LAT, MEDELLIN_LNG = 6.2476, -75.5658
# Fase 2: solo si hay candidatos nuevos (bajo volumen manual)
FIELD_MASK = "places.id,places.displayName,places.location,places.types"


class Command(BaseCommand):
    help = 'Busca un lugar por nombre en Google y lo añade a PendingPlace si no existe.'

    def add_arguments(self, parser):
        parser.add_argument('query', type=str, help='Nombre a buscar (ej. "Moresko", "Purple Club Medellin")')
        parser.add_argument('--dry-run', action='store_true', help='Solo mostrar qué se encontraría, no guardar')

    def handle(self, *args, **options):
        api_key = getattr(settings, 'GOOGLE_API_KEY', None)
        if not api_key:
            raise CommandError("GOOGLE_API_KEY no configurada.")

        query = options['query'].strip()
        if not query:
            raise CommandError("Indica un nombre a buscar (ej. agregar_lugar_por_nombre \"Moresko\").")

        dry_run = options['dry_run']

        # Fase 1: Text Search IDs Only (gratis) — evita la llamada con campos Pro si no hay nada
        try:
            id_candidates = text_search_ids_only(
                api_key,
                f"{query} Medellín",
                MEDELLIN_LAT,
                MEDELLIN_LNG,
                radius=25000.0,
            )
        except requests.RequestException as e:
            raise CommandError(f"Error al llamar a Google Text Search (IDs Only): {e}")

        if not id_candidates:
            self.stdout.write(self.style.WARNING(
                f'Google no devolvió resultados para "{query}". Prueba otro nombre o más específico (ej. "Purple Club Medellin").'
            ))
            return

        existing_place_ids = set(Places.objects.values_list('place_id', flat=True))
        existing_pending = set(PendingPlace.objects.values_list('place_id', flat=True))
        known = existing_place_ids | existing_pending
        new_ids = [pid for pid in id_candidates if pid not in known]

        if not new_ids and all(pid in known for pid in id_candidates):
            self.stdout.write(self.style.WARNING(
                f'Google encontró {len(id_candidates)} resultado(s) para "{query}", pero todos ya están en Places o en la cola.'
            ))
            for i, pid in enumerate(id_candidates, 1):
                self.stdout.write(f"   {i}. place_id={pid} — ya conocido")
            return

        # Fase 2: detalles mínimos para PendingPlace (Text Search con campos Pro; bajo volumen manual)
        url = 'https://places.googleapis.com/v1/places:searchText'
        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': api_key,
            'X-Goog-FieldMask': FIELD_MASK,
        }
        body = {
            "textQuery": f"{query} Medellín",
            "languageCode": "es",
            "regionCode": "CO",
            "locationBias": {
                "circle": {
                    "center": {"latitude": MEDELLIN_LAT, "longitude": MEDELLIN_LNG},
                    "radius": 25000.0
                }
            },
            "pageSize": 10,
        }

        try:
            resp = requests.post(url, json=body, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise CommandError(f"Error al llamar a Google Text Search: {e}")

        data = resp.json()
        places = data.get("places", [])
        if not places:
            self.stdout.write(self.style.WARNING(f'Sin detalles para "{query}" (IDs encontrados: {len(id_candidates)}).'))
            return

        added = 0

        self.stdout.write(f"\n📋 Resultados para \"{query}\":")
        for i, p in enumerate(places, 1):
            place_id = extract_place_id(p.get("id", ""))
            nombre = p.get("displayName", {}).get("text", "—")
            loc = p.get("location", {})
            lat, lng = loc.get("latitude"), loc.get("longitude")
            tipos = p.get("types", [])

            if place_id in known:
                self.stdout.write(f"   {i}. {nombre} — ya en Places o en cola (omitido)")
                continue

            if not dry_run:
                PendingPlace.objects.get_or_create(
                    place_id=place_id,
                    defaults={
                        'nombre': nombre,
                        'tipos': tipos,
                        'lat': lat,
                        'lng': lng,
                        'status': 'pending',
                    }
                )
                known.add(place_id)
                added += 1

            self.stdout.write(self.style.SUCCESS(f"   {i}. {nombre} ({tipos[0] if tipos else '?'}) — {'añadido a pendientes' if not dry_run else 'se añadiría'}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  DRY RUN — nada guardado. Quita --dry-run para añadir."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n✅ {added} lugar(es) añadido(s) a la cola. Procesa con: python manage.py procesar_pendientes"))
