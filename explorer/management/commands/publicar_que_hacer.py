"""Publica en Places los lugares de "Qué hacer" que ya tienen ficha de Maps y fotos en R2.

Atracciones, museos, parques y miradores del valle (y Guatapé) con buena calificación.
Cada tipo de Google pide su propio mínimo de reseñas: un parque de barrio o una iglesia
con pocas reseñas no es un plan para un visitante. Una lista negra de nombres saca lo que
Maps clasifica mal (gimnasios, centros comerciales, oficinas…).

No llama a la API de Google ni descarga fotos. No borra nada.

  python manage.py publicar_que_hacer --dry-run
  python manage.py publicar_que_hacer
"""

from __future__ import annotations

import re
import unicodedata

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from explorer.management.commands.publicar_pendientes_enriquecidos import ZONA_MEDELLIN
from explorer.management.commands.publicar_pendientes_enriquecidos import Command as Publicador
from explorer.models import GooglePlaceDetails, PendingPlace, Places, RegionOSM

# (tipo en Places, tipos de Google que lo dan, mínimo de reseñas). El primero que casa gana.
REGLAS = (
    ("museum", {"museum"}, 100),
    ("botanical_garden", {"botanical_garden"}, 100),
    ("observation_deck", {"observation_deck"}, 100),
    ("amusement_park", {"amusement_park"}, 200),
    ("stadium", {"stadium"}, 2000),
    ("hiking_area", {"hiking_area"}, 50),
    ("art_gallery", {"art_gallery"}, 100),
    ("performing_arts_theater", {"performing_arts_theater"}, 300),
    ("cultural_center", {"cultural_center"}, 300),
    ("church", {"church"}, 1500),
    ("historical_landmark", {"historical_place", "historical_landmark", "monument"}, 200),
    ("tourist_attraction", {"tourist_attraction"}, 200),
    ("park", {"park"}, 1000),
)
RATING_MIN = 4.3
FOTOS_MIN = 3
# Lo que Maps clasifica como parque, museo o atracción sin serlo.
NO_ES_PLAN = re.compile(
    r"centro comercial|smart ?fit|bodytech|gimnas|\bgym\b|estaci[oó]n de polic|brigada|divisi[oó]n del ej"
    r"|\bhotel\b|hostal|hospedaje|chalet|cl[ií]nica|\bspa\b|vida nocturna|parqueadero|notar[ií]a|colegio"
    r"|oficina|funeraria|cancha|\binder\b|telemedell|casino|colombo americano|unidad deportiva"
    r"|centro de deportes|polideportivo|\bcaf[eé]\b",
    re.I,
)
# Nombres que no dicen qué es el lugar o que no son un plan (revisados a mano el 31 oct 2026).
NOMBRES_FUERA = {"jardin", "porvenir", "guatape", "hidroelectrica", "silleta 3", "municipio guarne", "lideres inc"}


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in texto if not unicodedata.combining(c))).strip()


# Maps llama "atracción turística" a museos, iglesias y miradores: el nombre lo aclara.
TIPO_POR_NOMBRE = (
    (re.compile(r"^(casa )?museo\b|^muua\b|planetario", re.I), "museum"),
    (re.compile(r"^(parroquia|iglesia|catedral|bas[ií]lica)\b", re.I), "church"),
    (re.compile(r"^mirador\b", re.I), "observation_deck"),
    (re.compile(r"^teatro\b", re.I), "performing_arts_theater"),
)


def tipo_y_minimo(det: GooglePlaceDetails) -> tuple[str, int] | None:
    """Tipo de Places y mínimo de reseñas; primero por el tipo principal, luego por los demás.

    El mínimo es el de la regla de Google; el tipo puede corregirlo el nombre.
    """
    for candidatos in ({det.primary_type}, set(det.types or [])):
        for tipo, google, minimo in REGLAS:
            if candidatos & google:
                nombre = (det.display_name or "").strip()
                return next((t for rx, t in TIPO_POR_NOMBRE if rx.search(nombre)), tipo), minimo
    return None


def elegir() -> tuple[list[tuple[GooglePlaceDetails, str]], dict, dict]:
    """Fichas de Maps que pasan las reglas, con su tipo; también los conteos por tipo y descarte."""
    tipos_google = set().union(*(google for _t, google, _m in REGLAS))
    qs = (
        GooglePlaceDetails.objects.filter(
            fetch_status="ok",
            ubicacion__within=ZONA_MEDELLIN,
            photo_urls__isnull=False,
            rating__gte=RATING_MIN,
        )
        .filter(Q(primary_type__in=tipos_google) | Q(types__overlap=list(tipos_google)))
        .exclude(Q(category__istartswith="Cerrado permanentemente") | Q(business_status="CLOSED_PERMANENTLY"))
        .exclude(display_name="")
        .exclude(place_id__in=Places._base_manager.values("place_id"))
        .order_by(F("user_rating_count").desc(nulls_last=True), "place_id")
    )
    elegidos, por_tipo = [], {}
    descartes = {"nombre": 0, "reseñas": 0, "fotos": 0, "fuera de zona": 0, "repetido": 0}
    for det in qs.iterator():
        regla = tipo_y_minimo(det)
        if regla is None:
            continue
        tipo, minimo = regla
        if NO_ES_PLAN.search(det.display_name or "") or _norm(det.display_name) in NOMBRES_FUERA:
            descartes["nombre"] += 1
            continue
        if (det.user_rating_count or 0) < minimo:
            descartes["reseñas"] += 1
            continue
        if len([u for u in det.photo_urls or [] if u]) < FOTOS_MIN:
            descartes["fotos"] += 1
            continue
        # Solo lo que cae en una de nuestras zonas: la plaza de un pueblo lejano no es Medellín.
        if not RegionOSM.objects.filter(geom_4326__contains=det.ubicacion).exists():
            descartes["fuera de zona"] += 1
            continue
        # Maps tiene a veces dos fichas del mismo sitio (Parque Explora): gana la más reseñada.
        if any(_norm(o.display_name) == _norm(det.display_name)
               and o.ubicacion.distance(det.ubicacion) * 111_000 < 300 for o, _t in elegidos):
            descartes["repetido"] += 1
            continue
        elegidos.append((det, tipo))
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
    return elegidos, por_tipo, descartes


class Command(BaseCommand):
    help = "Publica atracciones, museos, parques y miradores con buena calificación."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0, help="0 = todos los que pasan")

    def handle(self, *args, **options):
        elegidos, por_tipo, descartes = elegir()
        if options["limit"]:
            elegidos = elegidos[: options["limit"]]

        self.stdout.write(f"elegidos: {len(elegidos)} | por tipo: {por_tipo} | descartados: {descartes}")
        if options["dry_run"]:
            for det, tipo in elegidos:
                self.stdout.write(f"  {tipo:24} {det.display_name[:50]:50} {det.rating} ({det.user_rating_count})")
            self.stdout.write(self.style.WARNING("dry-run: no se guardó nada"))
            return

        publicador = Publicador(stdout=self.stdout, stderr=self.stderr)
        publicados = 0
        for det, tipo in elegidos:
            with transaction.atomic():
                lugar = publicador._publicar(det)
                if lugar is None:
                    continue
                Places._base_manager.filter(pk=lugar.pk).update(tipo=tipo)
                publicador._asignar_comuna(lugar)
                PendingPlace.objects.filter(place_id=det.place_id).update(status="processed", procesado_en=timezone.now())
            publicados += 1
            self.stdout.write(f"ok {tipo:24} /lugar/{lugar.slug}/")
        self.stdout.write(self.style.SUCCESS(f"publicados {publicados}"))
