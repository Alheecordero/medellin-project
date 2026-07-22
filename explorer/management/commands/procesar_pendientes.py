"""
PASO 2: Procesa los place_ids descubiertos en scan_nuevos_lugares.
Pide Place Details completos + fotos y guarda en Places + Foto.

Requisitos: GOOGLE_API_KEY en settings; GCS configurado (credenciales y bucket)
para guardar fotos y JSON. Valida credenciales al inicio para evitar fallos a mitad.
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from explorer.models import Places, Foto, PendingPlace
import requests
import json
import time
import random


# FieldMask completo para Place Details — TODOS los campos que usa Places model
FIELDMASK_DETAILS = ",".join([
    # Básicos
    "id",
    "displayName",
    "formattedAddress",
    "shortFormattedAddress",
    "location",
    "types",
    # Rating y popularidad
    "rating",
    "userRatingCount",
    "priceLevel",
    # Horarios
    "currentOpeningHours",
    "regularOpeningHours",
    # Contacto
    "websiteUri",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "googleMapsUri",
    # Contenido editorial
    "editorialSummary",
    "reviews",
    "photos",
    # Ubicación extra
    "plusCode",
    # Pagos
    "paymentOptions",
    # Accesibilidad
    "accessibilityOptions",
    # Servicios
    "takeout",
    "dineIn",
    "delivery",
    # Comidas que sirve
    "servesBreakfast",
    "servesLunch",
    "servesDinner",
    "servesBeer",
    "servesWine",
    "servesBrunch",
    "servesCocktails",
    "servesDessert",
    "servesCoffee",
    # Ambiente
    "goodForGroups",
    "goodForChildren",
    "outdoorSeating",
    "menuForChildren",
    "liveMusic",
    "allowsDogs",
    # Reservas
    "reservable",
])


class Command(BaseCommand):
    help = 'PASO 2: Procesa PendingPlaces — pide detalles a Google y guarda en Places.'

    IMAGE_FOLDER = 'images/'
    MAX_PHOTOS = 5

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0,
                            help='Máximo de lugares a procesar (0 = todos)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Solo muestra qué haría, no procesa')
        parser.add_argument('--status', action='store_true',
                            help='Muestra estadísticas de la cola y sale')
        parser.add_argument('--retry-failed', action='store_true',
                            help='Re-intenta los que fallaron')

    def handle(self, *args, **options):
        # ─── Status (no requiere credenciales) ───
        if options['status']:
            self._show_status()
            return

        dry_run = options['dry_run']

        # ─── Validar credenciales y almacenamiento antes de procesar ───
        api_key = self._validar_configuracion(dry_run)
        if not api_key:
            return

        # Re-intentar fallidos
        if options['retry_failed']:
            updated = PendingPlace.objects.filter(status='failed').update(status='pending')
            self.stdout.write(self.style.WARNING(f"🔄 {updated} fallidos marcados como pendientes"))

        # Obtener pendientes
        pendientes = PendingPlace.objects.filter(status='pending').order_by('descubierto_en')
        if options['limit'] > 0:
            pendientes = pendientes[:options['limit']]

        total = pendientes.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("✅ No hay lugares pendientes por procesar."))
            self._show_status()
            return

        self.stdout.write(f"📋 Procesando {total} lugares pendientes...")
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  DRY RUN — no se guardará nada"))

        # Pre-check: place_ids que ya existen en Places (por si se agregaron manualmente)
        pending_pids = list(pendientes.values_list('place_id', flat=True))
        already_in_db = set(
            Places.objects.filter(place_id__in=pending_pids).values_list('place_id', flat=True)
        )
        if already_in_db:
            self.stdout.write(f"   ⚠️ {len(already_in_db)} ya existen en Places, se marcarán como procesados")
            if not dry_run:
                PendingPlace.objects.filter(place_id__in=already_in_db).update(
                    status='processed', procesado_en=timezone.now()
                )

        stats = {'procesados': 0, 'guardados': 0, 'fallidos': 0, 'ya_existian': 0, 'api_calls': 0}
        stats['ya_existian'] = len(already_in_db)

        # Usar el storage configurado en el proyecto (GCS o local)
        storage = default_storage

        for i, pending in enumerate(pendientes, 1):
            # Saltar si ya existe
            if pending.place_id in already_in_db:
                continue

            self.stdout.write(f"\n[{i}/{total}] {pending.nombre or pending.place_id}")

            if dry_run:
                self.stdout.write(f"   → Tipos: {pending.tipos}")
                self.stdout.write(f"   → Ubicación: ({pending.lat}, {pending.lng})")
                stats['procesados'] += 1
                continue

            # ═══════════════════════════════════════════════════════
            # Pedir detalles completos a Google
            # ═══════════════════════════════════════════════════════
            detalles = self._get_place_details(api_key, pending.place_id)
            stats['api_calls'] += 1

            if not detalles:
                pending.status = 'failed'
                pending.error_msg = 'No se obtuvo respuesta de Google Place Details'
                pending.procesado_en = timezone.now()
                pending.save()
                stats['fallidos'] += 1
                self.stdout.write(self.style.ERROR(f"   ❌ Sin respuesta de API"))
                continue

            # Guardar todo en una transacción para no dejar datos a medias
            try:
                with transaction.atomic():
                    lugar = self._guardar_lugar(detalles, pending.place_id)
                    if not lugar:
                        raise ValueError("Error al guardar en Places")

                    # Guardar fotos
                    fotos_guardadas = 0
                    for foto_data in detalles.get("photos", [])[:self.MAX_PHOTOS]:
                        if self._guardar_foto(storage, api_key, lugar, foto_data):
                            fotos_guardadas += 1

                    if fotos_guardadas > 0:
                        lugar.tiene_fotos = True
                        lugar.save(update_fields=['tiene_fotos'])

                    # Guardar JSON original (usa el storage por defecto del proyecto)
                    json_bytes = json.dumps(detalles, indent=2).encode("utf-8")
                    file_name = f"{lugar.place_id}_{lugar.slug}.json"
                    lugar.google_api_json.save(file_name, ContentFile(json_bytes), save=True)

                    # Marcar pendiente como procesado
                    pending.status = 'processed'
                    pending.procesado_en = timezone.now()
                    pending.error_msg = ''
                    pending.save(update_fields=['status', 'procesado_en', 'error_msg'])

                stats['guardados'] += 1
                self.stdout.write(self.style.SUCCESS(
                    f"   ✅ Guardado: {lugar.nombre} | {lugar.tipo} | "
                    f"⭐{lugar.rating or '-'} | 📷{fotos_guardadas}"
                ))
            except Exception as e:
                pending.status = 'failed'
                pending.error_msg = str(e)[:500]
                pending.procesado_en = timezone.now()
                pending.save(update_fields=['status', 'error_msg', 'procesado_en'])
                stats['fallidos'] += 1
                self.stdout.write(self.style.ERROR(f"   ❌ Error guardando: {e}"))

            # Pausa entre requests
            if i < total:
                pausa = random.uniform(0.5, 1.5)
                time.sleep(pausa)

        # ═══════════════════════════════════════════════════════
        # RESUMEN
        # ═══════════════════════════════════════════════════════
        self.stdout.write(f"\n{'═'*60}")
        self.stdout.write(self.style.SUCCESS("📊 RESUMEN DEL PROCESAMIENTO"))
        self.stdout.write(f"   Llamadas API:    {stats['api_calls']} (~${stats['api_calls'] * 0.017:.2f} USD)")
        self.stdout.write(f"   Guardados:       {stats['guardados']}")
        self.stdout.write(f"   Fallidos:        {stats['fallidos']}")
        self.stdout.write(f"   Ya existían:     {stats['ya_existian']}")
        if dry_run:
            self.stdout.write(self.style.WARNING("   ⚠️  DRY RUN — nada fue guardado"))

        self.stdout.write(f"\n   💡 Siguiente paso: python manage.py asignar_regiones")
        self.stdout.write(f"   💡 Luego: python manage.py calcular_weighted_rating")
        self.stdout.write(f"   💡 Luego: python manage.py generar_miniaturas_gcs")

        self._show_status()

    def _validar_configuracion(self, dry_run):
        """
        Valida GOOGLE_API_KEY y (si no es dry_run) que el storage esté operativo.
        Devuelve la API key o None si hay error y se debe salir.
        """
        # 1) API Key obligatoria
        api_key = getattr(settings, 'GOOGLE_API_KEY', None)
        if not api_key or not str(api_key).strip():
            raise CommandError(
                "GOOGLE_API_KEY no está configurada o está vacía. "
                "Configúrala en .env o en settings (variables de entorno)."
            )

        if dry_run:
            return api_key

        # 2) Storage: debe poder usarse para guardar fotos y JSON
        try:
            storage = default_storage
            # Comprobar que el backend responde (exists en path que no existe es False, no excepción)
            storage.exists("images/_procesar_pendientes_check")
        except Exception as e:
            raise CommandError(
                f"No se pudo usar el almacenamiento de archivos (GCS/local): {e}\n"
                "Para producción asegura: archivo de credenciales GCS en el proyecto "
                "o STORAGES correcto en settings."
            )

        # 3) Si el backend es GCS, el bucket debe estar definido en settings
        cls = type(storage)
        if 'gcloud' in getattr(cls, '__module__', '') or cls.__name__ == 'GoogleCloudStorage':
            bucket = getattr(settings, 'GS_BUCKET_NAME', None)
            if not bucket or not str(bucket).strip():
                raise CommandError(
                    "GS_BUCKET_NAME no está configurado. "
                    "Con GCS debe existir en settings (credenciales en vivemedellin-fdc8cbb3b441.json)."
                )

        return api_key

    def _show_status(self):
        """Muestra estadísticas de la cola."""
        total = PendingPlace.objects.count()
        pending = PendingPlace.objects.filter(status='pending').count()
        processed = PendingPlace.objects.filter(status='processed').count()
        failed = PendingPlace.objects.filter(status='failed').count()
        skipped = PendingPlace.objects.filter(status='skipped').count()

        self.stdout.write(f"\n📋 COLA PendingPlace:")
        self.stdout.write(f"   ⏳ Pendientes:  {pending}")
        self.stdout.write(f"   ✅ Procesados:  {processed}")
        self.stdout.write(f"   ❌ Fallidos:    {failed}")
        self.stdout.write(f"   🚫 Descartados: {skipped}")
        self.stdout.write(f"   📊 Total:       {total}")
        if pending > 0:
            self.stdout.write(self.style.WARNING(
                f"\n   💰 Costo estimado Fase 2 ({pending} detalles): {self._estimado_fase2(pending)}"
            ))

    def _estimado_fase2(self, n):
        """Costo aproximado USD para n llamadas Place Details (Pro + Photos)."""
        # Place Details Pro: 5,000 gratis/mes, luego $17/1000. Photos: 1,000 gratis, luego $7/1000.
        free_pro, free_photos = 5000, 1000
        billable_pro = max(0, n - free_pro)
        billable_photos = max(0, n - free_photos)
        usd_pro = billable_pro * (17 / 1000)
        usd_photos = billable_photos * (7 / 1000)
        total = usd_pro + usd_photos
        return f"~${total:.2f} USD"

    def _get_place_details(self, api_key, place_id):
        """Pide detalles completos de un lugar a Google Places API."""
        url = f'https://places.googleapis.com/v1/places/{place_id}'
        headers = {
            'X-Goog-Api-Key': api_key,
            'X-Goog-FieldMask': FIELDMASK_DETAILS,
        }
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                self.stdout.write(self.style.ERROR(
                    f"   API Error {resp.status_code}: {resp.text[:200]}"
                ))
                return None
            return resp.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   Error: {e}"))
            return None

    def _guardar_lugar(self, detalles, place_id):
        """
        Guarda un lugar en Places.
        Lógica IDÉNTICA a fetch_nearby_places_v2.procesar_punto()
        """
        # Ubicación (obligatoria)
        location = detalles.get("location", {})
        lat_p = location.get("latitude")
        lon_p = location.get("longitude")
        if not lat_p or not lon_p:
            self.stdout.write(self.style.ERROR(f"   ❌ Sin coordenadas"))
            return None

        # Nombre
        nombre = detalles.get("displayName", {}).get("text", "Sin nombre")

        # Tipo principal
        tipos = detalles.get("types", [])
        tipo = tipos[0] if tipos else "otros"

        # Horarios
        opening_hours = detalles.get("currentOpeningHours", {})
        weekday_desc = opening_hours.get("weekdayDescriptions", [])
        horario_texto = "\n".join(weekday_desc) if weekday_desc else None

        # Payment options
        payment = detalles.get("paymentOptions", {})

        # Accessibility
        access = detalles.get("accessibilityOptions", {})

        # Plus code
        plus_code = detalles.get("plusCode", {})
        areas = list(plus_code.values()) if plus_code else None

        # Price level
        precio_raw = detalles.get("priceLevel")
        precio = str(precio_raw) if precio_raw is not None else None

        # Editorial summary
        editorial = detalles.get("editorialSummary", {})
        descripcion = editorial.get("overview") if editorial else None

        try:
            lugar = Places.objects.create(
                place_id=place_id,
                nombre=nombre,
                tipo=tipo,
                direccion=detalles.get("formattedAddress"),
                ubicacion=Point(lon_p, lat_p, srid=4326),
                rating=detalles.get("rating"),
                total_reviews=detalles.get("userRatingCount"),
                abierto_ahora=opening_hours.get("openNow"),
                horario_texto=horario_texto,
                horario_json=detalles.get("currentOpeningHours"),
                sitio_web=detalles.get("websiteUri"),
                telefono=detalles.get("nationalPhoneNumber"),
                google_maps_uri=detalles.get("googleMapsUri"),
                directions_uri=detalles.get("shortFormattedAddress"),
                precio=precio,
                descripcion=descripcion,
                reviews=detalles.get("reviews"),
                types=tipos,
                areas_google_api=areas,
                # Servicios
                takeout=detalles.get("takeout"),
                dine_in=detalles.get("dineIn"),
                delivery=detalles.get("delivery"),
                # Pagos
                accepts_credit_cards=payment.get("creditCards"),
                accepts_debit_cards=payment.get("debitCards"),
                accepts_cash_only=payment.get("cashOnly"),
                accepts_nfc=payment.get("nfc"),
                # Accesibilidad
                wheelchair_accessible_entrance=access.get("wheelchairAccessibleEntrance"),
                wheelchair_accessible_parking=access.get("wheelchairAccessibleParking"),
                wheelchair_accessible_restroom=access.get("wheelchairAccessibleRestroom"),
                wheelchair_accessible_seating=access.get("wheelchairAccessibleSeating"),
                # Comidas
                serves_breakfast=detalles.get("servesBreakfast"),
                serves_lunch=detalles.get("servesLunch"),
                serves_dinner=detalles.get("servesDinner"),
                serves_beer=detalles.get("servesBeer"),
                serves_wine=detalles.get("servesWine"),
                serves_brunch=detalles.get("servesBrunch"),
                serves_cocktails=detalles.get("servesCocktails"),
                serves_dessert=detalles.get("servesDessert"),
                serves_coffee=detalles.get("servesCoffee"),
                # Ambiente
                good_for_groups=detalles.get("goodForGroups"),
                good_for_children=detalles.get("goodForChildren"),
                outdoor_seating=detalles.get("outdoorSeating"),
                menu_for_children=detalles.get("menuForChildren"),
                live_music=detalles.get("liveMusic"),
                allows_dogs=detalles.get("allowsDogs"),
            )
            return lugar
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Error DB: {e}"))
            return None

    def _guardar_foto(self, storage, api_key, lugar, foto_data):
        """
        Descarga y guarda una foto en el storage del proyecto (GCS o local)
        y crea el registro Foto con la URL que devuelve el backend.
        """
        name = foto_data.get("name")
        if not name:
            return False

        uid = name.split("/")[-1]
        path = f"{self.IMAGE_FOLDER}{lugar.place_id}/{uid}.jpg"

        try:
            if not storage.exists(path):
                url = f"https://places.googleapis.com/v1/{name}/media?maxHeightPx=1200&key={api_key}"
                r = requests.get(url, timeout=20)
                r.raise_for_status()
                storage.save(path, ContentFile(r.content))
            # URL pública: usar la que devuelve el backend (GCS o media local)
            photo_url = storage.url(path)
            Foto.objects.get_or_create(
                lugar=lugar,
                imagen=photo_url,
                defaults={'descripcion': f"Foto de {lugar.nombre}"}
            )
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Error foto: {e}"))
            return False
