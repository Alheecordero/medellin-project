#!/usr/bin/env python3
"""Piloto E2E en VPS scraper: Playwright Maps → JSON (sin Django/GIS)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Reutiliza el extractor del repo si está en PYTHONPATH
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from explorer.scraping.maps_place_overview import scrape_place_overview  # noqa: E402


def main() -> None:
    place_ids = sys.argv[1:]
    if not place_ids:
        place_ids = ["ChIJiQ_2Y2QpRI4ROY3iu_Mx75o"]
    out = []
    for pid in place_ids:
        print(f"SCRAPE {pid} …", file=sys.stderr)
        result = scrape_place_overview(pid, headless=True, wait_ms=8000)
        out.append(result)
        st = result.get("status")
        name = (result.get("data") or {}).get("name") or ""
        print(f"  → {st} {name}", file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
