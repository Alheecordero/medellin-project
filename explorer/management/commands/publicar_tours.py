"""Publica en Places las agencias de tours de Qué hacer ("Tours y excursiones").

Maps mezcla en "Agencia de viajes" a quien vende vuelos y paquetes con quien hace tours en
la ciudad, y su tipo principal no sirve (sale "sitio turístico" o "punto de interés"). Por
eso la lista es de nombres revisados a mano el 31 oct 2026: solo operadores de tours para
quien visita Medellín. Aun así cada una pasa la misma vara de calidad del índice.

Si una ya está publicada (Graffitour) solo le cambia el tipo. Con --retirar despublica las de
FUERA (tiene_fotos=False: dan 404 y salen de todo); no borra la ficha. No llama a la API de Google ni
descarga fotos. No borra nada.

  python manage.py publicar_tours --dry-run
  python manage.py publicar_tours
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from explorer.management.commands.publicar_pendientes_enriquecidos import ZONA_MEDELLIN
from explorer.management.commands.publicar_pendientes_enriquecidos import Command as Publicador
from explorer.management.commands.publicar_que_hacer import FOTOS_MIN, _norm
from explorer.models import GooglePlaceDetails, PendingPlace, Places, RegionOSM

TIPO = "tour_agency"
RATING_MIN = 4.5
RESENAS_MIN = 50  # la vara de Qué hacer: con menos no sale en la página ni en el sitemap
# Revisadas en su web: venden viajes fuera de Medellín (Europa, Cancún, San Andrés, Capurganá,
# paquetes nacionales), no tours en la ciudad. Se publicaron el 31 oct y se retiraron ese día.
FUERA = (
    "corazon-viajero", "suroeste-travel", "discovering-colombia-medellin",
    "club-de-los-perdidos", "mari-andariega", "rutas-y-aventuras",
)
AGENCIAS = {
    _norm(n)
    for n in (
        "Tours Guatape SAS",
        "Turismo en Medellin",
        "Aquatour Guatapé SAS",
        "Graffitour SAG TOUR MEDELLIN",
        "Fly Colombia City Tour",
        "Operadora Turística Detour",
        "Comuna 13 - Graffiti tour Viajeros MAC",
        "Rutas ON - El placer de rodar.",
        "Transporte & Turismo Medellin",
        "Super Tours Medellin",
        "Servicio de lanchas y helicóptero guatape",
        "¡Graffitour comuna 13 Medellín!",
        "Movilcsent tours",
        "Tours by Locals Medellín",
        "Maoke Travel",
        "KOORA TRIP. (antes eramos Outdoors Guatape) W",
        "JJ NÁUTICA SAS - JJ EXPERIENCES",
        "Guatapé Water Sports",
        "Carriquí Walking Tours",
        "YoAndoConNando | Local Concierge | Personal D",
    )
}


def _empieza_por_agencia(nombre: str) -> bool:
    # Maps corta algunos nombres largos: basta con que empiece igual.
    n = _norm(nombre)
    return any(n == a or n.startswith(a) for a in AGENCIAS)


def elegir() -> tuple[list[GooglePlaceDetails], list[str]]:
    """Fichas de Maps de la lista que pasan la vara; también los descartes con su motivo."""
    elegidas, descartes, vistos = [], [], set()
    qs = (
        GooglePlaceDetails.objects.filter(fetch_status="ok", ubicacion__within=ZONA_MEDELLIN)
        .exclude(business_status="CLOSED_PERMANENTLY")
        .exclude(category__istartswith="Cerrado permanentemente")
        .filter(category__icontains="agencia")
        .order_by(F("user_rating_count").desc(nulls_last=True), "place_id")
    )
    for det in qs.iterator():
        if not _empieza_por_agencia(det.display_name):
            continue
        nombre = _norm(det.display_name)
        if nombre in vistos:
            descartes.append(f"repetida: {det.display_name}")
            continue
        if (det.rating or 0) < RATING_MIN or (det.user_rating_count or 0) < RESENAS_MIN:
            descartes.append(f"calificación: {det.display_name} {det.rating} ({det.user_rating_count})")
            continue
        if len([u for u in det.photo_urls or [] if u]) < FOTOS_MIN:
            descartes.append(f"fotos: {det.display_name}")
            continue
        if not RegionOSM.objects.filter(geom_4326__contains=det.ubicacion).exists():
            descartes.append(f"fuera de zona: {det.display_name}")
            continue
        vistos.add(nombre)
        elegidas.append(det)
    return elegidas, descartes


class Command(BaseCommand):
    help = "Publica las agencias de tours elegidas a mano como 'Tours y excursiones'."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--retirar", action="store_true", help="despublica las de FUERA")

    def handle(self, *args, **options):
        if options["retirar"]:
            qs = Places._base_manager.filter(slug__in=FUERA, tiene_fotos=True)
            self.stdout.write(f"a retirar: {', '.join(qs.values_list('slug', flat=True)) or 'ninguna'}")
            if not options["dry_run"]:
                self.stdout.write(f"retiradas {qs.update(tiene_fotos=False)}")
            return
        elegidas, descartes = elegir()
        publicadas = {
            p.place_id: p for p in Places._base_manager.filter(place_id__in=[d.place_id for d in elegidas])
        }
        self.stdout.write(f"elegidas: {len(elegidas)} ({len(publicadas)} ya publicadas) | descartadas: {len(descartes)}")
        for motivo in descartes:
            self.stdout.write(f"  descartada por {motivo}")
        if options["dry_run"]:
            for det in elegidas:
                ya = publicadas.get(det.place_id)
                estado = f"ya está: /lugar/{ya.slug}/ ({ya.tipo})" if ya else "nueva"
                self.stdout.write(f"  {det.display_name[:50]:50} {det.rating} ({det.user_rating_count}) {estado}")
            self.stdout.write(self.style.WARNING("dry-run: no se guardó nada"))
            return

        publicador = Publicador(stdout=self.stdout, stderr=self.stderr)
        nuevas = retipadas = 0
        for det in elegidas:
            with transaction.atomic():
                if det.place_id in publicadas:
                    Places._base_manager.filter(place_id=det.place_id).exclude(tipo=TIPO).update(tipo=TIPO)
                    retipadas += 1
                    continue
                lugar = publicador._publicar(det)
                if lugar is None:
                    continue
                Places._base_manager.filter(pk=lugar.pk).update(tipo=TIPO)
                publicador._asignar_comuna(lugar)
                PendingPlace.objects.filter(place_id=det.place_id).update(status="processed", procesado_en=timezone.now())
            nuevas += 1
            self.stdout.write(f"ok /lugar/{lugar.slug}/")
        self.stdout.write(self.style.SUCCESS(f"publicadas {nuevas}, con tipo cambiado {retipadas}"))
