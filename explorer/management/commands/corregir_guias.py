"""Correcciones editoriales de las guías (revisión del 9 nov 2026). Por defecto solo muestra el cambio.

  python manage.py corregir_guias            # vista previa: antes → después, no guarda nada
  python manage.py corregir_guias --aplicar  # lo aplica en una transacción

Qué corrige y por qué (ver docs/REVISION_GUIAS_2026-11-09.md):
- Paradas fuera de la zona de su guía: Despecho Medellín, DANCEFREE y Donde Aquellos (El Poblado) en
  Laureles; Barrio Sur (Envigado) en Bares en El Poblado.
- Hatoviejo Palmas (Buenos Aires) en el Centro de día: la guía es del Centro, va la sede de Junín.
- Purple Club: la dirección de la ficha (Cl 10A #36-29) es la del hotel Haven; su Instagram oficial
  no da dirección y fuentes secundarias lo ponen en la Av. 33. Sale hasta verificarla.
- 37 Park: su Instagram oficial no muestra terraza en altura; sale de la guía de rooftops.
- La Matriarca El Poblado tenía tipo "dog_cafe" por un barrido de descubrimiento; Maps dice restaurante.
- En las tres guías prioritarias solo queda publicado el texto que respalda una fuente oficial. El
  resto pasa a notas_editoriales con lo que falta verificar, sin borrarlo.
- En las demás guías publicadas, las recomendaciones genéricas ("Japonés.", "Terraza con nota alta.")
  pasan a notas: no explican nada y se repetían en las fichas.

No pone autor ni fecha de revisión: eso lo hace el editor cuando revise de verdad. Idempotente.
"""

from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max

from explorer.models import CuratedGuide, CuratedGuideItem, Places
from explorer.utils.guias import revisar_guia

VERIFICADO = date(2026, 11, 9)
PRIORITARIAS = ("noche-en-laureles-y-la-70", "rooftops-con-vista-al-valle", "top-de-lugares-lgbtq-en-medellin")

GUIAS = {
    "noche-en-laureles-y-la-70": {
        "para_quien": "Para una noche en Laureles y La 70: bares de salsa, rumba con comida y discotecas, "
                      "todos dentro de Laureles-Estadio.",
        "para_quien_en": "For a night out in Laureles and La 70: salsa bars, party spots with food and clubs, "
                         "all inside Laureles-Estadio.",
        "criterio": "Solo lugares dentro de Laureles-Estadio con ficha publicada, para elegir por el tipo de "
                    "música. Horarios, cover y reglas de entrada salen de la web o "
                    "las redes oficiales de cada lugar, con la fecha en que se consultaron.",
        "criterio_en": "Only places inside Laureles-Estadio with a published listing, to choose by music. "
                       "Opening hours, cover and door rules come from each venue's own "
                       "website or social accounts, with the date they were checked.",
    },
    "rooftops-con-vista-al-valle": {
        "titulo": "Rooftops en Medellín",
        "titulo_en": "Rooftops in Medellín",
        "para_quien": "Para elegir una terraza en lo alto de un hotel o edificio, según el plan: comer, tomar algo "
                      "o seguir la noche.",
        "para_quien_en": "To pick a terrace on top of a hotel or building, depending on the plan: dinner, drinks "
                         "or a longer night.",
        "criterio": "Solo terrazas en la parte alta de un hotel o edificio. Las "
                    "reglas de entrada y los horarios salen de la web o las redes oficiales de cada lugar, con fecha.",
        "criterio_en": "Only terraces on top of a hotel or building. Door rules "
                       "and hours come from each venue's own website or social accounts, with a date.",
    },
    "top-de-lugares-lgbtq-en-medellin": {
        "titulo": "Lugares LGBTQ en Medellín",
        "titulo_en": "LGBTQ places in Medellín",
        "descripcion": "Bares y discotecas LGBTQ de Medellín, para elegir según el plan de la noche.",
        "descripcion_en": "LGBTQ bars and clubs in Medellín, to choose by the plan for the night.",
        "para_quien": "Para quien busca un bar para empezar o una discoteca para seguir dentro de la escena LGBTQ "
                      "de la ciudad.",
        "para_quien_en": "For anyone looking for a bar to start or a club to keep going in the city's LGBTQ scene.",
        "criterio": "Entran lugares con ficha publicada que se presentan como espacios LGBTQ. "
                    "Los datos que cambian, como horarios y reservas, salen de su web o redes oficiales, "
                    "con fecha.",
        "criterio_en": "Places with a published listing that present themselves as LGBTQ venues. "
                       "Data that changes, like hours and bookings, comes from their own website or "
                       "social accounts, with a date.",
    },
    "un-dia-en-guatape": {
        # Solo tiene restaurantes: el título prometía un día completo. El itinerario está en el borrador
        # un-dia-en-guatape-ampliada; la URL no cambia.
        "titulo": "Dónde comer en Guatapé",
        "titulo_en": "Where to eat in Guatapé",
    },
}

