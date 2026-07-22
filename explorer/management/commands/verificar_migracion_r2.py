"""
Verificación integral de migración GCS → R2.

Comprueba URLs en BD, accesibilidad HTTP y (opcional) paridad de buckets con rclone.

Uso:
  python manage.py verificar_migracion_r2
  python manage.py verificar_migracion_r2 --sample 100 --strict
  python manage.py verificar_migracion_r2 --rclone-check
"""
from __future__ import annotations

import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from explorer.models import CuratedGuide, Foto
from explorer.utils.media_urls import GCS_PUBLIC_PREFIX


class Command(BaseCommand):
    help = "Audita migración GCS→R2: BD, HTTP y opcionalmente rclone check."

    def add_arguments(self, parser):
        parser.add_argument("--sample", type=int, default=50, help="URLs aleatorias a probar con HEAD")
        parser.add_argument("--workers", type=int, default=16)
        parser.add_argument("--strict", action="store_true", help="Fallar si hay URLs GCS o HTTP <100%")
        parser.add_argument(
            "--rclone-check",
            action="store_true",
            help="Ejecutar rclone check gcs:bucket r2:bucket (lento, muy fiable)",
        )
        parser.add_argument("--min-success-pct", type=float, default=99.5, help="%% mínimo HTTP OK para corte")

    def handle(self, *args, **options):
        public_base = getattr(settings, "R2_PUBLIC_BASE_URL", "https://img.vivemedellin.co").rstrip("/")
        sample_n = options["sample"]
        workers = max(1, options["workers"])
        min_pct = options["min_success_pct"]

        self.stdout.write(f"\n{'═' * 62}")
        self.stdout.write("🔍 VERIFICACIÓN MIGRACIÓN GCS → R2")
        self.stdout.write(f"   Dominio R2: {public_base}")
        self.stdout.write(f"   USE_R2:     {getattr(settings, 'USE_R2', False)}")
        self.stdout.write("")

        ok = True

        # ── 1. URLs en base de datos ──
        self.stdout.write(self.style.HTTP_INFO("1️⃣  URLs en base de datos"))
        db_stats = self._db_stats()
        for line in db_stats["lines"]:
            self.stdout.write(f"   {line}")
        if db_stats["gcs_total"] > 0:
            ok = False
            self.stdout.write(self.style.ERROR(f"   ❌ Quedan {db_stats['gcs_total']:,} campos URL con GCS"))
        else:
            self.stdout.write(self.style.SUCCESS("   ✅ Sin URLs GCS en BD"))

        # ── 2. Muestra HTTP ──
        self.stdout.write(self.style.HTTP_INFO(f"\n2️⃣  Accesibilidad HTTP (muestra {sample_n})"))
        http_stats = self._http_sample(sample_n, workers)
        self.stdout.write(
            f"   Probadas: {http_stats['tested']:,} | OK: {http_stats['ok']:,} | "
            f"Fallos: {http_stats['fail']:,} | {http_stats['pct']:.1f} %"
        )
        if http_stats["fail_examples"]:
            for url, code in http_stats["fail_examples"][:5]:
                self.stdout.write(self.style.ERROR(f"   ✗ {code} {url[:85]}…"))
        if http_stats["pct"] < min_pct:
            ok = False
            self.stdout.write(
                self.style.ERROR(f"   ❌ Por debajo del umbral {min_pct}% (archivos faltantes en R2)")
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"   ✅ ≥ {min_pct}% accesibles en R2"))

        # ── 3. rclone check (opcional) ──
        if options["rclone_check"]:
            self.stdout.write(self.style.HTTP_INFO("\n3️⃣  rclone check (integridad bucket)"))
            rc_ok = self._rclone_check()
            if not rc_ok:
                ok = False

        # ── Resumen / criterios de corte ──
        self.stdout.write(f"\n{'═' * 62}")
        if ok:
            self.stdout.write(self.style.SUCCESS("✅ LISTO PARA CORTE: migración verificada"))
            self.stdout.write("   Siguiente: USE_R2 en .env producción → reiniciar gunicorn")
            self.stdout.write("   Esperar 7–14 días → desactivar bucket GCS")
        else:
            self.stdout.write(self.style.ERROR("❌ NO CORTAR GCS AÚN — completar migración primero"))
            self.stdout.write("   → rclone sync gcs:vivemedellin-bucket r2:vivemedellin-media")
            self.stdout.write("   → python manage.py migrar_urls_gcs_a_r2  (si quedan URLs GCS)")
            self.stdout.write("   → python manage.py verificar_migracion_r2 --sample 100")

        self.stdout.write("")
        if options["strict"] and not ok:
            sys.exit(1)

    def _db_stats(self) -> dict:
        gcs_q = Q(imagen__contains="storage.googleapis.com") | Q(
            imagen_miniatura__contains="storage.googleapis.com"
        ) | Q(imagen_mediana__contains="storage.googleapis.com")
        total = Foto.objects.count()
        gcs_fotos = Foto.objects.filter(gcs_q).distinct().count()
        gcs_fields = (
            Foto.objects.filter(imagen__contains="storage.googleapis.com").count()
            + Foto.objects.filter(imagen_miniatura__contains="storage.googleapis.com").count()
            + Foto.objects.filter(imagen_mediana__contains="storage.googleapis.com").count()
        )
        r2_all3 = Foto.objects.filter(
            imagen__contains="img.vivemedellin.co",
            imagen_miniatura__contains="img.vivemedellin.co",
            imagen_mediana__contains="img.vivemedellin.co",
        ).count()
        guides_gcs = CuratedGuide.objects.filter(imagen_cover__contains="storage.googleapis.com").count()

        lines = [
            f"Fotos totales:              {total:,}",
            f"Fotos con alguna URL GCS:   {gcs_fotos:,}",
            f"Campos URL GCS (suma):      {gcs_fields:,}",
            f"Fotos 3/3 variantes R2:     {r2_all3:,}",
            f"Guías cover GCS:            {guides_gcs:,}",
        ]
        return {"lines": lines, "gcs_total": gcs_fields + guides_gcs}

    def _http_sample(self, n: int, workers: int) -> dict:
        qs = list(
            Foto.objects.exclude(imagen="")
            .exclude(imagen__isnull=True)
            .values_list("imagen", "imagen_miniatura", "imagen_mediana")
        )
        urls: list[str] = []
        for im, mini, med in qs:
            for u in (im, mini, med):
                if u and "img.vivemedellin.co" in u:
                    urls.append(u)
        if not urls:
            return {"tested": 0, "ok": 0, "fail": 0, "pct": 0.0, "fail_examples": []}

        sample = random.sample(urls, min(n, len(urls)))

        def head(url: str) -> tuple[str, int]:
            try:
                r = requests.head(url, timeout=15, allow_redirects=True)
                return url, r.status_code
            except requests.RequestException:
                return url, 0

        ok = fail = 0
        fail_examples: list[tuple[str, int]] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(head, u) for u in sample]
            for fut in as_completed(futures):
                url, code = fut.result()
                if code == 200:
                    ok += 1
                else:
                    fail += 1
                    fail_examples.append((url, code))

        tested = ok + fail
        pct = (ok / tested * 100) if tested else 0.0
        return {"tested": tested, "ok": ok, "fail": fail, "pct": pct, "fail_examples": fail_examples}

    def _rclone_check(self) -> bool:
        gcs = f"gcs:{getattr(settings, 'GS_BUCKET_NAME', 'vivemedellin-bucket')}"
        r2 = f"r2:{getattr(settings, 'R2_BUCKET', 'vivemedellin-media')}"
        try:
            proc = subprocess.run(
                ["rclone", "check", gcs, r2, "--one-way", "--error-on-no-match"],
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if proc.returncode == 0:
                self.stdout.write(self.style.SUCCESS("   ✅ rclone check: buckets idénticos (GCS → R2)"))
                return True
            self.stdout.write(self.style.ERROR(f"   ❌ rclone check falló (code {proc.returncode})"))
            if proc.stdout:
                self.stdout.write(proc.stdout[-2000:])
            return False
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING("   ⚠️  rclone no instalado — omitido"))
            return True
        except subprocess.TimeoutExpired:
            self.stdout.write(self.style.ERROR("   ❌ rclone check timeout (>1h)"))
            return False
