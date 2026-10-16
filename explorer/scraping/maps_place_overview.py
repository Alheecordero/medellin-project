"""
Extractor gratis de ficha Google Maps vía Playwright (sin Places API).

maps_v3: overview + pestaña Acerca de + horarios expandidos + más
atributos / precio / descripción / reseñas. Sin descargar fotos.
"""

from __future__ import annotations

import re
import time
from typing import Any

SCRAPER_VERSION = "maps_v3"

EXTRACT_JS = r"""
(args) -> {
  const maxPhotos = (args && args[0]) || 20;
  const maxReviews = (args && args[1]) || 10;
  const stripIcons = (s) => String(s || "").replace(/[\uE000-\uF8FF]/g, "").replace(/\s+/g, " ").trim();
  const text = (el) => stripIcons(el && (el.innerText || el.textContent) || "");
  const q = (s) => document.querySelector(s);
  const qa = (s) => Array.from(document.querySelectorAll(s));
  const href = location.href;

  const UI_NOISE = /^(restaurantes cercanos|hoteles|cosas que hacer|bares|caf[eé]s|para llevar|tiendas de comestibles|guardado|recientes|obtener app|ver fotos|indicaciones|guardar|cerca|enviar al tel[eé]fono|compartir|descripci[oó]n general|opiniones|acerca de|pedir en l[ií]nea|sugerir una edici[oó]n|reclamar este negocio|fotos|fotos y videos|overview|about|reviews)$/i;

  let place_id = null;
  const mPlace = href.match(/place_id[=:]([A-Za-z0-9_-]+)/);
  if (mPlace) place_id = mPlace[1];
  const mCid = href.match(/!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)/);
  const cid = mCid ? mCid[1] : null;

  const h1 = q("h1");
  const name = text(h1);
  const lines = (document.body.innerText || "").split("\n").map(stripIcons).filter(Boolean);

  let rating = null, review_count = null;
  const ratingBtn = qa("button[aria-label], div[aria-label]").find(el => {
    const a = el.getAttribute("aria-label") || "";
    return /\d([.,]\d)?\s*(estrellas|stars)/i.test(a);
  });
  if (ratingBtn) {
    const a = ratingBtn.getAttribute("aria-label") || text(ratingBtn);
    const rm = a.match(/(\d+[.,]?\d*)\s*(estrellas|stars)/i);
    const cm = a.match(/([\d.,]+)\s*(reseñas|reviews|opiniones)/i);
    if (rm) rating = parseFloat(rm[1].replace(",", "."));
    if (cm) review_count = parseInt(cm[1].replace(/[.\s]/g, "").replace(",", ""), 10) || null;
  }
  const nameIdx = name ? lines.findIndex(l => l === name) : -1;
  if (rating == null || review_count == null) {
    const window = nameIdx >= 0 ? lines.slice(nameIdx, nameIdx + 14) : lines.slice(0, 80);
    for (const l of window) {
      if (rating == null && /^\d([.,]\d)?$/.test(l)) {
        const v = parseFloat(l.replace(",", "."));
        if (v >= 1 && v <= 5) rating = v;
      }
      if (review_count == null) {
        let m = l.match(/^\((\d+)\)$/) || l.match(/^(\d+)\s*(opiniones|reseñas|reviews)$/i);
        if (m) review_count = parseInt(m[1], 10);
      }
    }
  }

  let category = null;
  const nameNorm = (name || "").toLowerCase();
  if (nameIdx >= 0) {
    for (let i = nameIdx + 1; i < Math.min(lines.length, nameIdx + 18); i++) {
      const l = lines[i];
      if (/^(descripci[oó]n general|opiniones|acerca de|overview|about|reviews)$/i.test(l)) break;
      if (/^\d([.,]\d)?$/.test(l) || /^\(\d+\)$/.test(l) || UI_NOISE.test(l)) continue;
      if (l.length < 2 || l.length > 60) continue;
      if (/^(indicaciones|guardar|cerca|compartir|pedir)/i.test(l)) continue;
      if (l.toLowerCase() === nameNorm) continue;
      if (nameNorm && (l.toLowerCase().includes(nameNorm) || nameNorm.includes(l.toLowerCase()))) continue;
      category = l;
      break;
    }
  }

  let price_level = null;
  for (const l of (nameIdx >= 0 ? lines.slice(nameIdx, nameIdx + 20) : lines.slice(0, 40))) {
    if (/^\$+$/.test(l) || /^€+$/.test(l)) { price_level = l; break; }
    const pm = l.match(/\b(\${1,4})\b/);
    if (pm && !price_level) price_level = pm[1];
  }

  let address = null;
  const addrBtn = q('button[data-item-id="address"]') || q('button[data-item-id^="address"]');
  if (addrBtn) {
    address = stripIcons(text(addrBtn) || (addrBtn.getAttribute("aria-label") || "")
      .replace(/^(Address:|Dirección:)\s*/i, ""));
  }

  let phone = null, website = null, menu_uri = null;
  const phoneEl = q('button[data-item-id^="phone"]');
  if (phoneEl) {
    phone = stripIcons((phoneEl.getAttribute("aria-label") || text(phoneEl) || "")
      .replace(/^(Phone:|Teléfono:)\s*/i, ""));
  }
  const webEl = q('a[data-item-id="authority"]');
  if (webEl) website = webEl.href || null;
  const menuEl = qa("a[href]").find(a =>
    /rappi|ubereats|didi|menu|menú/i.test((a.href || "") + " " + text(a))
  );
  if (menuEl) menu_uri = menuEl.href || null;

  let hours_text = null, open_now = null;
  const hoursEl = q('button[data-item-id="oh"]');
  if (hoursEl) hours_text = stripIcons(hoursEl.getAttribute("aria-label") || text(hoursEl));
  if (!hours_text || /^horario de atenci[oó]n$/i.test(hours_text)) {
    const hourLine = lines.find(l =>
      /(abierto|cerrado|cierra|abre|open|closed)/i.test(l) &&
      !/^agregar horario/i.test(l) && l.length < 140
    );
    if (hourLine) hours_text = hourLine;
  }
  if (hours_text) {
    if (/^(abierto|open)\b|abierto ·|open now|cierra pronto/i.test(hours_text)) open_now = true;
    if (/^(cerrado|closed)\b|cerrado ·/i.test(hours_text)) open_now = false;
  }

  let lat = null, lng = null;
  const cm = href.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
  if (cm) { lat = parseFloat(cm[1]); lng = parseFloat(cm[2]); }

  let plus_code = null;
  const plusBtn = q('button[data-item-id="oloc"]');
  if (plusBtn) {
    plus_code = stripIcons((plusBtn.getAttribute("aria-label") || text(plusBtn) || "")
      .replace(/^(Plus code:|Código Plus:|Plus\s*Code:)\s*/i, ""));
  }
  if (!plus_code) {
    const pc = lines.find(l => /^[A-Z0-9]{4}\+[A-Z0-9]{2,3}\b/.test(l));
    if (pc) plus_code = pc;
  }

  const photo_urls = [];
  // Plan 1: no persistir fotos (fase 2 = scrape media solo de seleccionados).
  // maxPhotos=0 desactiva la recolección.
  if (maxPhotos > 0) {
    qa('img[src*="googleusercontent"], img[src*="ggpht"]').forEach(img => {
      const s = img.src || "";
      if (s && photo_urls.length < maxPhotos && !photo_urls.includes(s)) photo_urls.push(s);
    });
  }

  const reviews = [];
  qa('[data-review-id], .jftiEf').slice(0, maxReviews).forEach(el => {
    const t = text(el);
    if (t && t.length > 20) reviews.push({ text: t.slice(0, 1000) });
  });

  const blocked = /\/sorry|unusual traffic|captcha/i.test(href + " " + document.title);

  return {
    place_id_from_url: place_id, cid, page_url: href, name, category, price_level,
    rating, review_count, address, phone, website, menu_uri,
    hours_text, open_now, lat, lng, plus_code,
    photo_urls, reviews, blocked, h1_found: !!h1, title: document.title,
    body_snippet: stripIcons((document.body.innerText || "").slice(0, 1200)),
  };
}
""".replace("(args) -> {", "(args) => {")