QUITAR = {
    "noche-en-laureles-y-la-70": {
        "dulce-jesus-mio": "Despecho Medellín está en El Poblado (Cra. 38 #19-255), fuera de Laureles.",
        "dancefree": "DANCEFREE está en El Poblado (Cl 10A #40-27), fuera de Laureles.",
        "donde-aquellos-bar": "Donde Aquellos está en El Poblado (Cra. 38 #9A-26), fuera de Laureles.",
    },
    "bares-en-el-poblado": {
        "barrio-sur-cafe-bar": "Barrio Sur está en Envigado (Cl. 30 Sur #43A-23), fuera de El Poblado.",
    },
    "top-de-lugares-lgbtq-en-medellin": {
        "purple-club": "La dirección de la ficha (Cl 10A #36-29) es la del hotel Haven. Su Instagram oficial "
                       "(@purpleclub_medellin, activo en nov 2026) no da dirección; fuentes secundarias lo ponen en "
                       "la Av. 33 #78-107. Volver a añadir cuando la dirección esté confirmada y la ficha corregida.",
    },
    "rooftops-con-vista-al-valle": {
        "37-park-medellin-restaurante-bar": "Su Instagram oficial no muestra terraza en altura; fuentes "
                                            "secundarias lo describen a nivel de calle.",
        "panorama-rooftop-bar": "La ficha está cerrada: no se mostraba y rompía la numeración.",
    },
}

CAMBIAR_SEDE = {
    "centro-de-dia": (
        "restaurante-hatoviejo", "restaurante-hatoviejo-centro",
        "La guía es del Centro: Hatoviejo Palmas está en Buenos Aires (Cl. 16 #28-60); la sede de Junín, "
        "Cra. 47 #52-17, en La Candelaria.",
    ),
}

