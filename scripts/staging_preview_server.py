#!/usr/bin/env python3
"""
Preview LOCAL de GooglePlaceDetails (staging) sin GeoDjango/GDAL.

  DATABASE_URL=postgis://...@127.0.0.1:5433/colombia-osm \\
  .venv/bin/python scripts/staging_preview_server.py

Abre: http://127.0.0.1:8055/
"""

from __future__ import annotations

import html
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

HOST = "127.0.0.1"
PORT = int(os.environ.get("STAGING_PREVIEW_PORT", "8055"))


def db_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip().strip("'").strip('"')
    if not url:
        p = "/tmp/vive_db_tunnel.url"
        if os.path.exists(p):
            url = open(p, encoding="utf-8").read().strip()
    if not url:
        raise SystemExit("Falta DATABASE_URL o /tmp/vive_db_tunnel.url")
    if "@127.0.0.1:5432/" in url:
        url = url.replace("@127.0.0.1:5432/", "@127.0.0.1:5433/")
    return url


def connect():
    u = urlparse(db_url().replace("postgis://", "postgresql://", 1))
    return psycopg2.connect(
        dbname=u.path.lstrip("/"),
        user=unquote(u.username or ""),
        password=unquote(u.password or ""),
        host=u.hostname or "127.0.0.1",
        port=u.port or 5432,
    )


CSS = """
:root{--bg:#0f1419;--card:#1a222c;--text:#e8eef4;--muted:#8b9aab;--acc:#3d9cf0;--ok:#3ecf8e;--warn:#f0b429}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--text)}
header{padding:1.2rem 1.5rem;border-bottom:1px solid #2a3542}a{color:var(--acc);text-decoration:none}
.badge{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.75rem;background:#2a3542;color:var(--warn)}
.badge.new{background:#1a3a2a;color:var(--ok)}.badge.old{background:#3a2a1a;color:var(--warn)}
main{max-width:1100px;margin:0 auto;padding:1.2rem 1.5rem 3rem}
form{display:flex;flex-wrap:wrap;gap:.7rem;margin-bottom:1rem;align-items:end}
label{display:flex;flex-direction:column;gap:.25rem;font-size:.8rem;color:var(--muted)}
input,select{background:var(--card);border:1px solid #2a3542;color:var(--text);padding:.45rem .6rem;border-radius:6px}
button,.btn{background:var(--acc);color:#fff;border:0;padding:.5rem .9rem;border-radius:6px;cursor:pointer}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:.55rem .5rem;border-bottom:1px solid #2a3542;vertical-align:top}
th{color:var(--muted);font-size:.75rem;text-transform:uppercase}
.tag{font-size:.72rem;padding:.12rem .4rem;border-radius:4px;background:#243040;color:#9ec5ea}
section{background:var(--card);border-radius:10px;padding:1rem;margin-bottom:1rem}
dl{display:grid;grid-template-columns:160px 1fr;gap:.35rem .75rem;margin:0;font-size:.92rem}
dt{color:var(--muted)}dd{margin:0;word-break:break-word}
.photos{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:.5rem}
.photos img{width:100%;height:110px;object-fit:cover;border-radius:8px;background:#111}
.amen span{background:#243040;padding:.2rem .5rem;border-radius:4px;font-size:.8rem;margin:.2rem;display:inline-block}
.review{border-top:1px solid #2a3542;padding:.65rem 0;font-size:.88rem;color:#c5d0db}
pre{overflow:auto;max-height:320px;background:#11161c;padding:.75rem;border-radius:8px;font-size:.75rem;color:#9ec5ea}
.pager{margin-top:1rem;display:flex;gap:1rem;align-items:center;color:var(--muted)}
"""


