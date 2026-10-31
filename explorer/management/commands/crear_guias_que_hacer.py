"""Crea como borradores las guías hechas con lugares de Qué hacer.

Las paradas se eligieron a mano el 31 oct 2026, en dos tandas de cuatro guías, entre los
lugares publicados con publicar_que_hacer. Quedan sin publicar y sin comentarios: el comentario de cada parada
es la opinión del local y la escribe quien publica. El staff las ve en su URL normal.

La versión ampliada de Guatapé es una copia de la guía publicada con el Peñol y el pueblo
delante; trae los comentarios de los restaurantes. La publicada no se toca.

No borra nada y no toca una guía que ya exista con el mismo slug.

  python manage.py crear_guias_que_hacer --dry-run
  python manage.py crear_guias_que_hacer
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from explorer.models import CuratedGuide, CuratedGuideItem, Places, RegionOSM

GUIAS = (
    {
        "slug": "comuna-13",
        "titulo": "Comuna 13: qué ver",
        "titulo_en": "Comuna 13: what to see",
        "descripcion": (
            "La Comuna 13 pasó de ser uno de los barrios más golpeados por la violencia a ser el "
            "recorrido más visitado de Medellín: grafitis, escaleras eléctricas al aire libre, hip hop "
            "y miradores sobre la ciudad. Estas son las paradas para recorrerla en una mañana."
        ),
        "descripcion_en": (
            "Comuna 13 went from being one of the neighborhoods hit hardest by violence to Medellín's "
            "most visited walk: graffiti, open-air escalators, hip hop and viewpoints over the city. "
            "These are the stops to see it in a morning."
        ),
        "como_recorrer": (
            "Llega en metro hasta la estación San Javier y sigue hasta las escaleras eléctricas. "
            "Mejor temprano, antes de que se llene."
        ),
        "categoria": "zona",
        "zona": "San Javier",
        "tema": "dia",
        "paradas": (
            "tour-comuna-13-medellin",
            "escalas-electricas-de-la-comuna-13",
            "mirador-comuna-13",
            "casa-de-las-estrategias-casa-cultural-morada",
            "tour-comuna-13-graffitour-guia-graffiti-tour",
            "estacion-metrocable-juan-xxiii",
        ),
    },
    {
        "slug": "museos-de-medellin",
        "titulo": "Museos de Medellín",
        "titulo_en": "Museums in Medellín",
        "descripcion": (
            "Los museos mejor valorados de Medellín, del arte moderno a la memoria del conflicto, con "
            "un castillo y un planetario en medio."
        ),
        "descripcion_en": (
            "Medellín's best rated museums, from modern art to the memory of the conflict, with a "
            "castle and a planetarium in between."
        ),
        "categoria": "plan",
        "tema": "dia",
        "paradas": (
            "museo-el-castillo",
            "museo-de-arte-moderno-de-medellin",
            "museo-casa-de-la-memoria",
            "muua-museo-universitario-de-la-universidad-de-antioquia",
            "planetario-de-medellin-jesus-emilio-ramirez",
            "museo-del-agua-epm",
            "casa-museo-otraparte",
            "museo-etnografico-madre-laura",
        ),
    },
    {
        "slug": "miradores-de-medellin",
        "titulo": "Miradores de Medellín",
        "titulo_en": "Viewpoints in Medellín",
        "descripcion": (
            "Dónde ver el valle de Aburrá desde arriba: cerros de la ciudad, Las Palmas, Santa Elena y "
            "algunos en Bello y Sabaneta. Casi todos se disfrutan mejor al atardecer."
        ),
        "descripcion_en": (
            "Where to see the Aburrá Valley from above: the city's hills, Las Palmas, Santa Elena and a "
            "few in Bello and Sabaneta. Most are best at sunset."
        ),
        "categoria": "plan",
        "tema": "dia",
        "paradas": (
            "mirador-cerro-el-picacho",
            "segundo-mirador-de-las-palmas",
            "mirador-de-santa-elena",
            "parque-de-las-esculturas-cerro-nutibara",
            "mirador-comuna-13",
            "mirador-segundo-piso-estacion-metrocable",
            "mirador-de-san-felix",
            "vista-al-vuelo",
            "el-asfixiadero",
        ),
    },
    {
        "slug": "un-dia-en-guatape-ampliada",
        "titulo": "Un día en Guatapé",
        "titulo_en": "A day in Guatapé",
        "descripcion": (
            "Guatapé en un día: subir la Piedra del Peñol, caminar las calles de zócalos de colores y "
            "terminar en una mesa junto al embalse."
        ),
        "descripcion_en": (
            "Guatapé in a day: climb the rock of El Peñol, walk the streets of painted zócalos and end "
            "at a table by the reservoir."
        ),
        "categoria": "escapada",
        "zona": "Guatapé",
        "orden": 40,
        "paradas": (
            "la-piedra-de-guatape-y-penol",
            "plazoleta-de-los-zocalos",
            "parque-principal-de-guatape",
            "malecon-de-guatape",
            "monasterio-santa-maria-de-la-epifania",
        ),
        "copiar_paradas_de": "un-dia-en-guatape",
    },
    {
        "slug": "que-hacer-en-medellin",
        "titulo": "Qué hacer en Medellín",
        "titulo_en": "Things to do in Medellín",
        "descripcion": (
            "Lo imprescindible de Medellín para una primera visita: el centro de Botero, la Comuna 13, "
            "el metrocable a Arví, los museos que cuentan la ciudad y un día en Guatapé."
        ),
        "descripcion_en": (
            "The essentials of Medellín for a first visit: Botero's downtown, Comuna 13, the cable car "
            "to Arví, the museums that tell the city's story and a day in Guatapé."
        ),
        "categoria": "plan",
        "tema": "dia",
        "orden": 10,
        "paradas": (
            "plaza-botero",
            "parque-de-los-pies-descalzos",
            "tour-comuna-13-medellin",
            "museo-casa-de-la-memoria",
            "jardin-botanico-de-medellin",
            "parque-explora",
            "parque-arvi",
            "museo-de-arte-moderno-de-medellin",
            "museo-el-castillo",
            "parque-de-las-esculturas-cerro-nutibara",
            "estadio-de-futbol-atanasio-girardot",
            "la-piedra-de-guatape-y-penol",
        ),
    },
    {
        "slug": "planes-con-ninos",
        "titulo": "Planes con niños en Medellín",
        "titulo_en": "Things to do with kids in Medellín",
        "descripcion": (
            "Ciencia, animales, agua y aventura: los planes mejor valorados de Medellín para ir con "
            "niños, casi todos cerca de una estación del metro."
        ),
        "descripcion_en": (
            "Science, animals, water and adventure: Medellín's best rated plans with kids, most of "
            "them near a metro station."
        ),
        "categoria": "plan",
        "tema": "dia",
        "paradas": (
            "parque-explora",
            "planetario-de-medellin-jesus-emilio-ramirez",
            "jardin-botanico-de-medellin",
            "parque-de-los-deseos",
            "parque-norte",
            "museo-del-agua-epm",
            "parques-del-rio",
            "summit-adventure-park-medellin",
            "flying-squirrel-sports-los-molinos-medellin",
            "parque-arvi",
        ),
    },
    {
        "slug": "parques-y-naturaleza",
        "titulo": "Parques y naturaleza cerca de Medellín",
        "titulo_en": "Parks and nature near Medellín",
        "descripcion": (
            "Bosque, quebradas y cerros sin salir del valle: de Arví en metrocable a los cerros "
            "tutelares de la ciudad."
        ),
        "descripcion_en": (
            "Forest, streams and hills without leaving the valley: from Arví by cable car to the "
            "city's guardian hills."
        ),
        "categoria": "plan",
        "tema": "dia",
        "paradas": (
            "parque-arvi",
            "chorro-clarin-parque-arvi",
            "jardin-botanico-de-medellin",
            "orquideorama-jardin-botanico",
            "parque-natural-cerro-el-volador",
            "cerro-de-las-tres-cruces-medellin",
            "parque-ecoturistico-el-salado",
            "jardin-circunvalar-cinturon-verde",
            "parque-ecologico-los-salados-comfenalco-antioquia",
        ),
    },
    {
        "slug": "teatros-de-medellin",
        "titulo": "Teatros de Medellín",
        "titulo_en": "Theaters in Medellín",
        "descripcion": (
            "De los grandes escenarios del centro a las salas independientes: dónde ver teatro, "
            "conciertos y ópera en Medellín."
        ),
        "descripcion_en": (
            "From the big downtown stages to independent venues: where to see theater, concerts and "
            "opera in Medellín."
        ),
        "categoria": "plan",
        "tema": "noche",
        "paradas": (
            "teatro-pablo-tobon-uribe",
            "teatro-metropolitano-jose-gutierrez-gomez",
            "pequeno-teatro-de-medellin",
            "museo-teatro-prado-el-aguila-descalza",
            "teatro-matacandelas",
            "teatro-universitario-camilo-torres",
            "teatro-de-la-universidad-de-medellin",
            "fundacion-casateatro-el-poblado",
        ),
    },
)


class Command(BaseCommand):
    help = "Crea como borradores las guías hechas con lugares de Qué hacer."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        for spec in GUIAS:
            if CuratedGuide.objects.filter(slug=spec["slug"]).exists():
                self.stdout.write(f"ya existe: {spec['slug']} (no se toca)")
                continue
            lugares = {p.slug: p for p in Places.objects.filter(slug__in=spec["paradas"]).prefetch_related(None)}
            faltan = [s for s in spec["paradas"] if s not in lugares]
            copiadas = []
            if spec.get("copiar_paradas_de"):
                origen = CuratedGuide.objects.filter(slug=spec["copiar_paradas_de"]).first()
                if origen:
                    copiadas = list(origen.items.order_by("posicion"))
            zona = RegionOSM.objects.filter(name=spec["zona"]).order_by("-way_area").first() if spec.get("zona") else None
            self.stdout.write(
                f"{spec['slug']}: {len(lugares)} paradas nuevas + {len(copiadas)} copiadas"
                + (f" | faltan: {', '.join(faltan)}" if faltan else "")
                + (f" | zona: {zona.name}" if zona else "")
            )
            if dry:
                continue
            with transaction.atomic():
                guia = CuratedGuide.objects.create(
                    slug=spec["slug"],
                    titulo=spec["titulo"],
                    titulo_en=spec["titulo_en"],
                    descripcion=spec["descripcion"],
                    descripcion_en=spec["descripcion_en"],
                    como_recorrer=spec.get("como_recorrer", ""),
                    categoria=spec["categoria"],
                    tema=spec.get("tema", ""),
                    zona=zona,
                    orden=spec.get("orden", 50),
                    publicado=False,
                )
                posicion = 0
                for slug in spec["paradas"]:
                    if slug in lugares:
                        posicion += 1
                        CuratedGuideItem.objects.create(guia=guia, lugar=lugares[slug], posicion=posicion)
                for item in copiadas:
                    if item.lugar_id in {l.pk for l in lugares.values()}:
                        continue
                    posicion += 1
                    CuratedGuideItem.objects.create(
                        guia=guia, lugar_id=item.lugar_id, posicion=posicion,
                        comentario=item.comentario, comentario_en=item.comentario_en,
                        como_llegar=item.como_llegar, advertencia=item.advertencia,
                        destacado=item.destacado, destacado_en=item.destacado_en,
                    )
            self.stdout.write(f"  creada como borrador: /guias/{guia.slug}/ ({posicion} paradas)")
        if dry:
            self.stdout.write(self.style.WARNING("dry-run: no se guardó nada"))
