"""Quita las variantes de foto (mediana y miniatura) que dan 404 en R2.

Cerca del 2,5 % de las miniaturas de fichas indexables no existen en el bucket (bug 17 de la
auditoría). La plantilla usa el original cuando la variante está vacía, así que vaciar el
campo arregla la imagen rota. El original no se toca.

Solo pide la cabecera (HEAD) de cada URL. Con --dry-run cuenta y no escribe.

  python manage.py revisar_miniaturas --dry-run
  python manage.py revisar_miniaturas
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import requests
from django.core.management.base import BaseCommand
from django.db.models import Q

from explorer.models import Foto, Places
from explorer.utils.media_urls import resolve_media_url

CAMPOS = ("imagen_miniatura", "imagen_mediana")


def _falta(url: str) -> bool:
    """True solo si R2 responde 404: un fallo de red no borra nada."""
    try:
        return requests.head(resolve_media_url(url) or url, timeout=10, allow_redirects=True).status_code == 404
    except requests.RequestException:
        return False


class Command(BaseCommand):
    help = "Vacía las variantes de foto que no existen en R2 (fichas indexables)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--hilos", type=int, default=16)
        parser.add_argument("--limit", type=int, default=0, help="0 = todas")

    def handle(self, *args, **options):
        fotos = (
            Foto.objects.filter(lugar__in=Places.objects.indexables().prefetch_related(None).values("pk"))
            .filter(Q(imagen_miniatura__gt="") | Q(imagen_mediana__gt=""))
            .values_list("pk", *CAMPOS)
        )
        if options["limit"]:
            fotos = fotos[: options["limit"]]
        urls = [(pk, campo, url) for pk, *valores in fotos for campo, url in zip(CAMPOS, valores) if url]
        self.stdout.write(f"revisando {len(urls)} variantes")
        with ThreadPoolExecutor(max_workers=options["hilos"]) as pool:
            rotas = [(pk, campo) for (pk, campo, _u), falta in zip(urls, pool.map(lambda t: _falta(t[2]), urls)) if falta]

        por_campo = {campo: [pk for pk, c in rotas if c == campo] for campo in CAMPOS}
        self.stdout.write(f"rotas: {len(rotas)} de {len(urls)} | " + ", ".join(f"{c}: {len(p)}" for c, p in por_campo.items()))
        if options["dry_run"]:
            for pk, campo in rotas[:20]:
                self.stdout.write(f"  foto {pk} {campo}")
            self.stdout.write(self.style.WARNING("dry-run: no se guardó nada"))
            return
        for campo, pks in por_campo.items():
            if pks:
                Foto.objects.filter(pk__in=pks).update(**{campo: None})
        self.stdout.write(self.style.SUCCESS(f"vaciadas {len(rotas)} variantes"))
