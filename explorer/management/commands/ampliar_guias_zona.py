"""Completa las guías de zona publicadas que no llegan a GUIA_MIN_LUGARES con lugares de Qué hacer.

Envigado, Belén y Sabaneta tenían 3 o 4 restaurantes: con menos de 5 lugares la guía lleva
noindex y sale del índice. Se les suman el parque y la cultura de la zona (elegidos a mano el
31 oct 2026) delante de las mesas, con un comentario que solo dice qué es el lugar.

No borra paradas ni cambia sus comentarios. Una parada que ya esté en la guía no se repite,
así que se puede correr dos veces.

  python manage.py ampliar_guias_zona --dry-run
  python manage.py ampliar_guias_zona
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from explorer.models import CuratedGuide, CuratedGuideItem, Places

# guía → (descripción nueva, descripción en inglés, paradas que van delante: (slug, comentario, comentario_en))
AMPLIAR = {
    "envigado": (
        "Un pueblo al sur de El Poblado: el parque principal, la casa de Fernando González, un "
        "ecoparque y dónde comer después.",
        "A town south of El Poblado: the main square, Fernando González's house, an eco park and "
        "where to eat afterwards.",
        (
            ("parque-principal-de-envigado-marceliano-velez-barreneche", "El parque principal, el centro del pueblo.", "The main square, the heart of town."),
            ("casa-museo-otraparte", "La casa museo de Fernando González. El café está al lado.", "Fernando González's house museum. The café is next door."),
            ("parque-ecoturistico-el-salado", "Ecoparque para caminar junto a la quebrada.", "Eco park for a walk by the stream."),
        ),
    ),
    "belen": (
        "Belén, en el sur de la ciudad: su parque, el cerro Nutibara y dónde comer sin salir del barrio.",
        "Belén, in the south of the city: its square, Nutibara hill and where to eat without leaving "
        "the neighborhood.",
        (
            ("parque-belen", "El parque del barrio, frente a la iglesia.", "The neighborhood square, facing the church."),
            ("parque-de-las-esculturas-cerro-nutibara", "Esculturas y vista de la ciudad en lo alto del cerro Nutibara.", "Sculptures and city views on top of Nutibara hill."),
            ("teatro-de-la-universidad-de-medellin", "Teatro con conciertos y obras.", "Theater with concerts and plays."),
        ),
    ),
    "sabaneta": (
        "Sabaneta conserva el parque de pueblo. Primero la vuelta por el parque y la casa de la "
        "cultura; después, estas mesas.",
        "Sabaneta keeps its small-town square. First a walk around the square and the cultural "
        "center; then, these tables.",
        (
            ("parque-de-sabaneta", "El parque de pueblo, donde empieza la vuelta.", "The town square, where the walk starts."),
            ("casa-de-la-cultura-la-barquerena", "La casa de la cultura del municipio.", "The town's cultural center."),
            ("parque-de-los-cuatro-elementos", "Otro parque del municipio, de los más valorados.", "Another of the town's best rated parks."),
        ),
    ),
}


class Command(BaseCommand):
    help = "Completa las guías de Envigado, Belén y Sabaneta con su parque y su cultura."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        for slug, (descripcion, descripcion_en, paradas) in AMPLIAR.items():
            guia = CuratedGuide.objects.filter(slug=slug).first()
            if guia is None:
                self.stdout.write(f"no existe: {slug}")
                continue
            ya = set(guia.items.values_list("lugar__slug", flat=True))
            lugares = {p.slug: p for p in Places.objects.filter(slug__in=[s for s, _c, _e in paradas]).prefetch_related(None)}
            nuevas = [(lugares[s], c, e) for s, c, e in paradas if s in lugares and s not in ya]
            faltan = [s for s, _c, _e in paradas if s not in lugares]
            self.stdout.write(
                f"{slug}: {len(ya)} paradas + {len(nuevas)} nuevas"
                + (f" | faltan: {', '.join(faltan)}" if faltan else "")
            )
            if dry or not nuevas:
                continue
            with transaction.atomic():
                # Las nuevas van delante. Postgres revisa (guia, posicion) fila a fila: correr las de
                # siempre de un salto chocaría, así que pasan primero por un rango libre.
                guia.items.update(posicion=F("posicion") + 1000)
                guia.items.update(posicion=F("posicion") - 1000 + len(nuevas))
                for posicion, (lugar, comentario, comentario_en) in enumerate(nuevas, start=1):
                    CuratedGuideItem.objects.create(
                        guia=guia, lugar=lugar, posicion=posicion, comentario=comentario, comentario_en=comentario_en,
                    )
                guia.descripcion, guia.descripcion_en = descripcion, descripcion_en
                guia.save(update_fields=["descripcion", "descripcion_en", "fecha_actualizacion"])
            self.stdout.write(f"  ampliada: /guias/{slug}/ ({len(ya) + len(nuevas)} paradas)")
        if dry:
            self.stdout.write(self.style.WARNING("dry-run: no se guardó nada"))
