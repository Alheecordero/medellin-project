"""
Excluir los que ya tenemos y descartar los que no nos sirven.

1. Pendientes cuyo place_id YA está en Places → marcar 'processed' (ya los tenemos).
2. Del resto: los que no nos sirven (tipo no útil o tipo excluido) → marcar 'skipped'.
3. El resto siguen 'pending' para procesar después.

Así la cola solo tiene lugares nuevos y útiles para vivemedellin.co.

Uso:
  python manage.py descartar_pendientes_inutiles --dry-run   # Solo muestra
  python manage.py descartar_pendientes_inutiles             # Aplica
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from explorer.models import PendingPlace, Places

from explorer.management.commands.scan_nuevos_lugares import (
    EXCLUDED_TYPES,
    EXTRA_EXCLUDED_TYPES,
    INCLUDED_TYPES,
)


class Command(BaseCommand):
    help = 'Excluir ya existentes (processed) y descartar inútiles (skipped).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Solo muestra cuántos, sin guardar')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        pendientes = PendingPlace.objects.filter(status='pending')
        total = pendientes.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No hay pendientes con status='pending'."))
            return

        # 1) place_ids que ya tenemos en Places (excluir = marcar processed)
        existing_place_ids = set(Places.objects.values_list('place_id', flat=True))
        to_mark_processed = []
        to_evaluate = []
        for p in pendientes.only('id', 'place_id', 'tipos'):
            if p.place_id in existing_place_ids:
                to_mark_processed.append(p.id)
            else:
                to_evaluate.append(p)

        # 2) De los que no están en Places: descartar los que no nos sirven
        excluded_all = frozenset(EXCLUDED_TYPES) | frozenset(EXTRA_EXCLUDED_TYPES)
        to_skip_ids = []
        for p in to_evaluate:
            tipos = list(p.tipos) if p.tipos else []
            if any(t in excluded_all for t in tipos):
                to_skip_ids.append(p.id)
                continue
            if not any(t in INCLUDED_TYPES for t in tipos):
                to_skip_ids.append(p.id)

        remain = total - len(to_mark_processed) - len(to_skip_ids)

        self.stdout.write(f"📋 Pendientes (pending): {total}")
        self.stdout.write(f"   Ya en Places (→ processed): {len(to_mark_processed)}")
        self.stdout.write(f"   No nos sirven (→ skipped):  {len(to_skip_ids)}")
        self.stdout.write(f"   Siguen pendientes:          {remain}")

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\n⚠️  DRY RUN — nada guardado. Ejecuta sin --dry-run para aplicar."
            ))
            return

        if to_mark_processed:
            PendingPlace.objects.filter(id__in=to_mark_processed).update(
                status='processed', procesado_en=now,
            )
            self.stdout.write(self.style.SUCCESS(f"\n✅ {len(to_mark_processed)} marcados como processed (ya en Places)."))
        if to_skip_ids:
            PendingPlace.objects.filter(id__in=to_skip_ids).update(
                status='skipped', procesado_en=now,
            )
            self.stdout.write(self.style.SUCCESS(f"✅ {len(to_skip_ids)} marcados como skipped (no nos sirven)."))

        remaining = PendingPlace.objects.filter(status='pending').count()
        self.stdout.write(f"\n   Pendientes restantes: {remaining}")
        self.stdout.write(f"   → python manage.py procesar_pendientes")
