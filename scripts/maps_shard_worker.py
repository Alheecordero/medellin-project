#!/usr/bin/env python3
"""
Worker de shard: Playwright Maps → Postgres prod (túnel), sin Places API.

Uso en VPS:
  DATABASE_URL=postgis://...@127.0.0.1:5433/colombia-osm \\
  PYTHONPATH=/root/medellin-project \\
  /root/UK/venv/bin/python scripts/maps_shard_worker.py \\
    --shard-index 0 --shard-count 4 --pause 2
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg2
from psycopg2.extras import Json

from explorer.scraping.maps_place_overview import SCRAPER_VERSION, scrape_place_overview
from explorer.utils.place_classify import classify_place


def _parse_db_url(url: str) -> dict:
    url = url.strip().strip("'").strip('"')
    if url.startswith("postgis://"):
        url = "postgresql://" + url[len("postgis://") :]
    elif url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    u = urlparse(url)
    return {
        "dbname": (u.path or "/").lstrip("/") or "postgres",
        "user": unquote(u.username or ""),
        "password": unquote(u.password or ""),
        "host": u.hostname or "127.0.0.1",
        "port": u.port or 5432,
    }


def connect():
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        raise SystemExit("Falta DATABASE_URL")
    return psycopg2.connect(**_parse_db_url(raw))


def fetch_batch(conn, *, shard_index: int, shard_count: int, limit: int) -> list[dict]:
    """IDs sin details OK, partición por hash MD5 estable."""
    sql = """
        SELECT g.place_id, g.scan_types, g.search_queries
        FROM explorer_googleplaceid g
        WHERE NOT EXISTS (
            SELECT 1 FROM explorer_googleplacedetails d
            WHERE d.place_id = g.place_id AND d.fetch_status = 'ok'
        )
          AND mod(('x' || substr(md5(g.place_id), 1, 8))::bit(32)::int, %s) = %s
        ORDER BY g.place_id
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (shard_count, shard_index, limit))
        rows = cur.fetchall()
    out = []
    for place_id, scan_types, search_queries in rows:
        out.append(
            {
                "place_id": place_id,
                "scan_types": list(scan_types or []),
                "search_queries": list(search_queries or []),
            }
        )
    return out


