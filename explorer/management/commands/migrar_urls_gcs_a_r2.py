"""
Reescribe URLs de media en la BD: GCS → dominio público R2.

Uso:
  python manage.py migrar_urls_gcs_a_r2 --dry-run
  python manage.py migrar_urls_gcs_a_r2
  python manage.py migrar_urls_gcs_a_r2 --verify-sample 20
"""
import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from explorer.models import CuratedGuide, Foto
from explorer.utils.media_urls import GCS_PUBLIC_PREFIX, gcs_url_to_public


class Command(BaseCommand):
    help = "Convierte URLs storage.googleapis.com → R2 (img.vivemedellin.co)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--verify-sample", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **options):
        public_base = (
            getattr(settings, "R2_PUBLIC_BASE_URL", None)
            or getattr(settings, "MEDIA_PUBLIC_BASE_URL", "https://img.vivemedellin.co/")
        ).rstrip("/")
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write("🔄 Migración de URLs GCS → R2")
        self.stdout.write(f"   Origen:  {GCS_PUBLIC_PREFIX}")
        self.stdout.write(f"   Destino: {public_base}/")
        if dry_run:
            self.stdout.write(self.style.WARNING("   ⚠️  DRY RUN"))
        self.stdout.write("")

        stats = {"foto": 0, "guide": 0, "fields": 0}
        to_save: list[Foto] = []

        for foto in Foto.objects.iterator(chunk_size=batch_size):
            changed = False
            for field in ("imagen", "imagen_miniatura", "imagen_mediana"):
                old = getattr(foto, field)
                new = gcs_url_to_public(old, public_base)
                if new and new != old:
                    setattr(foto, field, new)
                    stats["fields"] += 1
                    changed = True
            if changed:
                stats["foto"] += 1
                if dry_run:
                    continue
                to_save.append(foto)
                if len(to_save) >= batch_size:
                    Foto.objects.bulk_update(
                        to_save, ["imagen", "imagen_miniatura", "imagen_mediana"], batch_size=batch_size
                    )
                    self.stdout.write(f"   … {stats['foto']:,} fotos actualizadas")
                    to_save.clear()

        if to_save and not dry_run:
            Foto.objects.bulk_update(
                to_save, ["imagen", "imagen_miniatura", "imagen_mediana"], batch_size=batch_size
            )

        guides_save = []
        for guide in CuratedGuide.objects.exclude(imagen_cover="").exclude(imagen_cover__isnull=True):
            new = gcs_url_to_public(guide.imagen_cover, public_base)
            if new and new != guide.imagen_cover:
                stats["guide"] += 1
                stats["fields"] += 1
                if not dry_run:
                    guide.imagen_cover = new
                    guides_save.append(guide)

        if guides_save and not dry_run:
            CuratedGuide.objects.bulk_update(guides_save, ["imagen_cover"])

        self.stdout.write(self.style.SUCCESS(f"   Fotos actualizadas:   {stats['foto']:,}"))
        self.stdout.write(self.style.SUCCESS(f"   Guías actualizadas:  {stats['guide']:,}"))
        self.stdout.write(f"   Campos URL tocados:  {stats['fields']:,}")

        remaining = Foto.objects.filter(imagen__contains="storage.googleapis.com").count()
        if remaining:
            self.stdout.write(self.style.WARNING(f"   ⚠️  Fotos aún con GCS: {remaining:,}"))
        else:
            self.stdout.write(self.style.SUCCESS("   ✅ Sin URLs GCS en Foto.imagen"))

        if options["verify_sample"] and not dry_run:
            self._verify(options["verify_sample"])

        self.stdout.write("")

    def _verify(self, sample: int):
        self.stdout.write(f"\n🔍 Verificando {sample} URLs…")
        ok = fail = 0
        for foto in Foto.objects.exclude(imagen="").order_by("?")[:sample]:
            url = foto.imagen
            if not url or "storage.googleapis.com" in url:
                continue
            try:
                r = requests.head(url, timeout=15, allow_redirects=True)
                if r.status_code == 200:
                    ok += 1
                else:
                    fail += 1
                    self.stdout.write(self.style.ERROR(f"   ✗ {r.status_code} {url[:80]}…"))
            except requests.RequestException as exc:
                fail += 1
                self.stdout.write(self.style.ERROR(f"   ✗ {url[:60]}… — {exc}"))
        self.stdout.write(self.style.SUCCESS(f"   OK: {ok} | Fallos: {fail} (404 = archivo aún no copiado a R2)"))