# Texto con fuente oficial. Lo que cambia (horarios, cover, reglas) va en advertencia, con fuente y fecha.
PARADAS = {
    ("noche-en-laureles-y-la-70", "la-tienda-de-la-70"): {
        "comentario": "Rumba con comida montañera, artistas y shows en vivo, según su perfil oficial.",
        "comentario_en": "A party spot with mountain-style Colombian food, artists and live shows, per its official profile.",
        "ocasion": "rumba con comida",
        "ocasion_en": "partying with food",
        "fuente_url": "https://www.instagram.com/latiendadela70/",
    },
    ("noche-en-laureles-y-la-70", "son-havana-bar"): {
        "comentario": "Bar de salsa y son cubano, como se presenta en su web.",
        "comentario_en": "A salsa and Cuban son bar, as its website presents it.",
        "ocasion": "bailar salsa",
        "ocasion_en": "dancing salsa",
        "fuente_url": "https://sonhavana.co/",
    },
    ("noche-en-laureles-y-la-70", "dulcinea"): {
        "comentario": "Discoteca de Laureles con reguetón, vallenato y bandas en vivo, según su web.",
        "comentario_en": "A Laureles club with reggaeton, vallenato and live bands, per its website.",
        "ocasion": "bailar reguetón y vallenato",
        "ocasion_en": "dancing reggaeton and vallenato",
        "advertencia": "Abre de jueves a sábado. Cover y consumo mínimo cambian cada semana; reservas por WhatsApp. "
                       "Código semiformal (sin gorra, pantaloneta ni chanclas) y solo mayores de 18 con documento original.",
        "advertencia_en": "Open Thursday to Saturday. Cover and minimum spend change weekly; bookings by WhatsApp. "
                          "Smart-casual dress code (no caps, shorts or flip-flops), 18+ with original ID.",
        "fuente_url": "https://discotecadulcinea.com/",
        "verificado_en": VERIFICADO,
    },
    ("rooftops-con-vista-al-valle", "inzolente-rooftop"): {
        "comentario": "La terraza del último piso del hotel Hashtag98, en El Poblado.",
        "comentario_en": "The top-floor terrace of the Hashtag98 hotel, in El Poblado.",
        "advertencia": "Solo mayores de 18, según su perfil oficial.",
        "advertencia_en": "18+ only, per its official profile.",
        "fuente_url": "https://www.instagram.com/inzolenterooftop/",
        "verificado_en": VERIFICADO,
    },
    ("rooftops-con-vista-al-valle", "the-up-garden-rooftop"): {
        "comentario": "La terraza del Art Hotel, en El Poblado, con carta de cocina y cócteles.",
        "comentario_en": "The Art Hotel's terrace, in El Poblado, with a food and cocktail menu.",
        "advertencia": "Reservas por mensaje directo o WhatsApp, según su perfil oficial.",
        "advertencia_en": "Bookings by direct message or WhatsApp, per its official profile.",
        "fuente_url": "https://www.instagram.com/theupgardenrooftop/",
        "verificado_en": VERIFICADO,
    },
    ("rooftops-con-vista-al-valle", "lavocaderia-laureles-rooftop"): {
        "comentario": "Restaurante de cocina con aguacate en el sexto piso del Hotel Mythical, junto a Unicentro. "
                      "La única terraza de la lista en Laureles.",
        "comentario_en": "An avocado-themed restaurant on the sixth floor of Hotel Mythical, next to Unicentro. "
                         "The only terrace on this list in Laureles.",
        "ocasion": "almorzar o cenar",
        "ocasion_en": "lunch or dinner",
        "advertencia": "Lunes a jueves de 12 m. a 10 p. m., viernes y sábado hasta las 10:30 p. m., domingos y "
                       "festivos hasta las 9 p. m. Reservas en línea.",
        "advertencia_en": "Monday to Thursday 12 pm–10 pm, Friday and Saturday until 10:30 pm, Sundays and holidays "
                          "until 9 pm. Online bookings.",
        "fuente_url": "https://linktr.ee/lavocaderia",
        "verificado_en": VERIFICADO,
    },
    ("top-de-lugares-lgbtq-en-medellin", "bar-chiquita"): {
        "comentario": "Se presenta como «el bar gay cerca de ti»: shows de drag todas las noches, cócteles y reguetón.",
        "comentario_en": "It calls itself “the gay bar near you”: drag shows every night, cocktails and reggaeton.",
        "ocasion": "shows de drag",
        "ocasion_en": "drag shows",
        "advertencia": "Martes a jueves y domingos de 6 p. m. a 2 a. m.; viernes y sábados de 7 p. m. a 3 a. m. "
                       "Reservas por WhatsApp.",
        "advertencia_en": "Tuesday to Thursday and Sunday 6 pm–2 am; Friday and Saturday 7 pm–3 am. Bookings by WhatsApp.",
        "fuente_url": "https://barchiquita.com/",
        "verificado_en": VERIFICADO,
    },
}

AGREGAR = {
    "noche-en-laureles-y-la-70": ["dulcinea"],
}

