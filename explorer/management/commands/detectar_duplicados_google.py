"""
Detecta posibles duplicados: registros distintos que Text Search resuelve al mismo place_id.

Recorre lugares con google_match_status=review o ambiguous, o todos si --all.
Si dos Places distintos obtienen el mismo ID candidato de Google, los reporta.

Uso:
  python manage.py detectar_duplicados_google --dry-run
  python manage.py detectar_duplicados_google --limit 100
"""
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from explorer.models import Places
from explorer.utils.google_places import build_text_query, text_search_ids_only


class Command(BaseCommand):
    help = "Encuentra Places distintos que podrían ser el mismo establecimiento en Google."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--all",
            action="store_true",
            help="Revisar todos los lugares, no solo review/ambiguous",
        )

    def handle(self, *args, **options):
        api_key = getattr(settings, "GOOGLE_API_KEY", None)
        if not api_key:
            raise CommandError("GOOGLE_API_KEY no configurada.")

        # Duplicados obvios: mismo place_id (no debería pasar por unique)
        dup_place_id = (
            Places.objects.values("place_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        if dup_place_id.exists():
            self.stdout.write(self.style.ERROR("⚠️  place_id duplicados en BD (violación de unique):"))
            for row in dup_place_id:
                lugares = Places.objects.filter(place_id=row["place_id"])
                self.stdout.write(f"   {row['place_id']}: {lugares.count()} registros")

        qs = Places.objects.all().order_by("nombre")
        if not options["all"]:
            qs = qs.filter(google_match_status__in=["review", "ambiguous", "pending"])
        if options["limit"] > 0:
            qs = qs[: options["limit"]]

        # Agrupar por nombre normalizado (heurística rápida sin API)
        from explorer.utils.google_places import normalize_name

        by_norm: dict[str, list] = {}
        for lugar in qs.iterator():
            key = normalize_name(lugar.nombre)
            if len(key) < 4:
                continue
            by_norm.setdefault(key, []).append(lugar)

        candidatos = {k: v for k, v in by_norm.items() if len(v) > 1}
        if not candidatos:
            self.stdout.write(self.style.SUCCESS("No se encontraron grupos con nombres similares en el subset."))
            return

        self.stdout.write(f"\n🔎 {len(candidatos)} grupo(s) con nombres normalizados iguales:\n")
        for norm, lugares in sorted(candidatos.items(), key=lambda x: -len(x[1])):
            self.stdout.write(f"\n   «{norm}» ({len(lugares)} registros):")
            for l in lugares:
                self.stdout.write(f"      • [{l.id}] {l.nombre} — place_id={l.place_id[:20]}…")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\n⚠️  DRY RUN — usa verificar_place_ids_google para confirmar con Google."))
            return

        self.stdout.write(
            "\n💡 Siguiente paso: revisar manualmente o unir registros tras confirmar con "
            "verificar_place_ids_google y Place Details."
        )
