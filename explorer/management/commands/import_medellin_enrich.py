"""
Importa el scrape de galería de Medellín a la base y a R2.

Lee los JSON que deja el VPS en un directorio, actualiza GooglePlaceDetails
y, si el lugar ya es público, renueva Places y añade Foto. Los lugares nuevos
quedan en PendingPlace, con las fotos ya subidas para que la URL de Google
no caduque. No publica lugares nuevos.

  python manage.py import_medellin_enrich --input-dir data/medellin-enrich --limit 8
"""

from __future__ import annotations

import hashlib
import json
import re
from io import BytesIO
from pathlib import Path

import requests
from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image

from explorer.models import (
    PLACE_TYPE_CHOICES,
    Foto,
    GooglePlaceDetails,
    GooglePlaceId,
    PendingPlace,
    Places,
)
from explorer.utils.media_urls import resolve_media_url
from explorer.utils.place_classify import classify_place

VALID_TIPOS = {code for code, _label in PLACE_TYPE_CHOICES}
HEALTH_TIPOS = {"health", "doctor"}
HEALTH_TEXT = re.compile(
    r"farmac|hospital|cl[ií]nic|veterinar|odont|dentist|droguer|"
    r"laboratorio de an[aá]lisis|centro m[eé]dico|(?<![a-záéíóú])m[eé]dic",
    re.I,
)
HEALTH_CODES = {
    "pharmacy",
    "drugstore",
    "hospital",
    "doctor",
    "dentist",
    "veterinary_care",
    "physiotherapist",
}
USER_AGENT = "Mozilla/5.0 (compatible; ViveMedellin/1.0; +https://vivemedellin.net)"
GLOBAL_RATING = 4.36
MIN_REVIEWS = 25


def _clean_address(value: str) -> str:
    text = (value or "").strip()
    for prefix in ("Dirección:", "Direccion:", "Address:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
    return text


def _hours(value):
    if not value:
        return "", None
    if isinstance(value, str):
        return value.strip(), None
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, str):
                lines.append(item.strip())
            elif isinstance(item, dict):
                lines.append(str(item.get("text") or item.get("line") or "").strip())
        return "\n".join(line for line in lines if line), value
    if isinstance(value, dict):
        text = value.get("weekday_text") or value.get("text") or ""
        if isinstance(text, list):
            text = "\n".join(str(item) for item in text)
        return str(text).strip(), value
    return str(value).strip(), None


def _http_url(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text[:1000]
    return ""


def _upgrade_photo_url(url: str) -> str:
    clean = (url or "").strip()
    low = clean.lower()
    if "googleusercontent.com" not in low and "ggpht.com" not in low:
        return clean
    if "/a/" in low or "/a-" in low:
        return ""
    base = clean.split("=", 1)[0]
    return f"{base}=w1600-h1600-k-no"


def _photo_digest(url: str) -> str:
    base = (url or "").split("=", 1)[0]
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def _image_urls(data: dict) -> list[str]:
    raw = data.get("images") or []
    urls = []
    for item in raw:
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict):
            urls.append(str(item.get("url") or item.get("src") or ""))
    seen = set()
    out = []
    for url in urls:
        upgraded = _upgrade_photo_url(url)
        if not upgraded:
            continue
        digest = _photo_digest(upgraded)
        if digest in seen:
            continue
        seen.add(digest)
        out.append(upgraded)
    return out[:30]


def _is_health(name: str, category: str, primary: str, tipo: str) -> bool:
    if tipo in HEALTH_TIPOS or (primary or "").lower() in HEALTH_CODES:
        return True
    blob = " ".join((name or "", category or "", primary or ""))
    return bool(HEALTH_TEXT.search(blob))


def _text_same(current, new) -> bool:
    return (current or "").strip() == (new or "").strip()


def _num_same(current, new, tol: float = 0.001) -> bool:
    if current is None or new is None:
        return current is None and new is None
    try:
        return abs(float(current) - float(new)) < tol
    except (TypeError, ValueError):
        return str(current) == str(new)


def _json_same(current, new) -> bool:
    return json.dumps(current, sort_keys=True, default=str) == json.dumps(
        new, sort_keys=True, default=str
    )


def _point_same(current, new_point) -> bool:
    if current is None or new_point is None:
        return current is None and new_point is None
    try:
        return (
            abs(float(current.y) - float(new_point.y)) < 1e-5
            and abs(float(current.x) - float(new_point.x)) < 1e-5
        )
    except (TypeError, ValueError, AttributeError):
        return False