# Texto que no respalda ninguna fuente oficial: pasa a notas con lo que hay que verificar.
SIN_FUENTE = {
    "noche-en-laureles-y-la-70": {
        "el-tibiri-bar": "Sin web ni redes legibles. Fuentes secundarias: bar de salsa en un sótano, desde 1991.",
    },
    "rooftops-con-vista-al-valle": {
        "envy-rooftop": "Web de The Charlee (403) y perfil con restricción de edad: confirmar terraza y vista.",
        "360-rooftop-bar": "Sin fuente oficial. Secundarias: piso 11 del hotel Haven, Cl 10A #36-29, con piscina.",
        "la-deriva-rooftop-bar": "Sin fuente oficial. Secundarias: terraza del hotel Click Clack, sexto piso.",
        "mal-de-ojo-rooftop-medellin": "Sin fuente oficial y dos direcciones distintas en secundarias.",
        "mamba-negra": "Sin fuente oficial. Secundarias: Cl. 2 #20-50, piso 22. Confirmar que es terraza.",
        "zarzo-rooftop-bar": "Hotel El Zarzo (Cra. 38 #10A-29) confirma el bar, pero no describe terraza ni vista.",
    },
    "top-de-lugares-lgbtq-en-medellin": {
        "club-oraculo": "Sin fuente oficial legible. Secundarias: Cra. 36 #8A-123, shows de drag.",
        "industry-club-medellin": "Instagram oficial solo con login de mayores de 18. Secundarias la ponen en "
                                  "Calle 26A #43F-72 (Barrio Colombia); confirmar zona y concepto.",
        "donde-aquellos-bar": "Sin fuente oficial legible. Secundarias: bar gay con terraza desde 2000, Cra 38 #9A-26.",
    },
}

TIPOS = {
    "restaurante-la-matriarca-medellin-chicharron-comida-tradicional": (
        "dog_cafe", "restaurant", "Maps: Restaurante colombiano (primary_type restaurant).",
    ),
}


def _nota(item, texto):
    previas = (item.notas_editoriales or "").strip()
    return texto if texto in previas else (previas + "\n" + texto).strip()


