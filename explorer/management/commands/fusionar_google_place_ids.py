"""
Fase 0 del plan gratuito: fusionar IDs existentes al catálogo GooglePlaceId.

Importa Places.place_id y PendingPlace.place_id sin llamar a Google.

Uso:
  python manage.py fusionar_google_place_ids --dry-run
  python manage.py fusionar_google_place_ids
"""
from django.core.management.base import BaseCommand

from explorer.models import GooglePlaceId, PendingPlace, Places
from explorer.utils.google_ids_registry import register_google_place_ids


class Command(BaseCommand):
    help = "Fusiona Places + PendingPlace → GooglePlaceId (gratis, sin API)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        places_ids = list(Places.objects.values_list("place_id", flat=True))
        pending_ids = list(PendingPlace.objects.values_list("place_id", flat=True))
        catalog_ids = set(GooglePlaceId.objects.values_list("place_id", flat=True))

        nuevos_places = [p for p in places_ids if p and p not in catalog_ids]
        nuevos_pending = [p for p in pending_ids if p and p not in catalog_ids]
        # Pending puede solapar Places
        pending_only = [p for p in nuevos_pending if p not in set(places_ids)]

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(self.style.SUCCESS("📦 FASE 0 — Fusión al catálogo GooglePlaceId"))
        self.stdout.write(f"   Places total:           {len(places_ids):,}")
        self.stdout.write(f"   PendingPlace total:     {len(pending_ids):,}")
        self.stdout.write(f"   Catálogo actual:        {len(catalog_ids):,}")
        self.stdout.write(f"   Nuevos desde Places:    {len(nuevos_places):,}")
        self.stdout.write(f"   Nuevos solo Pending:     {len(pending_only):,}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n   ⚠️  DRY RUN — nada guardado"))
            return

        n1, u1 = register_google_place_ids(
            nuevos_places,
            source="places_import",
            included_type="places_import",
        )
        n2, u2 = register_google_place_ids(
            pending_only,
            source="pending_import",
            included_type="pending_import",
        )

        total = GooglePlaceId.objects.count()
        self.stdout.write(self.style.SUCCESS(f"\n   🆕 Importados Places:   {n1:,}"))
        self.stdout.write(self.style.SUCCESS(f"   🆕 Importados Pending:   {n2:,}"))
        self.stdout.write(f"   ↻ Actualizados:          {u1 + u2:,}")
        self.stdout.write(self.style.SUCCESS(f"   📚 Catálogo total:      {total:,}\n"))