def _photo_already_stored(imagen: str, digest: str, existing: set[str]) -> bool:
    if imagen in existing:
        return True
    needle = f"/g{digest}."
    return any(needle in url for url in existing)


def _ensure_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        base = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        alpha = img.split()[-1] if img.mode in ("RGBA", "LA") else None
        base.paste(img, mask=alpha)
        return base
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _fit_long_edge(img: Image.Image, edge: int) -> Image.Image:
    if max(img.size) <= edge:
        return img.copy()
    img = img.copy()
    img.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return img


def _fit_width(img: Image.Image, width: int) -> Image.Image:
    if img.width <= width:
        return img.copy()
    ratio = width / float(img.width)
    return img.resize((width, max(1, int(img.height * ratio))), Image.Resampling.LANCZOS)


def _as_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _weighted(rating, reviews) -> float | None:
    if rating is None or not reviews:
        return None
    reviews = int(reviews)
    rating = float(rating)
    total = reviews + MIN_REVIEWS
    return (reviews / total) * rating + (MIN_REVIEWS / total) * GLOBAL_RATING


def _public_url(path: str) -> str:
    url = resolve_media_url(default_storage.url(path)) or ""
    if url.startswith("https//"):
        url = "https://" + url[len("https//") :]
    elif url.startswith("http//"):
        url = "http://" + url[len("http//") :]
    return url