def page(title: str, body: str) -> bytes:
    doc = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body>{body}</body></html>"""
    return doc.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        try:
            if path == "/":
                self._list(qs)
            elif path.startswith("/d/"):
                self._detail(unquote(path[3:]))
            else:
                self._send(404, page("404", "<main><p>No encontrado</p><a href='/'>Inicio</a></main>"))
        except Exception as exc:
            self._send(500, page("Error", f"<main><pre>{html.escape(str(exc))}</pre></main>"))

    def _list(self, qs):
        q = (qs.get("q") or [""])[0].strip()
        family = (qs.get("family") or [""])[0].strip()
        only_new = (qs.get("only_new") or [""])[0] == "1"
        try:
            page_n = max(1, int((qs.get("page") or ["1"])[0]))
        except ValueError:
            page_n = 1
        per = 40
        offset = (page_n - 1) * per

        where = ["d.fetch_status = 'ok'"]
        params: list = []
        if family:
            where.append("d.tipo_family = %s")
            params.append(family)
        if q:
            where.append(
                "(d.display_name ILIKE %s OR d.place_id ILIKE %s OR d.category ILIKE %s OR d.formatted_address ILIKE %s)"
            )
            like = f"%{q}%"
            params.extend([like, like, like, like])
        if only_new:
            where.append(
                "NOT EXISTS (SELECT 1 FROM explorer_places p WHERE p.place_id = d.place_id)"
            )
        wh = " AND ".join(where)

        with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM explorer_googleplacedetails d WHERE {wh}", params)
            total = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM explorer_googleplacedetails WHERE fetch_status='ok'")
            total_ok = cur.fetchone()["n"]
            cur.execute(
                f"""
                SELECT d.place_id, d.display_name, d.tipo_family, d.tipo, d.category,
                       d.rating, d.user_rating_count, d.fetched_at,
                       EXISTS(SELECT 1 FROM explorer_places p WHERE p.place_id=d.place_id) AS in_places
                FROM explorer_googleplacedetails d
                WHERE {wh}
                ORDER BY d.fetched_at DESC NULLS LAST
                LIMIT %s OFFSET %s
                """,
                params + [per, offset],
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT DISTINCT tipo_family FROM explorer_googleplacedetails WHERE fetch_status='ok' AND tipo_family<>'' ORDER BY 1"
            )
            families = [r["tipo_family"] for r in cur.fetchall()]

        pages = max(1, (total + per - 1) // per)
        opts = "".join(
            f'<option value="{html.escape(f)}"{" selected" if f==family else ""}>{html.escape(f)}</option>'
            for f in families
        )
        trs = []
        for r in rows:
            name = html.escape(r["display_name"] or r["place_id"])
            badge = (
                '<span class="badge old">ya en Places</span>'
                if r["in_places"]
                else '<span class="badge new">solo staging</span>'
            )
            rating = "—"
            if r["rating"] is not None:
                rating = str(r["rating"])
                if r["user_rating_count"]:
                    rating += f" ({r['user_rating_count']})"
            fetched = r["fetched_at"].strftime("%Y-%m-%d %H:%M") if r["fetched_at"] else "—"
            trs.append(
                f"<tr><td><a href='/d/{html.escape(r['place_id'])}'>{name}</a>"
                f"<div style='color:var(--muted);font-size:.75rem'>{html.escape(r['place_id'])}</div></td>"
                f"<td><span class='tag'>{html.escape(r['tipo_family'] or '')}</span> {html.escape(r['tipo'] or '')}</td>"
                f"<td>{html.escape(r['category'] or '—')}</td><td>{html.escape(rating)}</td>"
                f"<td>{badge}</td><td style='color:var(--muted);font-size:.8rem'>{fetched}</td></tr>"
            )

        q_enc = html.escape(q)
        prev = (
            f"<a class='btn' href='/?page={page_n-1}&q={q_enc}&family={html.escape(family)}{'&only_new=1' if only_new else ''}'>← Anterior</a>"
            if page_n > 1
            else ""
        )
        nxt = (
            f"<a class='btn' href='/?page={page_n+1}&q={q_enc}&family={html.escape(family)}{'&only_new=1' if only_new else ''}'>Siguiente →</a>"
            if page_n < pages
            else ""
        )
        body = f"""