class Command(BaseCommand):
    help = "Corrige las guías (revisión del 9 nov 2026). Sin --aplicar solo muestra los cambios."

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Guarda los cambios")

    def handle(self, *args, **options):
        aplicar = options["aplicar"]
        self.cambios = 0
        with transaction.atomic():
            self._guias()
            self._quitar()
            self._sedes()
            self._agregar()
            self._paradas()
            self._sin_fuente()
            self._genericos()
            self._tipos()
            if not aplicar:
                transaction.set_rollback(True)
        verbo = "aplicados" if aplicar else "por aplicar (vista previa, nada guardado)"
        self.stdout.write(self.style.SUCCESS(f"\n{self.cambios} cambios {verbo}"))
        if aplicar:
            self.stdout.write("\nAvisos que quedan en las guías prioritarias:")
            for guia in CuratedGuide.objects.filter(slug__in=PRIORITARIAS):
                for aviso in revisar_guia(guia):
                    self.stdout.write(f"  {guia.slug}: {aviso}")

    def _log(self, texto):
        self.cambios += 1
        self.stdout.write(f"  {texto}")

    def _guias(self):
        self.stdout.write("\nGuías")
        for slug, campos in GUIAS.items():
            guia = CuratedGuide.objects.filter(slug=slug).first()
            if guia is None:
                self.stdout.write(f"  no existe: {slug}")
                continue
            cambiados = []
            for campo, valor in campos.items():
                if getattr(guia, campo) != valor:
                    self._log(f"{slug}.{campo}: {str(getattr(guia, campo))[:60]!r} → {valor[:60]!r}")
                    setattr(guia, campo, valor)
                    cambiados.append(campo)
            if cambiados:
                guia.save(update_fields=cambiados + ["fecha_actualizacion"])

    def _quitar(self):
        self.stdout.write("\nParadas que salen")
        for slug, lugares in QUITAR.items():
            for lugar_slug, motivo in lugares.items():
                item = CuratedGuideItem.objects.filter(guia__slug=slug, lugar__slug=lugar_slug).first()
                if item:
                    self._log(f"{slug}: sale {lugar_slug} (#{item.posicion}, «{item.comentario[:50]}»). {motivo}")
                    item.delete()

    def _sedes(self):
        self.stdout.write("\nSedes")
        for slug, (vieja, nueva, motivo) in CAMBIAR_SEDE.items():
            item = CuratedGuideItem.objects.filter(guia__slug=slug, lugar__slug=vieja).first()
            if item:
                lugar = Places.objects.get(slug=nueva)
                self._log(f"{slug}: {vieja} → {nueva}. {motivo}")
                item.lugar = lugar
                item.notas_editoriales = _nota(item, f"Sede corregida el {VERIFICADO}: {motivo}")
                item.save(update_fields=["lugar", "notas_editoriales"])

    def _agregar(self):
        self.stdout.write("\nParadas nuevas")
        for slug, lugares in AGREGAR.items():
            guia = CuratedGuide.objects.get(slug=slug)
            for lugar_slug in lugares:
                lugar = Places.objects.get(slug=lugar_slug)
                if guia.items.filter(lugar=lugar).exists():
                    continue
                posicion = (guia.items.aggregate(m=Max("posicion"))["m"] or 0) + 1
                CuratedGuideItem.objects.create(guia=guia, lugar=lugar, posicion=posicion)
                self._log(f"{slug}: entra {lugar_slug} en la posición {posicion}")

    def _paradas(self):
        self.stdout.write("\nTexto con fuente oficial")
        for (slug, lugar_slug), campos in PARADAS.items():
            item = CuratedGuideItem.objects.filter(guia__slug=slug, lugar__slug=lugar_slug).first()
            if item is None:
                self.stdout.write(f"  no está: {slug} / {lugar_slug}")
                continue
            cambiados = []
            for campo, valor in campos.items():
                if getattr(item, campo) != valor:
                    if campo == "comentario" and item.comentario:
                        item.notas_editoriales = _nota(item, f"Comentario anterior: {item.comentario}")
                        cambiados.append("notas_editoriales")
                    setattr(item, campo, valor)
                    cambiados.append(campo)
            if cambiados:
                self._log(f"{slug} / {lugar_slug}: {', '.join(c for c in cambiados if c != 'notas_editoriales')}")
                item.save(update_fields=sorted(set(cambiados)))

    def _sin_fuente(self):
        self.stdout.write("\nTexto sin fuente oficial → notas")
        for slug, lugares in SIN_FUENTE.items():
            for lugar_slug, falta in lugares.items():
                item = CuratedGuideItem.objects.filter(guia__slug=slug, lugar__slug=lugar_slug).first()
                if item is None:
                    continue
                self._a_notas(item, f"Pendiente de verificar ({VERIFICADO}): {falta}", f"{slug} / {lugar_slug}")

    def _genericos(self):
        self.stdout.write("\nRecomendaciones genéricas → notas")
        for guia in CuratedGuide.objects.filter(publicado=True).exclude(slug__in=PRIORITARIAS):
            genericas = {a.slug for a in revisar_guia(guia) if a.codigo == "generico"}
            for item in guia.items.filter(lugar__slug__in=genericas).select_related("lugar"):
                self._a_notas(item, "Falta por qué elegirlo: el texto anterior era genérico.", f"{guia.slug} / {item.lugar.slug}")

    def _a_notas(self, item, nota, etiqueta):
        if not (item.comentario or item.comentario_en or item.destacado or item.advertencia):
            item.notas_editoriales = _nota(item, nota)
            item.save(update_fields=["notas_editoriales"])
            return
        anterior = " | ".join(t for t in (item.comentario, item.comentario_en, item.destacado, item.advertencia) if t)
        self._log(f"{etiqueta}: «{item.comentario[:60]}» → notas")
        item.notas_editoriales = _nota(item, f"{nota}\nTexto anterior: {anterior}")
        item.comentario = item.comentario_en = item.destacado = item.destacado_en = item.advertencia = ""
        item.save(update_fields=["comentario", "comentario_en", "destacado", "destacado_en", "advertencia", "notas_editoriales"])

    def _tipos(self):
        self.stdout.write("\nTipos de ficha")
        for slug, (antes, despues, motivo) in TIPOS.items():
            n = Places._base_manager.filter(slug=slug, tipo=antes).update(tipo=despues)
            if n:
                self._log(f"{slug}: {antes} → {despues}. {motivo}")