class Command(BaseCommand):
    help = "Importa JSON del scrape de Medellín, sube fotos a R2 y actualiza la base."

    def add_arguments(self, parser):
        parser.add_argument("--input-dir", default="data/medellin-enrich")
        parser.add_argument("--limit", type=int, default=8)
        parser.add_argument("--place-id", default="", help="Procesar solo este place_id")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from django.conf import settings

        if not getattr(settings, "USE_R2", False):
            raise CommandError("R2 no está configurado en este entorno.")

        root = Path(options["input_dir"])
        if not root.is_absolute():
            root = Path(settings.BASE_DIR) / root
        if not root.is_dir():
            raise CommandError(f"No existe {root}")

        state_path = root / ".import-state.json"
        state = {}
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text())
            except json.JSONDecodeError:
                state = {}

        files = sorted(root.glob("ChIJ*.json"), key=lambda path: path.stat().st_mtime)
        only = (options["place_id"] or "").strip()
        if only:
            files = [path for path in files if path.stem == only or only in path.name]
        limit = max(1, int(options["limit"]))
        dry_run = bool(options["dry_run"])

        done = skipped = failed = 0
        for path in files:
            if done >= limit:
                break
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"json {path.name}: {exc}"))
                continue
            place_id = str(doc.get("place_id") or path.stem)
            saved_at = str(doc.get("saved_at") or "")
            previous = state.get(place_id) or {}
            if previous.get("saved_at") == saved_at and previous.get("status") in {
                "ok",
                "excluded",
                "empty",
                "gave_up",
            }:
                skipped += 1
                continue
            try:
                result = self._import_one(doc, dry_run=dry_run)
            except Exception as exc:
                failed += 1
                attempts = int(previous.get("attempts") or 0) + 1
                state[place_id] = {
                    "saved_at": saved_at,
                    "status": "gave_up" if attempts >= 3 else "error",
                    "attempts": attempts,
                    "error": str(exc)[:300],
                }
                self.stdout.write(self.style.ERROR(f"fail {place_id}: {exc}"))
                continue
            attempts = int(previous.get("attempts") or 0) + 1
            if result["status"] == "partial" and attempts >= 3:
                result["status"] = "ok"
            state[place_id] = {"saved_at": saved_at, "attempts": attempts, **result}
            done += 1
            campos = ",".join(result.get("campos") or []) or "-"
            self.stdout.write(
                f"{result['status']:9} {place_id} "
                f"public={int(result['public'])} "
                f"fotos_nuevas={result.get('fotos_nuevas', 0)} "
                f"fotos_ya={result.get('fotos_ya', 0)} "
                f"campos={campos} "
                f"sin_cambios={int(bool(result.get('sin_cambios')))} "
                f"slug={result.get('slug') or '-'}"
            )

        if not dry_run:
            state_path.write_text(json.dumps(state))
        self.stdout.write(
            self.style.SUCCESS(f"listos={done} saltados={skipped} fallos={failed}")
        )

    def _import_one(self, doc: dict, *, dry_run: bool) -> dict:
        data = doc.get("data") or {}
        overview = data.get("overview") or {}
        place_id = str(doc.get("place_id") or data.get("place_id") or "")
        if not place_id.startswith("ChIJ"):
            raise CommandError("place_id inválido")

        name = (overview.get("name") or data.get("name") or "")[:500]
        category = (overview.get("category_label") or overview.get("primary_type") or "")[:200]
        primary_raw = (overview.get("primary_type") or "")[:100]
        lat = overview.get("latitude") if overview.get("latitude") is not None else data.get("latitude")
        lng = overview.get("longitude") if overview.get("longitude") is not None else data.get("longitude")
        address = _clean_address(overview.get("formatted_address") or data.get("formatted_address") or "")
        phone = (overview.get("phone") or data.get("phone") or "")[:80]
        website = _http_url(overview.get("website_uri") or "")
        maps_url = _http_url(overview.get("page_url") or data.get("page_url") or "")
        rating = overview.get("rating") if overview.get("rating") is not None else data.get("rating")
        reviews = _as_int(overview.get("user_rating_count"))
        if reviews is None:
            reviews = _as_int(data.get("user_rating_count"))
        price = (overview.get("price_level") or "")[:50]
        hours_text, hours_json = _hours(overview.get("opening_hours"))
        ok = bool(doc.get("ok"))
        reason = str(doc.get("reason") or "")

        catalog = GooglePlaceId.objects.filter(place_id=place_id).first()
        classification = classify_place(
            maps_category=category or primary_raw,
            scan_types=list(getattr(catalog, "scan_types", None) or []) if catalog else [],
            search_queries=list(getattr(catalog, "search_queries", None) or []) if catalog else None,
        )
        tipo = classification.get("tipo") or "otros"
        if tipo not in VALID_TIPOS:
            tipo = "otros"
        excluded = _is_health(name, category, primary_raw, tipo) or tipo in HEALTH_TIPOS

        point = None
        if lat is not None and lng is not None:
            try:
                point = Point(float(lng), float(lat), srid=4326)
            except (TypeError, ValueError):
                point = None

        if dry_run:
            return {
                "status": "excluded" if excluded else ("ok" if ok else "empty"),
                "public": Places.objects.filter(place_id=place_id).exists(),
                "fotos": 0,
                "slug": "",
            }

        source_urls = _image_urls(data) if ok and not excluded else []
        foto_urls = self._store_photos(place_id, source_urls) if source_urls else []

        with transaction.atomic():
            self._save_details(
                place_id=place_id,
                catalog=catalog,
                name=name,
                category=category,
                classification=classification,
                tipo=tipo,
                lat=lat,
                lng=lng,
                point=point,
                address=address,
                phone=phone,
                website=website,
                maps_url=maps_url,
                rating=rating,
                reviews=reviews,
                price=price,
                hours_text=hours_text,
                hours_json=hours_json,
                ok=ok,
                reason=reason,
                excluded=excluded,
                foto_urls=foto_urls,
                saved_at=str(doc.get("saved_at") or ""),
            )
            place = Places.objects.filter(place_id=place_id).first()
            if place and ok and not excluded:
                change = self._refresh_place(
                    place,
                    name=name,
                    tipo=tipo,
                    address=address,
                    point=point,
                    rating=rating,
                    reviews=reviews,
                    phone=phone,
                    website=website,
                    maps_url=maps_url,
                    price=price,
                    hours_text=hours_text,
                    hours_json=hours_json,
                    foto_urls=foto_urls,
                )
            elif not place and ok and name:
                untouched = self._touch_pending(
                    place_id,
                    name=name,
                    tipos=classification.get("google_types") or [],
                    lat=lat,
                    lng=lng,
                    excluded=excluded,
                )
                change = {
                    "slug": "",
                    "campos": [] if untouched else ["pending"],
                    "fotos_nuevas": 0,
                    "fotos_ya": 0,
                    "sin_cambios": untouched,
                }
            else:
                change = {
                    "slug": (place.slug if place else "") or "",
                    "campos": [],
                    "fotos_nuevas": 0,
                    "fotos_ya": 0,
                    "sin_cambios": True,
                }

        status = "excluded" if excluded else ("ok" if ok else "empty")
        if source_urls and len(foto_urls) < len(source_urls):
            status = "partial"
        return {
            "status": status,
            "public": bool(place),
            "fotos": len(foto_urls),
            "fotos_nuevas": change["fotos_nuevas"],
            "fotos_ya": change["fotos_ya"],
            "campos": change["campos"],
            "sin_cambios": change["sin_cambios"],
            "slug": change["slug"],
        }

    def _store_photos(self, place_id: str, urls: list[str]) -> list[dict]:
        stored = []
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        for url in urls:
            digest = _photo_digest(url)
            original_key = f"images/{place_id}/g{digest}.webp"
            medium_key = f"tourism/images/medium/{place_id}/g{digest}.jpg"
            thumb_key = f"tourism/images/thumb/{place_id}/g{digest}.jpg"
            if all(default_storage.exists(key) for key in (original_key, medium_key, thumb_key)):
                stored.append(
                    {
                        "imagen": _public_url(original_key),
                        "imagen_mediana": _public_url(medium_key),
                        "imagen_miniatura": _public_url(thumb_key),
                        "digest": digest,
                    }
                )
                continue
            content = self._download(session, url)
            if not content:
                continue
            try:
                image = _ensure_rgb(Image.open(BytesIO(content)))
            except Exception:
                continue
            full = BytesIO()
            _fit_long_edge(image, 1600).save(full, format="WEBP", quality=75, method=4)
            medium = BytesIO()
            _fit_width(image, 800).save(medium, format="JPEG", quality=85, optimize=True)
            thumb = BytesIO()
            _fit_width(image, 220).save(thumb, format="JPEG", quality=80, optimize=True)
            default_storage.save(original_key, ContentFile(full.getvalue()))
            default_storage.save(medium_key, ContentFile(medium.getvalue()))
            default_storage.save(thumb_key, ContentFile(thumb.getvalue()))
            stored.append(
                {
                    "imagen": _public_url(original_key),
                    "imagen_mediana": _public_url(medium_key),
                    "imagen_miniatura": _public_url(thumb_key),
                    "digest": digest,
                }
            )
        return stored

    def _download(self, session: requests.Session, url: str) -> bytes:
        for candidate in (url, url.split("=", 1)[0]):
            try:
                response = session.get(candidate, timeout=25)
            except requests.RequestException:
                continue
            if response.status_code == 200 and len(response.content) > 800:
                return response.content
        return b""

    def _save_details(self, **item) -> None:
        classification = item["classification"]
        defaults = {
            "catalog_entry": item["catalog"],
            "display_name": item["name"],
            "category": item["category"],
            "primary_type": (classification.get("primary_type") or "")[:100],
            "tipo": item["tipo"],
            "tipo_family": classification.get("tipo_family") or "other",
            "tipo_source": classification.get("tipo_source") or "",
            "tipo_confidence": classification.get("tipo_confidence"),
            "types": classification.get("google_types") or [],
            "lat": item["lat"],
            "lng": item["lng"],
            "ubicacion": item["point"],
            "formatted_address": item["address"],
            "rating": item["rating"],
            "user_rating_count": item["reviews"],
            "phone": item["phone"],
            "website_uri": item["website"],
            "google_maps_uri": item["maps_url"],
            "price_level": item["price"][:10],
            "hours_text": item["hours_text"],
            "weekday_descriptions": item["hours_text"],
            "fetched_at": timezone.now(),
            "fetch_status": "ok" if item["ok"] else "error",
            "error_message": "excluido_salud" if item["excluded"] else item["reason"][:2000],
            "scraper_version": "medellin_gallery_v1",
            "photo_urls": [row["imagen"] for row in item["foto_urls"]] or None,
            "raw_json": {
                "saved_at": item["saved_at"],
                "excluded_health": item["excluded"],
                "fotos": len(item["foto_urls"]),
            },
        }
        current = GooglePlaceDetails.objects.filter(place_id=item["place_id"]).first()
        if current is None:
            GooglePlaceDetails.objects.create(place_id=item["place_id"], **defaults)
            return
        for field, value in defaults.items():
            if value in (None, "", [], {}) and field not in {"fetch_status", "fetched_at", "raw_json"}:
                continue
            setattr(current, field, value)
        current.save()

    def _touch_pending(
        self,
        place_id: str,
        *,
        name: str,
        tipos: list,
        lat,
        lng,
        excluded: bool,
    ) -> bool:
        """Actualiza PendingPlace solo si algo cambió. Devuelve True si quedó igual."""
        pending = PendingPlace.objects.filter(place_id=place_id).first()
        if pending is None:
            PendingPlace.objects.create(
                place_id=place_id,
                nombre=name[:255],
                tipos=tipos,
                lat=lat,
                lng=lng,
                status="skipped" if excluded else "pending",
                error_msg="salud" if excluded else "",
            )
            return False
        if pending.status == "processed":
            return True

        changed = False
        if name and not _text_same(pending.nombre, name[:255]):
            pending.nombre = name[:255]
            changed = True
        if tipos and list(pending.tipos or []) != list(tipos):
            pending.tipos = tipos
            changed = True
        if lat is not None and not _num_same(pending.lat, lat, tol=1e-5):
            pending.lat = lat
            changed = True
        if lng is not None and not _num_same(pending.lng, lng, tol=1e-5):
            pending.lng = lng
            changed = True
        if excluded and pending.status != "skipped":
            pending.status = "skipped"
            pending.error_msg = "salud"
            changed = True
        if changed:
            pending.save()
        return not changed

    def _refresh_place(self, place: Places, **item) -> dict:
        campos: list[str] = []
        if item["name"] and not _text_same(place.nombre, item["name"][:255]):
            place.nombre = item["name"][:255]
            campos.append("nombre")
        if item["address"] and not _text_same(place.direccion, item["address"]):
            place.direccion = item["address"]
            campos.append("direccion")
        if item["point"] is not None and not _point_same(place.ubicacion, item["point"]):
            place.ubicacion = item["point"]
            campos.append("ubicacion")
        rating_changed = item["rating"] is not None and not _num_same(place.rating, item["rating"])
        reviews_changed = item["reviews"] is not None and not _num_same(
            place.total_reviews, item["reviews"], tol=0.1
        )
        if rating_changed:
            place.rating = item["rating"]
            campos.append("rating")
        if reviews_changed:
            place.total_reviews = int(item["reviews"])
            campos.append("total_reviews")
        if rating_changed or reviews_changed:
            weighted = _weighted(place.rating, place.total_reviews)
            if weighted is not None and not _num_same(place.weighted_rating, weighted):
                place.weighted_rating = weighted
                campos.append("weighted_rating")
        if item["phone"] and not _text_same(place.telefono, item["phone"][:50]):
            place.telefono = item["phone"][:50]
            campos.append("telefono")
        if item["website"] and not _text_same(place.sitio_web, item["website"]):
            place.sitio_web = item["website"]
            campos.append("sitio_web")
        if item["maps_url"] and not _text_same(place.google_maps_uri, item["maps_url"]):
            place.google_maps_uri = item["maps_url"]
            campos.append("google_maps_uri")
        if item["price"] and not _text_same(place.precio, item["price"]):
            place.precio = item["price"]
            campos.append("precio")
        if item["hours_text"] and not _text_same(place.horario_texto, item["hours_text"]):
            place.horario_texto = item["hours_text"]
            campos.append("horario")
        if item["hours_json"] is not None and not _json_same(place.horario_json, item["hours_json"]):
            place.horario_json = item["hours_json"]
            if "horario" not in campos:
                campos.append("horario")
        if place.tipo in {"", "otros"} and item["tipo"] not in {"", "otros"} and place.tipo != item["tipo"]:
            place.tipo = item["tipo"]
            campos.append("tipo")

        existing = set(place.fotos.values_list("imagen", flat=True))
        created = 0
        repeated = 0
        for row in item["foto_urls"]:
            if _photo_already_stored(row["imagen"], row["digest"], existing):
                repeated += 1
                continue
            Foto.objects.create(
                lugar=place,
                imagen=row["imagen"][:1000],
                imagen_mediana=(row["imagen_mediana"] or "")[:1000] or None,
                imagen_miniatura=(row["imagen_miniatura"] or "")[:1000] or None,
                descripcion="google-maps",
            )
            existing.add(row["imagen"])
            created += 1
        if created:
            place.tiene_fotos = True
            place.imagenes_optimizadas = True
            campos.append("fotos")

        if campos:
            place.save()
        return {
            "slug": place.slug or "",
            "campos": campos,
            "fotos_nuevas": created,
            "fotos_ya": repeated,
            "sin_cambios": not campos,
        }