def upsert(conn, place_id: str, result: dict, catalog: dict) -> None:
    data = result.get("data") or {}
    status = result.get("status") or "error"
    classification = classify_place(
        maps_category=data.get("category"),
        scan_types=catalog.get("scan_types") or [],
        search_queries=catalog.get("search_queries") or None,
        body_snippet=data.get("body_snippet"),
    )

    review_count = data.get("review_count")
    if isinstance(review_count, str):
        digits = "".join(c for c in review_count if c.isdigit())
        review_count = int(digits) if digits else None

    def clean_url(val: str | None) -> str:
        val = (val or "")[:1000]
        if val.startswith("http://") or val.startswith("https://"):
            return val
        return ""

    lat, lng = data.get("lat"), data.get("lng")
    now = datetime.now(timezone.utc)
    raw = {
        "scraped_at": now.isoformat(),
        "result_status": status,
        "final_url": result.get("final_url"),
        "classification": classification,
        "data": data,
    }

    # catalog FK
    catalog_id = None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM explorer_googleplaceid WHERE place_id = %s", (place_id,)
        )
        row = cur.fetchone()
        if row:
            catalog_id = row[0]

    fields = {
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
        "formatted_address": data.get("address") or "",
        "plus_code": (data.get("plus_code") or "")[:120],
        "lat": lat,
        "lng": lng,
        "rating": data.get("rating"),
        "user_rating_count": review_count,
        "phone": (data.get("phone") or "")[:80],
        "website_uri": clean_url(data.get("website")),
        "google_maps_uri": clean_url(result.get("final_url") or data.get("page_url")),
        "menu_uri": clean_url(data.get("menu_uri")),
        "open_now": data.get("open_now"),
        "hours_text": data.get("hours_text") or "",
        "dine_in": data.get("dine_in"),
        "takeout": data.get("takeout"),
        "delivery": data.get("delivery"),
        "amenities": Json(data.get("amenities")) if data.get("amenities") else None,
        "reviews": Json(data.get("reviews")) if data.get("reviews") else None,
        "photo_urls": Json(data.get("photo_urls")) if data.get("photo_urls") else None,
        "fetched_at": now,
        "fetch_status": status,
        "error_message": (result.get("error") or "")[:2000],
        "scraper_version": result.get("scraper_version") or SCRAPER_VERSION,
        "raw_json": Json(raw),
        "updated_at": now,
    }

    cols = list(fields.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)

    sql = f"""
        INSERT INTO explorer_googleplacedetails
            (place_id, created_at, {", ".join(cols)})
        VALUES
            (%s, %s, {placeholders})
        ON CONFLICT (place_id) DO UPDATE SET {updates}
    """
    values = [place_id, now] + [fields[c] for c in cols]
    # ArrayField types
    with conn.cursor() as cur:
        # psycopg2 adapts list→array for text[]
        cur.execute(sql, values)
        if lat is not None and lng is not None:
            cur.execute(
                """
                UPDATE explorer_googleplacedetails
                SET ubicacion = ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                WHERE place_id = %s
                """,
                (float(lng), float(lat), place_id),
            )
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard-index", type=int, required=True)
    ap.add_argument("--shard-count", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=25)
    ap.add_argument("--pause", type=float, default=2.0)
    ap.add_argument("--max-jobs", type=int, default=0, help="0 = hasta vaciar cola del shard")
    ap.add_argument("--chrome", default="/usr/bin/google-chrome")
    ap.add_argument("--wait-ms", type=int, default=8000)
    args = ap.parse_args()

    shard = args.shard_index
    print(
        f"[shard {shard}/{args.shard_count}] start scraper_version={SCRAPER_VERSION}",
        flush=True,
    )
    conn = connect()
    done = ok = err = blocked = 0
    consecutive_empty = 0

    while True:
        if args.max_jobs and done >= args.max_jobs:
            break
        limit = args.batch_size
        if args.max_jobs:
            limit = min(limit, args.max_jobs - done)
        batch = fetch_batch(
            conn, shard_index=shard, shard_count=args.shard_count, limit=limit
        )
        if not batch:
            consecutive_empty += 1
            print(f"[shard {shard}] cola vacía ({consecutive_empty})", flush=True)
            if consecutive_empty >= 3:
                break
            time.sleep(30)
            continue
        consecutive_empty = 0

        for item in batch:
            place_id = item["place_id"]
            t0 = time.time()
            result = scrape_place_overview(
                place_id,
                headless=True,
                chrome_path=args.chrome,
                wait_ms=args.wait_ms,
            )
            status = result.get("status") or "error"
            try:
                upsert(conn, place_id, result, item)
            except Exception as exc:
                conn.rollback()
                print(f"[shard {shard}] DB_ERR {place_id}: {exc}", flush=True)
                err += 1
                done += 1
                continue

            name = ((result.get("data") or {}).get("name") or "")[:36]
            elapsed = time.time() - t0
            print(
                f"[shard {shard}] {status:9} {elapsed:5.1f}s {place_id[:24]} {name}",
                flush=True,
            )
            done += 1
            if status == "ok":
                ok += 1
            elif status == "blocked":
                blocked += 1
                print(f"[shard {shard}] BLOQUEO — paro shard", flush=True)
                print(f"[shard {shard}] fin ok={ok} err={err} blocked={blocked}", flush=True)
                return
            else:
                err += 1

            if args.pause > 0:
                time.sleep(args.pause)

    print(f"[shard {shard}] fin ok={ok} err={err} blocked={blocked} done={done}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
