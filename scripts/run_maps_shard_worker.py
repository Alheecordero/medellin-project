#!/usr/bin/env python3
"""
Worker de shard: Playwright Maps ($0 API) → Postgres prod vía túnel.

Uso en VPS 89.167.92.76:
  PYTHONPATH=/root/medellin-project \\
  DATABASE_URL=postgis://...@127.0.0.1:5433/colombia-osm \\
  /root/UK/venv/bin/python scripts/run_maps_shard_worker.py \\
    --shard-index 0 --shard-count 4 --pause 2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg2
from psycopg2.extras import Json

from explorer.scraping.maps_place_overview import SCRAPER_VERSION, scrape_place_overview


def _load_classify():
    """Importa place_classify sin arrancar GeoDjango."""
    import importlib.util
    import types

    # PLACE_TYPE_CHOICES mínimo desde models (solo la tupla)
    models_mod = types.ModuleType("explorer.models")
    text = (ROOT / "explorer/models.py").read_text(encoding="utf-8")
    start = text.index("PLACE_TYPE_CHOICES = (")
    end = text.index("\n)", start) + 2
    ns: dict = {}
    exec(text[start:end], ns)
    models_mod.PLACE_TYPE_CHOICES = ns["PLACE_TYPE_CHOICES"]

    vive = types.ModuleType("explorer.utils.vive_areas")
    spec_v = importlib.util.spec_from_file_location(
        "explorer.utils.vive_areas", ROOT / "explorer/utils/vive_areas.py"
    )
    assert spec_v and spec_v.loader
    spec_v.loader.exec_module(vive)

    explorer = types.ModuleType("explorer")
    explorer_utils = types.ModuleType("explorer.utils")
    sys.modules["explorer"] = explorer
    sys.modules["explorer.utils"] = explorer_utils
    sys.modules["explorer.models"] = models_mod
    sys.modules["explorer.utils.vive_areas"] = vive

    spec = importlib.util.spec_from_file_location(
        "place_classify", ROOT / "explorer/utils/place_classify.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.classify_place


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip().strip("'").strip('"')
    if not url:
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip("'").strip('"')
                    break
    if not url:
        raise SystemExit("Falta DATABASE_URL")
    # Asegurar túnel :5433 si viene :5432 local
    if "@127.0.0.1:5432/" in url or "@localhost:5432/" in url:
        url = url.replace("@127.0.0.1:5432/", "@127.0.0.1:5433/").replace(
            "@localhost:5432/", "@127.0.0.1:5433/"
        )
    return url


def _connect(url: str):
    u = urlparse(url.replace("postgis://", "postgresql://", 1))
    return psycopg2.connect(
        dbname=u.path.lstrip("/"),
        user=unquote(u.username or ""),
        password=unquote(u.password or ""),
        host=u.hostname or "127.0.0.1",
        port=u.port or 5432,
    )


def _shard_ok(place_id: str, shard_index: int, shard_count: int) -> bool:
    h = int(hashlib.md5(place_id.encode()).hexdigest(), 16)
    return h % shard_count == shard_index


def fetch_queue(conn, *, shard_index: int, shard_count: int, limit: int) -> list[tuple]:
    """Devuelve (place_id, scan_types, search_queries) pendientes de este shard."""
    with conn.cursor() as cur:
        # Filtrar shard en SQL (md5) para no quedarnos cortos con un LIMIT chico
        # sobre place_id ordenados (bug que hacía “cola vacía” con decenas de miles pendientes).
        cur.execute(
            """
            SELECT g.place_id, g.scan_types, g.search_queries
            FROM explorer_googleplaceid g
            WHERE NOT EXISTS (
              SELECT 1 FROM explorer_googleplacedetails d
              WHERE d.place_id = g.place_id AND d.fetch_status = 'ok'
            )
              AND mod(
                abs(('x' || substr(md5(g.place_id), 1, 8))::bit(32)::bigint),
                %s
              ) = %s
            ORDER BY g.place_id
            LIMIT %s
            """,
            (shard_count, shard_index, limit),
        )
        rows = cur.fetchall()
    return [(r[0], r[1] or [], r[2] or []) for r in rows]


def upsert(conn, place_id: str, result: dict, classify_place, scan_types, search_queries):
    data = result.get("data") or {}
    status = result.get("status") or "error"
    classification = classify_place(
        maps_category=data.get("category"),
        scan_types=list(scan_types or []),
        search_queries=list(search_queries or []),
        body_snippet=data.get("body_snippet"),
    )
    now = datetime.now(timezone.utc)
    lat, lng = data.get("lat"), data.get("lng")
    review_count = data.get("review_count")
    if isinstance(review_count, str):
        digits = "".join(c for c in review_count if c.isdigit())
        review_count = int(digits) if digits else None

    def url_or_empty(v):
        v = (v or "")[:1000]
        if v.startswith("http://") or v.startswith("https://"):
            return v
        return ""

    raw = {
        "scraped_at": now.isoformat(),
        "result_status": status,
        "final_url": result.get("final_url"),
        "classification": classification,
        # Sin photo_urls: fase 2 scrapea media solo de seleccionados
        "data": {k: v for k, v in data.items() if k != "photo_urls"},
    }

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM explorer_googleplaceid WHERE place_id = %s", (place_id,)
        )
        row = cur.fetchone()
        catalog_id = row[0] if row else None

        cur.execute(
            """
            INSERT INTO explorer_googleplacedetails (
              place_id, catalog_entry_id, cid, display_name, category,
              primary_type, tipo, tipo_family, tipo_source, tipo_confidence, types,
              business_status, lat, lng, ubicacion, formatted_address, plus_code,
              rating, user_rating_count, phone, website_uri, google_maps_uri, menu_uri,
              price_level, description,
              open_now, hours_text, weekday_descriptions,
              dine_in, takeout, delivery, amenities, reviews, photo_urls, photos_meta,
              fetched_at, fetch_status, error_message, scraper_version, raw_json,
              created_at, updated_at
            ) VALUES (
              %(place_id)s, %(catalog_entry_id)s, %(cid)s, %(display_name)s, %(category)s,
              %(primary_type)s, %(tipo)s, %(tipo_family)s, %(tipo_source)s, %(tipo_confidence)s, %(types)s,
              '', %(lat)s, %(lng)s,
              CASE WHEN %(lng)s IS NOT NULL AND %(lat)s IS NOT NULL
                THEN ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography
                ELSE NULL END,
              %(formatted_address)s, %(plus_code)s,
              %(rating)s, %(user_rating_count)s, %(phone)s, %(website_uri)s, %(google_maps_uri)s, %(menu_uri)s,
              %(price_level)s, %(description)s,
              %(open_now)s, %(hours_text)s, %(weekday_descriptions)s,
              %(dine_in)s, %(takeout)s, %(delivery)s, %(amenities)s, %(reviews)s, %(photo_urls)s, NULL,
              %(fetched_at)s, %(fetch_status)s, %(error_message)s, %(scraper_version)s, %(raw_json)s,
              %(fetched_at)s, %(fetched_at)s
            )
            ON CONFLICT (place_id) DO UPDATE SET
              catalog_entry_id = EXCLUDED.catalog_entry_id,
              cid = EXCLUDED.cid,
              display_name = EXCLUDED.display_name,
              category = EXCLUDED.category,
              primary_type = EXCLUDED.primary_type,
              tipo = EXCLUDED.tipo,
              tipo_family = EXCLUDED.tipo_family,
              tipo_source = EXCLUDED.tipo_source,
              tipo_confidence = EXCLUDED.tipo_confidence,
              types = EXCLUDED.types,
              lat = EXCLUDED.lat,
              lng = EXCLUDED.lng,
              ubicacion = EXCLUDED.ubicacion,
              formatted_address = EXCLUDED.formatted_address,
              plus_code = EXCLUDED.plus_code,
              rating = EXCLUDED.rating,
              user_rating_count = EXCLUDED.user_rating_count,
              phone = EXCLUDED.phone,
              website_uri = EXCLUDED.website_uri,
              google_maps_uri = EXCLUDED.google_maps_uri,
              menu_uri = EXCLUDED.menu_uri,
              price_level = EXCLUDED.price_level,
              description = EXCLUDED.description,
              open_now = EXCLUDED.open_now,
              hours_text = EXCLUDED.hours_text,
              weekday_descriptions = EXCLUDED.weekday_descriptions,
              dine_in = EXCLUDED.dine_in,
              takeout = EXCLUDED.takeout,
              delivery = EXCLUDED.delivery,
              amenities = EXCLUDED.amenities,
              reviews = EXCLUDED.reviews,
              photo_urls = EXCLUDED.photo_urls,
              fetched_at = EXCLUDED.fetched_at,
              fetch_status = EXCLUDED.fetch_status,
              error_message = EXCLUDED.error_message,
              scraper_version = EXCLUDED.scraper_version,
              raw_json = EXCLUDED.raw_json,
              updated_at = EXCLUDED.updated_at
            """,
            {
                "place_id": place_id,
                "catalog_entry_id": catalog_id,
                "cid": (data.get("cid") or "")[:80],
                "display_name": (data.get("name") or "")[:500],
                "category": (data.get("category") or "")[:200],
                "primary_type": (classification.get("primary_type") or "")[:100],
                "tipo": classification.get("tipo") or "otros",
                "tipo_family": classification.get("tipo_family") or "other",
                "tipo_source": classification.get("tipo_source") or "",
                "tipo_confidence": classification.get("tipo_confidence"),
                "types": classification.get("google_types") or [],
                "lat": lat,
                "lng": lng,
                "formatted_address": data.get("address") or "",
                "plus_code": (data.get("plus_code") or "")[:120],
                "rating": data.get("rating"),
                "user_rating_count": review_count,
                "phone": (data.get("phone") or "")[:80],
                "website_uri": url_or_empty(data.get("website")),
                "google_maps_uri": url_or_empty(
                    result.get("final_url") or data.get("page_url")
                ),
                "menu_uri": url_or_empty(data.get("menu_uri")),
                "price_level": (data.get("price_level") or "")[:10],
                "description": (data.get("description") or "")[:5000],
                "open_now": data.get("open_now"),
                "hours_text": data.get("hours_text") or "",
                "weekday_descriptions": data.get("weekday_descriptions") or "",
                "dine_in": data.get("dine_in"),
                "takeout": data.get("takeout"),
                "delivery": data.get("delivery"),
                "amenities": Json(data.get("amenities")) if data.get("amenities") else None,
                "reviews": Json(data.get("reviews")) if data.get("reviews") else None,
                "photo_urls": None,
                "fetched_at": now,
                "fetch_status": status,
                "error_message": (result.get("error") or "")[:2000],
                "scraper_version": result.get("scraper_version") or SCRAPER_VERSION,
                "raw_json": Json(raw),
            },
        )
    conn.commit()
    return classification


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard-index", type=int, required=True)
    ap.add_argument("--shard-count", type=int, default=4)
    ap.add_argument("--batch", type=int, default=50, help="IDs a pedir por ronda")
    ap.add_argument("--pause", type=float, default=2.0)
    ap.add_argument("--wait-ms", type=int, default=7000)
    ap.add_argument("--max-jobs", type=int, default=0, help="0 = hasta vaciar/cola")
    ap.add_argument("--log-dir", default="/root/medellin-project/data/maps_shards")
    args = ap.parse_args()

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"shard_{args.shard_index}.log"

    def log(msg: str) -> None:
        line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    classify_place = _load_classify()
    conn = _connect(_db_url())
    log(
        f"start shard={args.shard_index}/{args.shard_count} pause={args.pause}s "
        f"scraper={SCRAPER_VERSION}"
    )

    done = ok = err = blocked = 0
    consecutive_empty = 0
    try:
        while True:
            if args.max_jobs and done >= args.max_jobs:
                break
            need = args.batch
            if args.max_jobs:
                need = min(need, args.max_jobs - done)
            queue = fetch_queue(
                conn,
                shard_index=args.shard_index,
                shard_count=args.shard_count,
                limit=need,
            )
            if not queue:
                consecutive_empty += 1
                log(f"cola vacía ({consecutive_empty})")
                if consecutive_empty >= 3:
                    break
                time.sleep(30)
                continue
            consecutive_empty = 0

            for place_id, scan_types, search_queries in queue:
                if args.max_jobs and done >= args.max_jobs:
                    break
                t0 = time.time()
                try:
                    result = scrape_place_overview(
                        place_id, headless=True, wait_ms=args.wait_ms
                    )
                    classification = upsert(
                        conn, place_id, result, classify_place, scan_types, search_queries
                    )
                    status = result.get("status")
                    name = ((result.get("data") or {}).get("name") or "")[:36]
                    fam = classification.get("tipo_family") or ""
                    elapsed = time.time() - t0
                    log(
                        f"[{done+1}] {status:9} {elapsed:5.1f}s {fam:14} "
                        f"{place_id[:22]} {name}"
                    )
                    if status == "ok":
                        ok += 1
                    elif status == "blocked":
                        blocked += 1
                        log("BLOCKED — parado shard")
                        return
                    else:
                        err += 1
                except Exception as exc:
                    err += 1
                    conn.rollback()
                    log(f"EXC {place_id}: {exc}")
                    log(traceback.format_exc().splitlines()[-3])
                done += 1
                if args.pause > 0:
                    time.sleep(args.pause)
    finally:
        conn.close()
        log(f"end done={done} ok={ok} err={err} blocked={blocked}")


if __name__ == "__main__":
    main()
