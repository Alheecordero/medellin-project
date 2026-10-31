"""Publica en Places los pendientes que ya tienen ficha de Maps y fotos en R2.

Usa lo que dejó import_medellin_enrich en GooglePlaceDetails: no llama a la
API de Google ni descarga fotos. Por olas, para medir qué indexa Google:

  --ola cartas   pendientes con carta de Rappi o DiDi en data/partner-menus/out
  --ola top      comida, café o noche con rating ≥ 4,2 y ≥ 50 reseñas

  python manage.py publicar_pendientes_enriquecidos --ola cartas --limit 500 --dry-run
  python manage.py publicar_pendientes_enriquecidos --ola cartas --limit 500
  python manage.py import_partner_menus

Los más reseñados entran primero. Marca el pendiente como procesado.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.contrib.gis.geos import Polygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from explorer.management.commands.completar_fichas_maps import HORARIO_INSTANTANEO, atributos
from explorer.management.commands.import_medellin_enrich import VALID_TIPOS, _weighted
from explorer.models import CentroComercial, Foto, GooglePlaceDetails, PendingPlace, Places, RegionOSM

FAMILIAS_TOP = {"food", "cafe_bakery", "nightlife"}
FOTO_ORIGINAL = re.compile(r"/images/(?P<pid>[^/]+)/(?P<name>g[0-9a-f]+)\.webp$")
MAX_FOTOS = 10
# Valle de Aburrá y oriente cercano (Guatapé): GooglePlaceDetails también guarda fichas de otros países.
ZONA_MEDELLIN = Polygon.from_bbox((-75.75, 5.95, -75.0, 6.55))
ZONA_MEDELLIN.srid = 4326


def _variantes(imagen: str) -> tuple[str | None, str | None]:
    """Mediana y miniatura que import_medellin_enrich subió junto a la original."""
    match = FOTO_ORIGINAL.search(imagen)
    if not match:
        return None, None
    base = imagen[: match.start()]
    pid, name = match["pid"], match["name"]
    return (
        f"{base}/tourism/images/medium/{pid}/{name}.jpg",
        f"{base}/tourism/images/thumb/{pid}/{name}.jpg",
    )


def _place_ids_con_carta(folder: Path) -> set[str]:
    ids = set()
    for path in folder.glob("*.json"):
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("ok"):
            ids.add(path.stem)
    return ids


class Command(BaseCommand):
    help = "Publica pendientes enriquecidos (ficha + fotos en R2) sin usar la API de Google."

    def add_arguments(self, parser):
        parser.add_argument("--ola", choices=["cartas", "top"], required=True)
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--menus-dir", type=Path, default=Path("data/partner-menus/out"))
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        pendientes = PendingPlace.objects.filter(status="pending").values_list("place_id", flat=True)
        qs = (
            GooglePlaceDetails.objects.filter(
                place_id__in=pendientes,
                fetch_status="ok",
                ubicacion__within=ZONA_MEDELLIN,
                photo_urls__isnull=False,
            )
            .exclude(error_message="excluido_salud")
            .exclude(display_name="")
            .exclude(place_id__in=Places._base_manager.values("place_id"))
        )
        if options["ola"] == "cartas":
            if not options["menus_dir"].is_dir():
                raise CommandError(f"No existe {options['menus_dir']}")
            qs = qs.filter(place_id__in=_place_ids_con_carta(options["menus_dir"]))
        else:
            qs = qs.filter(tipo_family__in=FAMILIAS_TOP, rating__gte=4.2, user_rating_count__gte=50)

        total = qs.count()
        orden = (F("user_rating_count").desc(nulls_last=True), F("rating").desc(nulls_last=True), "place_id")
        lote = list(qs.order_by(*orden)[: options["limit"]])
        self.stdout.write(f"ola {options['ola']}: {total} candidatos, lote de {len(lote)}")
        if options["dry_run"]:
            for det in lote[:15]:
                self.stdout.write(
                    f"  {det.place_id} {det.display_name} · {det.tipo} · "
                    f"{det.rating} ({det.user_rating_count}) · fotos {len(det.photo_urls or [])}"
                )
            return

        publicados = sin_comuna = 0
        for det in lote:
            with transaction.atomic():
                lugar = self._publicar(det)
                if lugar is None:
                    continue
                if not self._asignar_comuna(lugar):
                    sin_comuna += 1
                PendingPlace.objects.filter(place_id=det.place_id).update(
                    status="processed", procesado_en=timezone.now()
                )
            publicados += 1
            self.stdout.write(f"ok {det.place_id} /lugar/{lugar.slug}/")
        self.stdout.write(self.style.SUCCESS(f"publicados {publicados}, sin comuna {sin_comuna}"))

    def _publicar(self, det: GooglePlaceDetails) -> Places | None:
        fotos = [url for url in (det.photo_urls or []) if url][:MAX_FOTOS]
        if not fotos:
            return None
        lugar = Places.objects.create(
            place_id=det.place_id,
            nombre=det.display_name[:255],
            tipo=det.tipo if det.tipo in VALID_TIPOS else "otros",
            direccion=det.formatted_address or None,
            ubicacion=det.ubicacion,
            rating=det.rating,
            total_reviews=det.user_rating_count,
            weighted_rating=_weighted(det.rating, det.user_rating_count),
            horario_texto=None if HORARIO_INSTANTANEO.match(det.hours_text or "") else det.hours_text or None,
            sitio_web=det.website_uri or None,
            telefono=(det.phone or "")[:50] or None,
            google_maps_uri=det.google_maps_uri or None,
            precio=det.price_level or None,
            types=det.types or None,
            tiene_fotos=True,
            imagenes_optimizadas=True,
            **atributos(det.amenities),
        )
        for imagen in fotos:
            mediana, miniatura = _variantes(imagen)
            Foto.objects.create(
                lugar=lugar,
                imagen=imagen[:1000],
                imagen_mediana=mediana,
                imagen_miniatura=miniatura,
                descripcion="google-maps",
            )
        return lugar

    def _asignar_comuna(self, lugar: Places) -> bool:
        """Comuna de Medellín, municipio o corregimiento: cualquier zona de RegionOSM.

        También el centro comercial si cae dentro de uno; sus contadores se ponen al día
        con importar_centros_comerciales.
        """
        centro = CentroComercial.objects.filter(geom__contains=lugar.ubicacion).only("id").first()
        if centro is not None:
            lugar.centro_comercial = centro
            lugar.save(update_fields=["centro_comercial"])
        region = RegionOSM.objects.filter(geom_4326__contains=lugar.ubicacion).only("osm_id").first()
        if region is None:
            return False
        lugar.comuna_osm_id = region.osm_id
        lugar.save(update_fields=["comuna_osm_id"])
        return True