<header><h1 style="margin:0 0 .35rem;font-size:1.25rem">Staging local — GooglePlaceDetails</h1>
<p style="margin:0;color:var(--muted);font-size:.9rem">Solo localhost:{PORT}. Separado de Places. <span class="badge">LOCAL</span></p></header>
<main>
<div style="color:var(--muted);margin-bottom:1rem">Total OK: <strong>{total_ok}</strong> · filtrados: {total}</div>
<form method="get">
<label>Buscar<input name="q" value="{q_enc}" placeholder="nombre, place_id…"></label>
<label>Familia<select name="family"><option value="">(todas)</option>{opts}</select></label>
<label style="flex-direction:row;align-items:center;gap:.4rem;margin-top:1.1rem">
<input type="checkbox" name="only_new" value="1" {"checked" if only_new else ""}> Solo nuevos (sin Places)</label>
<button type="submit">Filtrar</button>
</form>
<table><thead><tr><th>Nombre</th><th>Familia</th><th>Categoría</th><th>Rating</th><th>Estado</th><th>Fetched</th></tr></thead>
<tbody>{''.join(trs) or '<tr><td colspan=6>Sin resultados</td></tr>'}</tbody></table>
<div class="pager">{prev}<span>Pág. {page_n}/{pages}</span>{nxt}</div>
</main>"""
        self._send(200, page("Staging local", body))

    def _detail(self, place_id: str):
        with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM explorer_googleplacedetails WHERE place_id=%s",
                (place_id,),
            )
            obj = cur.fetchone()
            if not obj:
                self._send(404, page("404", "<main><p>No encontrado</p><a href='/'>Volver</a></main>"))
                return
            cur.execute(
                "SELECT nombre, slug, tipo FROM explorer_places WHERE place_id=%s LIMIT 1",
                (place_id,),
            )
            place = cur.fetchone()

        photos = obj.get("photo_urls") if isinstance(obj.get("photo_urls"), list) else []
        reviews = obj.get("reviews") if isinstance(obj.get("reviews"), list) else []
        amenities = obj.get("amenities") if isinstance(obj.get("amenities"), dict) else {}
        amen_html = "".join(
            f"<span>{html.escape(str(k))}</span>" for k, v in amenities.items() if v
        ) or "<span style='color:var(--muted)'>Sin amenities</span>"
        photos_html = "".join(
            f'<a href="{html.escape(u)}" target="_blank" rel="noopener"><img src="{html.escape(u)}" loading="lazy"></a>'
            for u in photos[:24]
        ) or "<p style='color:var(--muted)'>Sin fotos</p>"
        rev_html = "".join(
            f"<div class='review'>{html.escape((r.get('text') if isinstance(r, dict) else str(r)) or '')}</div>"
            for r in reviews[:15]
        ) or "<p style='color:var(--muted)'>Sin reseñas</p>"
        try:
            raw = json.dumps(obj.get("raw_json"), ensure_ascii=False, indent=2)[:20000]
        except Exception:
            raw = str(obj.get("raw_json"))[:20000]

        badge = (
            '<span class="badge old">también en Places</span>'
            if place
            else '<span class="badge new">solo staging</span>'
        )
        places_block = ""
        if place:
            places_block = f"""<section><h2>Places (público)</h2><dl>
            <dt>nombre</dt><dd>{html.escape(place['nombre'] or '')}</dd>
            <dt>slug</dt><dd>{html.escape(place['slug'] or '')}</dd>
            <dt>tipo</dt><dd>{html.escape(place['tipo'] or '')}</dd></dl></section>"""

        def v(key, default="—"):
            val = obj.get(key)
            if val in (None, ""):
                return default
            return html.escape(str(val))

        body = f"""
<header><a href="/">← Listado</a> {badge}
<h1 style="margin:.5rem 0 .25rem;font-size:1.5rem">{html.escape(obj.get('display_name') or '(sin nombre)')}</h1>
<p style="color:var(--muted)">{v('category')} · {v('tipo_family')} / {v('tipo')}
{" · ★ "+v('rating') if obj.get('rating') is not None else ''}
{" · "+v('price_level') if obj.get('price_level') else ''}</p></header>
<main>
<section><h2>Identidad</h2><dl>
<dt>place_id</dt><dd><code>{v('place_id')}</code></dd>
<dt>primary_type</dt><dd>{v('primary_type')}</dd>
<dt>scraper</dt><dd>{v('scraper_version')} · {v('fetch_status')} · {v('fetched_at')}</dd>
</dl></section>
<section><h2>Contacto</h2><dl>
<dt>Dirección</dt><dd>{v('formatted_address')}</dd>
<dt>Coords</dt><dd>{v('lat')}, {v('lng')}</dd>
<dt>Tel</dt><dd>{v('phone')}</dd>
<dt>Web</dt><dd>{v('website_uri')}</dd>
<dt>Maps</dt><dd>{('<a href=\"%s\" target=_blank>Abrir</a>'%html.escape(obj['google_maps_uri'])) if obj.get('google_maps_uri') else '—'}</dd>
</dl></section>
<section><h2>Horario</h2><dl>
<dt>open_now</dt><dd>{v('open_now')}</dd>
<dt>hours</dt><dd>{v('hours_text')}</dd>
<dt>semanal</dt><dd><pre style="white-space:pre-wrap;margin:0">{v('weekday_descriptions')}</pre></dd>
</dl></section>
<section><h2>Descripción</h2><p>{v('description')}</p></section>
<section><h2>Amenities</h2><div class="amen">{amen_html}</div></section>
<section><h2>Fotos</h2>
<p style="color:var(--muted)">Plan 1 no guarda imágenes. Fase 2 scrapea media solo de seleccionados.</p></section>
<section><h2>Reseñas ({len(reviews)})</h2>{rev_html}</section>
{places_block}
<section><h2>raw_json</h2><pre>{html.escape(raw)}</pre></section>
</main>"""
        self._send(200, page(obj.get("display_name") or place_id, body))


def main():
    # Solo bind localhost
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Staging preview → http://{HOST}:{PORT}/  (Ctrl+C para salir)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
