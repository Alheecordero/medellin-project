"""Contenido propio de la ficha a partir de datos que ya tenemos: carta, atributos y reseñas.

Google ve lo mismo en Maps; lo que nos distingue es la carta con precios y un resumen
que la junta con el horario y los servicios.
"""

from __future__ import annotations

import re
from statistics import quantiles

from django.utils.translation import gettext as _

PRECIO_MINIMO = 2000  # Por debajo son adiciones o errores del partner.
MAX_PLATOS_SCHEMA = 40
SECCION_RELLENO = re.compile(r"promo|combo|\bby\b|bebida|gaseosa|adici|extra|para llevar|lo más pedido|más vendido|recomendad", re.I)


def pesos(valor: int) -> str:
    return "$" + f"{valor:,}".replace(",", ".")


def rango_precios(secciones) -> tuple[int, int] | None:
    """Cuartiles 1 y 3 de los platos con precio: el rango donde cae la mitad de la carta.

    Sin bebidas, adiciones ni combos del partner, salvo que la carta sea solo eso.
    """
    def _precios(filtrar):
        return sorted(
            plato.price
            for seccion in secciones
            if not (filtrar and SECCION_RELLENO.search(seccion["nombre"]))
            for plato in seccion["platos"]
            if plato.price and plato.price >= PRECIO_MINIMO and plato.is_available
        )

    precios = _precios(True)
    if len(precios) < 4:
        precios = _precios(False)
    if len(precios) < 4:
        return None
    q1, _q2, q3 = quantiles(precios, n=4)
    bajo, alto = _redondear(q1), _redondear(q3)
    return (bajo, alto) if bajo < alto else None


BOTELLA = re.compile(r"licor|botella|\d\s*ml\b|champa|whisk|vodka|tequila|\bron\b|vino|aguardiente|buchanan|old par", re.I)
PRECIO_TOPE = 300_000  # un plato por encima de esto y muy lejos del resto de la carta es un error
VECES_LA_MEDIANA = 20


