"""URLs públicas de media (GCS → R2)."""

from __future__ import annotations

from urllib.parse import urlparse

# Origen histórico ViveMedellín en Google Cloud Storage
GCS_BUCKET = "vivemedellin-bucket"
GCS_PUBLIC_PREFIX = f"https://storage.googleapis.com/{GCS_BUCKET}/"


def normalize_public_base_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/"


def normalize_r2_endpoint(endpoint_url: str, bucket: str) -> str:
    """
    Acepta endpoint con o sin sufijo /bucket (como lo muestra el panel de Cloudflare).
    django-storages espera solo: https://<account>.r2.cloudflarestorage.com
    """
    endpoint = endpoint_url.rstrip("/")
    suffix = f"/{bucket}"
    if endpoint.endswith(suffix):
        endpoint = endpoint[: -len(suffix)]
    return endpoint


def gcs_url_to_public(url: str | None, public_base: str) -> str | None:
    """Convierte una URL de GCS al dominio público de R2 (misma ruta de objeto)."""
    if not url:
        return url
    base = normalize_public_base_url(public_base)
    if url.startswith(GCS_PUBLIC_PREFIX):
        return base + url[len(GCS_PUBLIC_PREFIX) :]
    # Por si quedó otro host de GCS con el mismo bucket
    marker = f"googleapis.com/{GCS_BUCKET}/"
    if marker in url:
        path = url.split(marker, 1)[1]
        return base + path
    return url


def resolve_media_url(url: str | None) -> str | None:
    """Devuelve la URL pública en R2; convierte GCS legacy si hace falta."""
    if not url:
        return url
    try:
        from django.conf import settings

        public_base = (
            getattr(settings, "R2_PUBLIC_BASE_URL", None)
            or getattr(settings, "MEDIA_PUBLIC_BASE_URL", "https://img.vivemedellin.co/")
        ).rstrip("/")
    except Exception:
        public_base = "https://img.vivemedellin.co"
    converted = gcs_url_to_public(url, public_base)
    return converted if converted else url


def public_media_url(object_path: str, public_base: str) -> str:
    """Arma URL pública a partir de ruta relativa en el bucket (sin / inicial)."""
    path = object_path.lstrip("/")
    return normalize_public_base_url(public_base) + path


def public_media_domain(public_base: str) -> str:
    return urlparse(public_base).netloc or public_base.replace("https://", "").replace("http://", "")
