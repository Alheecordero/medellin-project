"""
Reactiva lugares descartados (skipped) que tienen al menos un tipo ÚTIL (en INCLUDED_TYPES).
Sirve para recuperar heladerías, panaderías, cafés, etc. que se descartaron por error.

Uso:
  python manage.py reactivar_descartados_utiles --dry-run   # Cuántos se reactivarían
  python manage.py reactivar_descartados_utiles             # Ponerlos de nuevo en pending
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from explorer.models import PendingPlace

from explorer.management.commands.scan_nuevos_lugares import INCLUDED_TYPES


class Command(BaseCommand):
    help = 'Reactiva descartados que tienen un tipo útil (ej. heladerías, panaderías).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        included = frozenset(INCLUDED_TYPES)

        skipped = PendingPlace.objects.filter(status='skipped')
        to_reactivate = []
        for p in skipped.only('id', 'nombre', 'tipos').iterator(chunk_size=500):
            tipos = list(p.tipos) if p.tipos else []
            if any(t in included for t in tipos):
                to_reactivate.append(p.id)

        count = len(to_reactivate)
        self.stdout.write(f"Descartados (skipped): {skipped.count():,}")
        self.stdout.write(f"A reactivar (tienen al menos un tipo útil): {count:,}")

        if count == 0:
            self.stdout.write(self.style.WARNING("Nada que reactivar."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n⚠️  DRY RUN — ejecuta sin --dry-run para reactivar {count}"))
            return

        updated = PendingPlace.objects.filter(id__in=to_reactivate).update(
            status='pending',
            procesado_en=None,
        )
        self.stdout.write(self.style.SUCCESS(f"\n✅ {updated} lugares reactivados (pending)."))
        self.stdout.write(f"   → python manage.py procesar_pendientes")
