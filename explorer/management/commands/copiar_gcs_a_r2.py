"""
Copia objetos de Google Cloud Storage a Cloudflare R2 (misma ruta/clave).

Recomendado para velocidad máxima: scripts/migrar_gcs_a_r2_rclone.sh (rclone).

Uso Django:
  python manage.py copiar_gcs_a_r2 --dry-run
  python manage.py copiar_gcs_a_r2 --workers 48 --no-head-check
  python manage.py copiar_gcs_a_r2 --prefix tourism/
"""
from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from google.cloud import storage as gcs_storage
from google.oauth2 import service_account

from Medellin.r2_config import normalize_r2_endpoint

# Hilos comparten cliente GCS; cada hilo usa su propio cliente S3 (thread-safe).
_thread_local = threading.local()
MULTIPART_THRESHOLD = 8 * 1024 * 1024  # 8 MB


class Command(BaseCommand):
    help = "Copia gs://vivemedellin-bucket → R2 (paralelo, streaming)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0, help="Máx. objetos (0 = todos)")
        parser.add_argument("--prefix", type=str, default="", help="Solo un prefijo, ej. tourism/")
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            default=True,
            help="Omitir objetos que ya existen en R2 (head_object por archivo)",
        )
        parser.add_argument(
            "--no-head-check",
            action="store_true",
            help="No comprobar R2 antes de copiar (más rápido si el bucket está vacío)",
        )
        parser.add_argument("--workers", type=int, default=32, help="Hilos paralelos (default: 32)")

    def handle(self, *args, **options):
        if not getattr(settings, "USE_R2", False):
            raise CommandError(
                "Configura R2 en .env (R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT_URL)."
            )

        gcs_bucket_name = getattr(settings, "GS_BUCKET_NAME", "vivemedellin-bucket")
        creds_path = os.path.join(settings.BASE_DIR, "vivemedellin-fdc8cbb3b441.json")
        if not os.path.exists(creds_path):
            creds_path = getattr(settings, "GS_CREDENTIALS_PATH", creds_path)
        if not os.path.exists(creds_path):
            raise CommandError(f"No se encuentra credencial GCS: {creds_path}")

        workers = max(1, options["workers"])
        dry_run = options["dry_run"]
        limit = options["limit"]
        prefix = options["prefix"]
        skip_existing = options["skip_existing"] and not options["no_head_check"]

        endpoint = normalize_r2_endpoint(settings.R2_ENDPOINT_URL, settings.R2_BUCKET)
        gcs_creds = service_account.Credentials.from_service_account_file(creds_path)
        gcs_client = gcs_storage.Client(
            credentials=gcs_creds, project=getattr(settings, "GS_PROJECT_ID", "vivemedellin")
        )
        gcs_bucket = gcs_client.bucket(gcs_bucket_name)

        r2_bucket = settings.R2_BUCKET
        r2_endpoint = endpoint
        r2_key_id = settings.R2_ACCESS_KEY_ID
        r2_secret = settings.R2_SECRET_ACCESS_KEY

        def get_s3():
            if not getattr(_thread_local, "s3", None):
                _thread_local.s3 = boto3.client(
                    "s3",
                    endpoint_url=r2_endpoint,
                    aws_access_key_id=r2_key_id,
                    aws_secret_access_key=r2_secret,
                    region_name="auto",
                )
            return _thread_local.s3

        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(f"📦 GCS  gs://{gcs_bucket_name}/{prefix}")
        self.stdout.write(f"📦 R2   {r2_bucket} → {settings.R2_PUBLIC_BASE_URL}")
        self.stdout.write(f"⚡ Workers: {workers}")
        if skip_existing:
            self.stdout.write("   Modo: omitir existentes (head check)")
        else:
            self.stdout.write(self.style.WARNING("   Modo: copiar sin head check (--no-head-check)"))
        if dry_run:
            self.stdout.write(self.style.WARNING("   ⚠️  DRY RUN"))
        self.stdout.write("")
        self.stdout.write(
            self.style.NOTICE(
                "💡 Más rápido: ./scripts/migrar_gcs_a_r2_rclone.sh (rclone sync, ~5–15×)"
            )
        )
        self.stdout.write("")
        sys.stdout.flush()

        stats = {"listed": 0, "copied": 0, "skipped": 0, "errors": 0, "bytes": 0}
        lock = threading.Lock()
        t0 = time.time()

        def log(msg: str) -> None:
            self.stdout.write(msg)
            sys.stdout.flush()

        def upload_stream(blob, s3) -> int:
            """GCS → R2 en streaming (sin cargar todo en RAM)."""
            size = blob.size or 0
            extra = {"ContentType": blob.content_type or "application/octet-stream"}
            with blob.open("rb") as src:
                if size >= MULTIPART_THRESHOLD:
                    from boto3.s3.transfer import TransferConfig

                    cfg = TransferConfig(
                        multipart_threshold=MULTIPART_THRESHOLD,
                        max_concurrency=4,
                        multipart_chunksize=8 * 1024 * 1024,
                        use_threads=True,
                    )
                    s3.upload_fileobj(src, r2_bucket, blob.name, ExtraArgs=extra, Config=cfg)
                else:
                    s3.upload_fileobj(src, r2_bucket, blob.name, ExtraArgs=extra)
            return size

        def copy_blob(blob) -> tuple[str, int]:
            key = blob.name
            s3 = get_s3()
            if skip_existing:
                try:
                    s3.head_object(Bucket=r2_bucket, Key=key)
                    return "skipped", 0
                except ClientError as e:
                    if e.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):
                        raise

            if dry_run:
                return "copied", blob.size or 0

            nbytes = upload_stream(blob, s3)
            return "copied", nbytes

        max_pending = workers * 4
        pending: set = set()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            for blob in gcs_client.list_blobs(gcs_bucket, prefix=prefix or None):
                with lock:
                    stats["listed"] += 1
                    listed = stats["listed"]
                if limit and listed > limit:
                    break

                pending.add(executor.submit(copy_blob, blob))

                if len(pending) >= max_pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        try:
                            status, nbytes = future.result()
                            with lock:
                                stats[status] += 1
                                stats["bytes"] += nbytes
                        except Exception as exc:
                            with lock:
                                stats["errors"] += 1
                            log(self.style.ERROR(f"   ✗ {exc}"))

                with lock:
                    copied = stats["copied"]
                    skipped = stats["skipped"]
                    listed = stats["listed"]
                    nbytes = stats["bytes"]
                if listed % 1000 == 0:
                    elapsed = time.time() - t0
                    rate = listed / elapsed if elapsed else 0
                    log(
                        f"   … {listed:,} listados | copiados {copied:,} | "
                        f"omitidos {skipped:,} | {nbytes/1e9:.2f} GB | {rate:.0f} obj/s"
                    )

            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        status, nbytes = future.result()
                        with lock:
                            stats[status] += 1
                            stats["bytes"] += nbytes
                    except Exception as exc:
                        with lock:
                            stats["errors"] += 1
                        log(self.style.ERROR(f"   ✗ {exc}"))

        elapsed = time.time() - t0
        self.stdout.write(f"\n{'═' * 60}")
        self.stdout.write(self.style.SUCCESS("📊 RESUMEN COPIA GCS → R2"))
        self.stdout.write(f"   Listados:  {stats['listed']:,}")
        self.stdout.write(f"   Copiados:  {stats['copied']:,}")
        self.stdout.write(f"   Omitidos:  {stats['skipped']:,}")
        self.stdout.write(f"   Errores:   {stats['errors']:,}")
        self.stdout.write(f"   Datos:     {stats['bytes']/1e9:.2f} GB")
        self.stdout.write(f"   Tiempo:    {elapsed/60:.1f} min")
        if elapsed > 0 and stats["copied"]:
            self.stdout.write(f"   Velocidad: {stats['copied']/elapsed:.1f} obj/s\n")
        sys.stdout.flush()