EXTRACT_ABOUT_JS = r"""
() => {
  const stripIcons = (s) => String(s || "").replace(/[\uE000-\uF8FF]/g, "").replace(/\s+/g, " ").trim();
  const lines = (document.body.innerText || "").split("\n").map(stripIcons).filter(Boolean);

  const aboutIdx = lines.findIndex(l => /^(acerca de|about|from the business|de la empresa)$/i.test(l));
  const slice = aboutIdx >= 0 ? lines.slice(aboutIdx, aboutIdx + 120) : lines.slice(0, 100);
  const blob = slice.join("\n");
  const blobLower = blob.toLowerCase();

  const amenities = {};
  const boolMap = [
    ["dine_in", /para comer aqu[ií]|dine[- ]?in|comer en el local/],
    ["takeout", /para llevar|takeout|take[- ]?away|comida para llevar/],
    ["delivery", /entrega a domicilio|delivery|domicilios?|pide a domicilio/],
    ["curbside_pickup", /recogida en la acera|curbside/],
    ["reservable", /se aceptan reservas|accepts reservations|reservas/],
    ["serves_breakfast", /desayuno|breakfast/],
    ["serves_lunch", /almuerzo|lunch|comida\b/],
    ["serves_dinner", /cena|dinner/],
    ["serves_brunch", /brunch/],
    ["serves_beer", /cerveza|beer/],
    ["serves_wine", /vino|wine/],
    ["serves_cocktails", /c[oó]ctel|cocktail/],
    ["serves_coffee", /caf[eé]|coffee/],
    ["serves_dessert", /postre|dessert/],
    ["serves_vegetarian_food", /vegetariano|vegetarian/],
    ["good_for_children", /apto para ni[nñ]os|good for kids|niños/],
    ["good_for_groups", /grupos|good for groups/],
    ["outdoor_seating", /terraza|asientos al aire libre|outdoor seating/],
    ["live_music", /m[uú]sica en vivo|live music/],
    ["allows_dogs", /se admiten perros|dog.?friendly|perros/],
    ["restroom", /ba[nñ]o|restroom|toilet/],
    ["wheelchair_accessible_entrance", /entrada.*silla de ruedas|wheelchair.?accessible.?entrance|accesible/],
    ["accepts_credit_cards", /tarjeta de cr[eé]dito|credit card/],
    ["accepts_debit_cards", /tarjeta de d[eé]bito|debit card/],
    ["accepts_nfc", /nfc|google pay|apple pay|contactless|sin contacto/],
    ["accepts_cash_only", /solo efectivo|cash only/],
  ];
  for (const [k, rx] of boolMap) {
    if (rx.test(blobLower)) amenities[k] = true;
  }

  // Horario semanal: líneas tipo "lunes 10:00–22:00"
  const dayRx = /^(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i;
  const weekday = [];
  for (const l of slice) {
    if (dayRx.test(l) && /\d/.test(l) && l.length < 80) weekday.push(l);
  }

  let description = null;
  for (let i = 0; i < slice.length; i++) {
    const l = slice[i];
    if (/^(descripci[oó]n|from the owner|informaci[oó]n|summary)/i.test(l) && slice[i+1] && slice[i+1].length > 40) {
      description = slice[i+1].slice(0, 2000);
      break;
    }
  }
  if (!description) {
    const long = slice.find(l => l.length > 80 && l.length < 600 && !dayRx.test(l) && !/https?:/.test(l));
    if (long) description = long.slice(0, 2000);
  }

  let price_level = null;
  for (const l of slice) {
    if (/^\$+$/.test(l)) { price_level = l; break; }
  }

  // Lista cruda de atributos visibles (chips / filas)
  const attribute_labels = [];
  for (const l of slice) {
    if (l.length < 3 || l.length > 60) continue;
    if (dayRx.test(l) || /^(acerca de|about|horario|hours)/i.test(l)) continue;
    if (/^\d/.test(l)) continue;
    attribute_labels.push(l);
    if (attribute_labels.length >= 40) break;
  }

  return {
    amenities,
    weekday_descriptions: weekday.join("\n"),
    description,
    price_level,
    attribute_labels,
    about_snippet: blob.slice(0, 1500),
    dine_in: amenities.dine_in || null,
    takeout: amenities.takeout || null,
    delivery: amenities.delivery || null,
  };
}
"""