def quitar_precios_imposibles(secciones) -> int:
    """Quita (solo en memoria) los precios que el partner escribió mal; devuelve cuántos.

    "$0" o un plato a veinte veces la mediana de la carta y por encima del tope ("Bandeja
    con carne" a $15.900.000, un tinto a $700.000) no se muestran ni van al rango ni al
    schema. Las botellas de licor sí pueden valer eso.
    """
    platos = [plato for seccion in secciones for plato in seccion["platos"]]
    # Con todos los precios: en una carta de empanadas a $1.900 la mediana es eso.
    precios = sorted(p.price for p in platos if p.price)
    mediana = precios[len(precios) // 2] if precios else 0
    quitados = 0
    for seccion in secciones:
        for plato in seccion["platos"]:
            cero = plato.price == 0 or plato.price_text.strip() in {"$0", "$ 0"}
            lejos = (
                mediana
                and (plato.price or 0) > max(PRECIO_TOPE, VECES_LA_MEDIANA * mediana)
                and not BOTELLA.search(f"{plato.name} {seccion['nombre']}")
            )
            if cero or lejos:
                plato.price, plato.price_text = None, ""
                quitados += 1
    return quitados


def _redondear(valor: float) -> int:
    return int(round(valor / 1000.0)) * 1000


def secciones_destacadas(secciones, limite: int = 3) -> list[str]:
    """Las secciones con más platos, sin las de promociones o bebidas del partner."""
    candidatas = [
        (len(seccion["platos"]), seccion["nombre"].strip())
        for seccion in secciones
        if seccion["nombre"].strip() and not SECCION_RELLENO.search(seccion["nombre"])
    ]
    candidatas.sort(key=lambda par: -par[0])
    vistas, nombres = set(), []
    for _n, nombre in candidatas:
        clave = nombre.lower()
        if clave not in vistas:
            vistas.add(clave)
            nombres.append(nombre.lower() if nombre.isupper() else nombre)
        if len(nombres) == limite:
            break
    return nombres


def _lista(items: list[str]) -> str:
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " " + _("y") + " " + items[-1]


def resumen(lugar, *, total_platos: int, secciones: list[str], rango, horario_filas) -> str:
    """Párrafo corto con lo que sabemos del lugar. Vacío si no hay nada que decir."""
    frases = []

    if total_platos and rango:
        frases.append(_("Su carta tiene %(n)s platos; la mitad cuesta entre %(bajo)s y %(alto)s.") % {
            "n": total_platos, "bajo": pesos(rango[0]), "alto": pesos(rango[1]),
        })
    elif total_platos:
        frases.append(_("Su carta tiene %(n)s platos.") % {"n": total_platos})
    if secciones:
        frases.append(_("Destacan %(secciones)s.") % {"secciones": _lista(secciones)})

    comidas = [nombre for campo, nombre in (
        ("serves_breakfast", _("desayuno")),
        ("serves_brunch", _("brunch")),
        ("serves_lunch", _("almuerzo")),
        ("serves_dinner", _("cena")),
    ) if getattr(lugar, campo)]
    if comidas:
        frases.append(_("Sirve %(comidas)s.") % {"comidas": _lista(comidas)})

    bebidas = [nombre for campo, nombre in (
        ("serves_coffee", _("café")),
        ("serves_beer", _("cerveza")),
        ("serves_wine", _("vino")),
        ("serves_cocktails", _("cócteles")),
    ) if getattr(lugar, campo)]
    if bebidas:
        frases.append(_("Para tomar hay %(bebidas)s.") % {"bebidas": _lista(bebidas)})

    rasgos = [nombre for campo, nombre in (
        ("outdoor_seating", _("terraza")),
        ("live_music", _("música en vivo")),
        ("allows_dogs", _("ambiente pet friendly")),
        ("good_for_groups", _("espacio para grupos")),
        ("good_for_children", _("plan para ir con niños")),
    ) if getattr(lugar, campo)]
    if rasgos:
        frases.append(_("Además: %(rasgos)s.") % {"rasgos": _lista(rasgos)})

    servicio = [nombre for campo, nombre in (
        ("delivery", _("domicilio")),
        ("takeout", _("para llevar")),
    ) if getattr(lugar, campo)]
    if servicio:
        frases.append(_("Hay servicio de %(servicio)s.") % {"servicio": _lista(servicio)})

    dias = sum(1 for fila in horario_filas or [] if fila.get("rangos"))
    if dias == 7:
        frases.append(_("Abre todos los días."))
    elif dias:
        frases.append(_("Abre %(n)s días a la semana.") % {"n": dias})

    # Una sola frase no aporta nada que no digan ya los chips.
    return " ".join(frases) if len(frases) >= 2 else ""


def citas_resenas(reviews, limite: int = 2, largo: int = 240) -> list[dict]:
    """Fragmentos de reseñas de 4★ o más, sin el nombre del autor."""
    citas = []
    for review in reviews or []:
        if not isinstance(review, dict) or (review.get("rating") or 0) < 4:
            continue
        texto = review.get("text")
        if isinstance(texto, dict):
            idioma = texto.get("languageCode") or ""
            texto = texto.get("text") or ""
        else:
            idioma = ""
        texto = " ".join(str(texto or "").split())
        if len(texto) < 60:
            continue
        if len(texto) > largo:
            texto = texto[:largo].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
        citas.append({
            "texto": texto,
            "rating": int(review["rating"]),
            "idioma": idioma,
            "fecha": (review.get("publishTime") or "")[:7],
        })
        if len(citas) == limite:
            break
    return citas


def menu_schema(url: str, secciones) -> dict:
    """schema.org Menu con un máximo de platos para no inflar el HTML."""
    restantes = MAX_PLATOS_SCHEMA
    bloques = []
    for seccion in secciones:
        if restantes <= 0:
            break
        items = []
        for plato in seccion["platos"]:
            if restantes <= 0:
                break
            if not plato.is_available:
                continue
            item = {"@type": "MenuItem", "name": plato.name[:120]}
            if plato.description:
                item["description"] = plato.description[:200]
            if plato.price:
                item["offers"] = {"@type": "Offer", "price": plato.price, "priceCurrency": "COP"}
            items.append(item)
            restantes -= 1
        if items:
            bloques.append({
                "@type": "MenuSection",
                "name": seccion["nombre"] or _("Carta"),
                "hasMenuItem": items,
            })
    menu = {"@type": "Menu", "url": url}
    if bloques:
        menu["hasMenuSection"] = bloques
    return menu
