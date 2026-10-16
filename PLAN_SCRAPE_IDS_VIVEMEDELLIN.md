# Plan: scrapear / enriquecer IDs sin ficha (ViveMedellín)

> **Ops actual (Plan 1 Playwright → staging):** ver [`docs/RESUME_MAPS_SCRAPE_PLAN1.md`](docs/RESUME_MAPS_SCRAPE_PLAN1.md)  
> Pausado 2026-09-07 en VPS `89.167.92.76` (~81.5% ok). Retomar con ese doc.

Basado en los scrapers de MenuRadar **ES** (`/root/SPAIN`) y **UK** (`Proj/uk`), y en lo que ya existe en ViveMedellín (`GooglePlaceId`, `procesar_pendientes`, `report_ids_sin_ficha`).

## Hallazgos MenuRadar

Ambos proyectos tienen **dos capas**:

1. **Match Place ID** — Places API (New) Text Search → `ChIJ…` (equivalente a tu barrido; ya lo tienes en el catálogo).
2. **Fotos Google Maps** — Playwright → JSON → import + R2. **No** trae rating, horarios, reseñas ni el resto de campos de una ficha Vive.

| | MenuRadar ES/UK | ViveMedellín |
|--|-----------------|--------------|
| Resolver Place ID | Text Search API | `GooglePlaceId` (hecho) |
| Ficha completa | No (Details casi no se usa) | `procesar_pendientes` (Place Details) |
| Fotos | Playwright Maps (barato, frágil, VPN) | Photos API vía Details |
| Cola | JSON jobs + shards + failure registry | `PendingPlace` (no enlazado al catálogo) |

**Conclusión:** copiar solo el scraper Maps **no alcanza** para publicar lugares. Lo útil de MenuRadar es el **patrón de cola/prioridad/shards**. Lo útil de Vive es **Place Details → `Places`**.

**Enfoque del plan:** API Place Details como camino principal de ficha + cola tipo MenuRadar sobre `GooglePlaceId.sin_ficha()`. Playwright de fotos = fase opcional posterior.

---

## Estado de partida

```bash
python manage.py report_ids_sin_ficha --por-area
# ~60k+ sin ficha vs ~17k con ficha
```

---

## Fase 0 — Puente catálogo → cola

Hoy `procesar_pendientes` solo lee `PendingPlace`.

1. Comando `enqueue_google_place_ids`:
   - Fuente: `GooglePlaceId.objects.sin_ficha()`
   - Filtros: `--area`, `--source`, `--limit`, `--exclude-types`
   - Prioridad: áreas core (Poblado, Laureles, Candelaria, Envigado, Belén), luego `discovery_count`, luego recientes
   - Destino: `PendingPlace(status=pending)` y/o `data/place-details-jobs.json`
2. Idempotente: no encolar si ya está en `Places` o processed.

---

## Fase 1 — Enriquecer fichas (Place Details)

Extender `procesar_pendientes` (o wrapper `procesar_catalogo_ids`):

- Misma `FIELDMASK_DETAILS` + fotos → `Places` + `Foto` + JSON storage
- Controles: `--limit`, presupuesto mensual, `--max-photos-per-place` (ej. 5), delay 0.3–0.5 s
- Shards: `--shard-index` / `--shard-count` (patrón UK)
- Registry de fallos permanentes (≥2)

**Coste:** ~$17/1000 Details tras 5.000 gratis/mes + Photos. No procesar 60k de un golpe.

Orden de campaña:

1. Core: Poblado, Laureles, Candelaria, Envigado, Belén  
2. Resto comunas Medellín  
3. Municipios valle  
4. Oriente / turismo  

---

## Fase 2 — (Opcional) Fotos baratas vía Playwright

Si duele el SKU Photos:

1. Adaptar `google_maps_photo_playwright.py` (UK/ES) a jobs Vive (`place_id`)
2. Import a `Foto` + R2
3. Correr en PC con IP residencial/VPN CO (VPS Hetzner suele 403)

La ficha puede existir antes con pocas fotos API.

---

## Fase 3 — Operación

| Comando | Rol |
|---------|-----|
| `report_ids_sin_ficha --por-area` | Cuántos faltan |
| `enqueue_google_place_ids --limit 1000 --area "…"` | Llenar cola |
| `procesar_pendientes --limit 500` | Details + fotos |
| Lote diario (shell) | Estilo `run_google_maps_daily_batch.sh` pero Details |

Éxito: bajar `% sin enriquecer` en áreas core primero.

---

## Qué no hacer

- No scrapear Maps esperando rating/horarios/reseñas.
- No Details masivo sin presupuesto ni prioridad.
- No Playwright de fotos desde el VPS sin probar 403.

---

## Entregables al implementar

1. `enqueue_google_place_ids`
2. Ajustes a `procesar_pendientes` (budget, max-photos, shards)
3. Sección en `STRATEGIA_NUEVOS_LUGARES.md`
4. Script lote diario
5. (Sprint 2) puerto mínimo photo playwright → `Foto`/R2

## Referencias MenuRadar

- ES: `/root/SPAIN/scripts/google_maps_photo_playwright.py`, `build_google_photo_jobs_from_db.py`, `match_ubereats_google_place_id.py`
- UK: `Proj/uk/scripts/google_maps_photo_playwright.py`, `build_google_maps_photo_jobs`, docs `FLUJO-GOOGLE-MAPS-FOTOS-UK.md`, `TRIPLE-SCRAPE-LAUNCH-PLAN.md`
- Vive: `explorer/management/commands/procesar_pendientes.py`, `report_ids_sin_ficha.py`
