"""Horario de la ficha leído de `horario_texto` ("lunes: 13:00–24:00").

Se pinta en el servidor para que Google lo lea sin JavaScript, y se convierte
en openingHoursSpecification para el JSON-LD.
"""

from __future__ import annotations

import re
import unicodedata

from django.utils.translation import gettext as _

DIAS = (
    # clave sin tildes, etiqueta en español (msgid), día de schema.org
    ("lunes", "Lunes", "Monday"),
    ("martes", "Martes", "Tuesday"),
    ("miercoles", "Miércoles", "Wednesday"),
    ("jueves", "Jueves", "Thursday"),
    ("viernes", "Viernes", "Friday"),
    ("sabado", "Sábado", "Saturday"),
    ("domingo", "Domingo", "Sunday"),
)
_INGLES = dict(zip(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"), range(7)))
_POR_CLAVE = {clave: i for i, (clave, _es, _en) in enumerate(DIAS)} | _INGLES
_RANGO = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?\s*m?\.?\s*[–\-—]+\s*(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?\s*m?\.?",
    re.I,
)


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _hora(h: str, m: str | None, ampm: str | None) -> str:
    hora = int(h)
    if ampm:
        ampm = ampm.lower()
        if ampm == "p" and hora < 12:
            hora += 12
        elif ampm == "a" and hora == 12:
            hora = 0
    hora = 23 if hora >= 24 else hora
    minuto = "59" if int(h) >= 24 else (m or "00")
    return f"{hora:02d}:{minuto}"


def filas_horario(texto: str | None) -> list[dict]:
    """Una fila por día, de lunes a domingo, con la etiqueta traducida."""
    filas = {}
    for linea in (texto or "").splitlines():
        if ":" not in linea or linea.strip() in ("", "None"):
            continue
        dia, horas = linea.split(":", 1)
        orden = _POR_CLAVE.get(_sin_tildes(dia.strip().lower()))
        if orden is None or orden in filas:
            continue
        horas = horas.strip()
        normal = _sin_tildes(horas.lower())
        cerrado = normal.startswith(("cerrado", "closed"))
        abierto_24 = "24 horas" in normal or "24 hours" in normal
        rangos = [] if cerrado else (
            [("00:00", "23:59")] if abierto_24
            else [(_hora(*m.group(1, 2, 3)), _hora(*m.group(4, 5, 6))) for m in _RANGO.finditer(horas)]
        )
        filas[orden] = {
            "dia": _(DIAS[orden][1]),
            "horas": _("Cerrado") if cerrado else horas,
            "schema_dia": DIAS[orden][2],
            "rangos": rangos,
        }
    return [filas[i] for i in sorted(filas)]


def opening_hours_spec(filas: list[dict]) -> list[dict]:
    return [
        {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": f"https://schema.org/{fila['schema_dia']}",
            "opens": abre,
            "closes": cierra,
        }
        for fila in filas
        for abre, cierra in fila["rangos"]
    ]
