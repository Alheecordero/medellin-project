"""Revisión editorial de las guías y numeración de sus paradas.

Los avisos no bloquean nada: le dicen al editor qué mirar antes de publicar o de fechar una
revisión. Las reglas (`revisar`) trabajan sobre datos simples para poder probarlas sin base;
`revisar_guia` los saca de la base.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

FORMATOS_NUMERADOS = ("ranking", "ruta")
# Una recomendación de menos palabras no explica nada ("Japonés.", "Mariscos.").
PALABRAS_MIN = 5
# Justificar con la nota o las reseñas no basta: son de Google, no criterio propio.
SOLO_NOTA = re.compile(r"\b(nota|reseñ|rating|valorad|estrellas)", re.I)
# Señales de que el lugar ya no está donde dice la ficha.
MUDANZA = re.compile(r"traslad|nueva ubicaci|se mud|cerr[óo]|ya no (est|exist|func)|no est[aá] ah[ií]|permanently closed|moved", re.I)
RESENAS_MIN = 20
# Palabras que no distinguen una sede de otra en el nombre.
# Palabras que no distinguen una marca de otra: tipos de lugar, artículos y zonas.
RELLENO_NOMBRE = {
    "restaurante", "restaurant", "bar", "cafe", "club", "discoteca", "rooftop", "the", "el", "la", "los",
    "las", "de", "del", "y", "medellin", "sede", "centro", "comercial", "cc", "poblado", "laureles",
    "parque", "museo", "mirador", "teatro", "casa", "jardin", "tour", "cerro", "plaza", "iglesia", "hotel",
    "ecoturistico", "ecologico", "natural", "fundacion", "universidad", "estacion", "comuna", "area", "reserva",
    "pizzeria", "cafeteria", "panaderia", "heladeria", "pasteleria", "areperia", "estadero", "cocina", "comida",
}
CAMPOS_TEXTO_GUIA = (
    "titulo", "titulo_en", "descripcion", "descripcion_en", "como_recorrer", "como_recorrer_en",
    "para_quien", "para_quien_en", "criterio", "criterio_en", "consejos", "consejos_en",
)
CAMPOS_TEXTO_PARADA = (
    "posicion", "comentario", "comentario_en", "destacado", "destacado_en", "como_llegar", "como_llegar_en",
    "advertencia", "advertencia_en", "diferencia", "diferencia_en", "ocasion", "ocasion_en", "presupuesto",
)


@dataclass
class Parada:
    slug: str
    nombre: str
    posicion: int = 0
    visible: bool = True
    comuna: str = ""
    en_zona: bool | None = None  # None: la guía no es de una zona
    fuera_de_zona_motivo: str = ""
    sedes_en_zona: list[str] = field(default_factory=list)  # otras sedes del mismo nombre dentro de la zona
    comentario: str = ""
    tipo: str = ""
    tipo_maps: str = ""
    total_reviews: int | None = None
    resenas_recientes: list[str] = field(default_factory=list)
    presupuesto: str = ""
    advertencia: str = ""
    verificado_en: date | None = None


@dataclass
class Aviso:
    codigo: str
    mensaje: str
    slug: str = ""

    def __str__(self):
        return f"[{self.codigo}] {self.slug + ': ' if self.slug else ''}{self.mensaje}"


def numerar(items, formato):
    """Número continuo sobre lo que se ve. Una selección no lleva número: no es un ranking."""
    for i, item in enumerate(items, start=1):
        item.numero = i if formato in FORMATOS_NUMERADOS else None
    return items


def nombre_base(nombre: str) -> str:
    """'Restaurante Hatoviejo Palmas' y 'Restaurante Hatoviejo Centro' → 'hatoviejo'."""
    texto = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode().lower()
    texto = re.split(r"\s[-|–(]\s?|\|", texto)[0]
    palabras = [p for p in re.findall(r"[a-z0-9]+", texto) if p not in RELLENO_NOMBRE]
    return palabras[0] if palabras else ""


def revisar(paradas: list[Parada], *, zona: str = "", formato: str = "seleccion", como_recorrer: str = "",
            publicada: bool = False, revisada: bool = False) -> list[Aviso]:
    avisos = []
    visibles = [p for p in paradas if p.visible]
    for p in paradas:
        if not p.visible:
            avisos.append(Aviso("oculta", "No se muestra (cerrada, fusionada o sin ficha publicada). Quitarla o reemplazarla.", p.slug))
            continue
        if p.en_zona is False and not p.fuera_de_zona_motivo.strip():
            msg = f"Está en {p.comuna or 'otra zona'}, fuera de {zona}."
            if p.sedes_en_zona:
                msg += f" ¿Sede equivocada? En la zona está {', '.join(p.sedes_en_zona)}."
            avisos.append(Aviso("fuera_de_zona", msg + " Quitarla o explicar la excepción.", p.slug))
        if p.tipo_maps and p.tipo and p.tipo != p.tipo_maps:
            avisos.append(Aviso("tipo", f"La ficha dice «{p.tipo}» y Maps «{p.tipo_maps}».", p.slug))
        if p.total_reviews is not None and p.total_reviews < RESENAS_MIN:
            avisos.append(Aviso("evidencia", f"Solo {p.total_reviews} reseñas: confirmar que existe y dónde.", p.slug))
        if any(MUDANZA.search(t or "") for t in p.resenas_recientes):
            avisos.append(Aviso("mudanza", "Una reseña habla de traslado o cierre: verificar la dirección.", p.slug))
        texto = (p.comentario or "").strip()
        if not texto:
            avisos.append(Aviso("sin_texto", "Sin recomendación: falta por qué elegirlo.", p.slug))
        elif len(texto.split()) < PALABRAS_MIN:
            avisos.append(Aviso("generico", f"«{texto}» no explica por qué elegirlo.", p.slug))
        elif SOLO_NOTA.search(texto):
            avisos.append(Aviso("generico", f"«{texto}» se apoya en la nota de Google.", p.slug))
        if (p.presupuesto or p.advertencia) and not p.verificado_en:
            avisos.append(Aviso("sin_fuente", "Presupuesto o aviso sin fecha de verificación: no se publican.", p.slug))

    vistos = {}
    for p in visibles:
        base = nombre_base(p.nombre)
        if base and base in vistos:
            avisos.append(Aviso("duplicado", f"Parece la misma marca que {vistos[base]}.", p.slug))
        vistos.setdefault(base, p.slug)

    if formato == "ruta" and not como_recorrer.strip():
        avisos.append(Aviso("ruta", "Es un recorrido pero no dice cómo hacerlo."))
    if publicada and not revisada:
        avisos.append(Aviso("sin_revision", "Publicada sin autor ni fecha de revisión editorial."))
    return avisos


def _paradas(guia) -> list[Parada]:
    from explorer.models import GooglePlaceDetails, Places, parada_visible

    items = list(guia.items.select_related("lugar").order_by("posicion"))
    visibles = set(guia.items.filter(parada_visible()).values_list("pk", flat=True))
    lugares = [i.lugar for i in items]
    detalles = {
        d.place_id: d for d in GooglePlaceDetails.objects.filter(place_id__in=[l.place_id for l in lugares if l.place_id])
        .only("place_id", "primary_type")
    }
    dentro = set()
    if guia.zona_id and guia.zona.geom_4326:
        dentro = set(
            Places._base_manager.filter(pk__in=[l.pk for l in lugares], ubicacion__within=guia.zona.geom_4326)
            .values_list("pk", flat=True)
        )
    from explorer.utils.place_classify import TIPOS_NICHO, vive_tipo_for_google

    paradas = []
    for item in items:
        lugar = item.lugar
        en_zona = None
        sedes = []
        if guia.zona_id:
            comuna = lugar.comuna
            en_zona = lugar.pk in dentro or (comuna is not None and comuna.pk == guia.zona_id)
            base = nombre_base(lugar.nombre)
            if not en_zona and base and guia.zona.geom_4326:
                sedes = list(
                    Places.objects.filter(tiene_fotos=True, nombre__icontains=base, ubicacion__within=guia.zona.geom_4326)
                    .exclude(pk=lugar.pk).values_list("slug", flat=True)[:3]
                )
        detalle = detalles.get(lugar.place_id)
        tipo_maps = vive_tipo_for_google(detalle.primary_type) if detalle and detalle.primary_type else ""
        # Solo los tipos de nicho que pega el barrido (La Matriarca, "dog_cafe"). Un teatro que Maps
        # llama discoteca o un museo con café no son errores de la ficha.
        if lugar.tipo not in TIPOS_NICHO or tipo_maps in ("", "otros", lugar.tipo):
            tipo_maps = ""
        recientes = sorted(
            (r for r in (lugar.reviews or []) if isinstance(r, dict)),
            key=lambda r: r.get("publishTime") or "", reverse=True,
        )[:3]
        paradas.append(Parada(
            slug=lugar.slug, nombre=lugar.nombre, posicion=item.posicion, visible=item.pk in visibles,
            comuna=lugar.comuna.name if lugar.comuna else "", en_zona=en_zona,
            fuera_de_zona_motivo=item.fuera_de_zona_motivo, sedes_en_zona=sedes,
            comentario=item.comentario, tipo=lugar.tipo, tipo_maps=tipo_maps,
            total_reviews=lugar.total_reviews,
            resenas_recientes=[(r.get("text") or {}).get("text", "") if isinstance(r.get("text"), dict) else (r.get("text") or "") for r in recientes],
            presupuesto=item.presupuesto, advertencia=item.advertencia, verificado_en=item.verificado_en,
        ))
    return paradas


def revisar_guia(guia) -> list[Aviso]:
    return revisar(
        _paradas(guia), zona=guia.zona.name if guia.zona_id else "", formato=guia.formato,
        como_recorrer=guia.como_recorrer, publicada=guia.publicado, revisada=bool(guia.revisado_en and guia.autor),
    )


def campos_importables(objeto, nuevos: dict, protegidos) -> dict:
    """Lo que un importador puede escribir: nada de texto en una guía o parada ya revisada."""
    revisado = getattr(objeto, "revisado_en", None) or getattr(objeto, "verificado_en", None)
    if objeto is None or not revisado:
        return dict(nuevos)
    return {k: v for k, v in nuevos.items() if k not in protegidos}