def maps_url_for_place_id(place_id: str) -> str:
    return (
        "https://www.google.com/maps/search/?api=1&query=place"
        f"&query_place_id={place_id}&hl=es-CO"
    )


def _parse_review_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = re.sub(r"[^\d]", "", str(value))
    return int(s) if s else None


def _click_tab(page, *names: str) -> bool:
    for name in names:
        try:
            page.get_by_role("tab", name=re.compile(name, re.I)).first.click(timeout=2500)
            return True
        except Exception:
            pass
        try:
            page.get_by_role("button", name=re.compile(name, re.I)).first.click(timeout=2000)
            return True
        except Exception:
            pass
        try:
            page.locator(f"text={name}").first.click(timeout=1500)
            return True
        except Exception:
            pass
    return False


def scrape_place_overview(
    place_id: str,
    *,
    headless: bool = True,
    chrome_path: str = "/usr/bin/google-chrome",
    wait_ms: int = 7000,
    max_photos: int = 0,
    max_reviews: int = 10,
    locale: str = "es-CO",
    open_about: bool = True,
    open_reviews: bool = True,
) -> dict[str, Any]:
    """Overview + About (+ reseñas). No descarga imágenes. $0 Places API."""
    from playwright.sync_api import sync_playwright

    url = maps_url_for_place_id(place_id)
    out: dict[str, Any] = {
        "ok": False,
        "status": "error",
        "place_id": place_id,
        "url": url,
        "scraper_version": SCRAPER_VERSION,
        "data": None,
        "error": None,
        "final_url": None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chrome_path,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            locale=locale,
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            for label in ("Aceptar todo", "Accept all", "Reject all", "Rechazar todo"):
                try:
                    page.get_by_role("button", name=label).click(timeout=2000)
                    time.sleep(0.4)
                except Exception:
                    pass

            page.wait_for_timeout(wait_ms)
            try:
                page.wait_for_selector("h1", timeout=20000)
            except Exception:
                pass
            page.wait_for_timeout(2000)

            data = page.evaluate(EXTRACT_JS, [max_photos, max_reviews])
            out["final_url"] = page.url

            if data.get("blocked") or "/sorry" in (page.url or ""):
                out["status"] = "blocked"
                out["error"] = "Maps /sorry o captcha"
                out["data"] = data
                return out

            name = (data.get("name") or "").strip()
            if not name and not data.get("h1_found"):
                out["status"] = "not_found"
                out["error"] = "Sin panel de lugar (h1 vacío)"
                out["data"] = data
                return out

            # Expandir horario si hay botón
            try:
                oh = page.locator('button[data-item-id="oh"]').first
                if oh.count():
                    oh.click(timeout=1500)
                    page.wait_for_timeout(800)
            except Exception:
                pass

            if open_about:
                if _click_tab(page, r"Acerca de", r"About"):
                    page.wait_for_timeout(1800)
                    about = page.evaluate(EXTRACT_ABOUT_JS)
                    if about:
                        am = dict(data.get("amenities") or {})
                        am.update(about.get("amenities") or {})
                        data["amenities"] = am
                        data["dine_in"] = about.get("dine_in") or data.get("dine_in")
                        data["takeout"] = about.get("takeout") or data.get("takeout")
                        data["delivery"] = about.get("delivery") or data.get("delivery")
                        if about.get("weekday_descriptions"):
                            data["weekday_descriptions"] = about["weekday_descriptions"]
                        if about.get("description"):
                            data["description"] = about["description"]
                        if about.get("price_level") and not data.get("price_level"):
                            data["price_level"] = about["price_level"]
                        data["attribute_labels"] = about.get("attribute_labels") or []
                        data["about_snippet"] = about.get("about_snippet")
                        # re-leer hours tras expand
                        try:
                            oh2 = page.evaluate(
                                """() => {
                                  const el = document.querySelector('button[data-item-id="oh"]');
                                  if (!el) return null;
                                  const t = (el.getAttribute('aria-label') || el.innerText || '').replace(/[\\uE000-\\uF8FF]/g,'').trim();
                                  return t || null;
                                }"""
                            )
                            if oh2 and len(oh2) > len(data.get("hours_text") or ""):
                                data["hours_text"] = oh2
                        except Exception:
                            pass

            if open_reviews and len(data.get("reviews") or []) < 3:
                if _click_tab(page, r"Opiniones", r"Reviews"):
                    page.wait_for_timeout(2000)
                    try:
                        page.mouse.wheel(0, 1200)
                        page.wait_for_timeout(800)
                    except Exception:
                        pass
                    more = page.evaluate(
                        """(maxReviews) => {
                          const strip = (s) => String(s||'').replace(/[\\uE000-\\uF8FF]/g,'').replace(/\\s+/g,' ').trim();
                          const out = [];
                          document.querySelectorAll('[data-review-id], .jftiEf').forEach(el => {
                            const t = strip(el.innerText||'');
                            if (t.length > 25 && out.length < maxReviews) out.push({text: t.slice(0,1000)});
                          });
                          return out;
                        }""",
                        max_reviews,
                    )
                    if more:
                        data["reviews"] = more

            if data.get("review_count") is not None:
                data["review_count"] = _parse_review_count(data.get("review_count"))

            out["ok"] = True
            out["status"] = "ok"
            out["data"] = data
            out["final_url"] = page.url
            return out
        except Exception as exc:
            out["error"] = str(exc)
            out["status"] = "error"
            try:
                out["final_url"] = page.url
            except Exception:
                pass
            return out
        finally:
            browser.close()
