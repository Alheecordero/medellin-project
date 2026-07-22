"""Helpers de URL/endpoint para Cloudflare R2."""

from urllib.parse import urlparse


def normalize_public_base_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/"


def normalize_r2_endpoint(endpoint_url: str, bucket: str) -> str:
    endpoint = endpoint_url.rstrip("/")
    suffix = f"/{bucket}"
    if endpoint.endswith(suffix):
        endpoint = endpoint[: -len(suffix)]
    return endpoint


def public_media_domain(public_base: str) -> str:
    return urlparse(public_base).netloc or public_base.replace("https://", "").replace("http://", "")
