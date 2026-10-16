# Retomar scrape Maps → GooglePlaceDetails (Plan 1)

**Pausado:** 2026-09-07 (noche, hora CO)  
**Motivo:** liberar VPS scraper para otro proyecto.  
**Estado al pausar:** workers `run_maps_shard_worker.py` detenidos; datos en Postgres prod intactos.

---

## Snapshot al pausar

| Métrica | Valor |
|--------|--------|
| Catálogo `GooglePlaceId` | **93 045** |
| `GooglePlaceDetails` ok | **75 852** (~**81.5%**) |
| Cola (sin ficha ok) | **17 193** |
| Último `fetched_at` | 2026-09-08 ~03:19 Europe/Berlin |
| Errores staging (no-ok) | ~0 en el último check |
| Scraper | `maps_v3` (Playwright, **$0** Places API) |
| Shards | 6 |

Ritmo sano histórico: ~600–650 ok/h → cola restante ≈ **1–1.5 días** si se retoma igual.

---

## Infra

| Rol | Host | Notas |
|-----|------|--------|
| **VPS scraper** | `root@89.167.92.76` (`ubuntu-8gb-hel1-1`) | Chrome + Playwright (`/root/UK/venv`), código en `/root/medellin-project` |
| **App / DB prod** | `root@65.109.54.17` (hserver3) | `/var/www/medellin-project`, Postgres |
| **Túnel DB** | En VPS: `127.0.0.1:5433` → hserver3 `:5432` | Histórico: `ssh -N -L 5433:127.0.0.1:5432 Hserver3` (pid típico `773045`) |
| **DATABASE_URL** | VPS: `/tmp/vive_db_tunnel.url` | Lo lee `launch_maps_shards.sh` |

Staging **no** aparece en el sitio público. Destino = tabla `explorer_googleplacedetails`, no `Places`.

---

## Qué es Plan 1 (y qué no)

**Sí**

- Overview Maps + About + reseñas → `GooglePlaceDetails`
- Clasificación (`explorer/utils/place_classify.py`) → `tipo` / `tipo_family`
- Upsert vía **psycopg2** en el VPS (sin GeoDjango/GDAL ahí)
- Fotos: `max_photos=0` / `photo_urls=None` (no guardar URLs CDN en esta fase)

**No (aún)**

- Places Details/Photos API de pago
- Publicar staging → `Places`
- Descargar/hospedar imágenes (eso es **Fase 2**, solo lugares seleccionados)

---

## Archivos clave (repo local = `Proj/med`)

| Path | Rol |
|------|-----|
| `scripts/run_maps_shard_worker.py` | Worker por shard (cola SQL + scrape + upsert) |
| `scripts/launch_maps_shards.sh` | Arranca N shards en el VPS |
| `explorer/scraping/maps_place_overview.py` | Extractor Playwright `maps_v3` |
| `explorer/utils/place_classify.py` | Clasificación |
| `explorer/models.py` → `GooglePlaceDetails` | Modelo staging |
| `explorer/migrations/0035_*.py`, `0036_*.py` | Migraciones (`price_level`, `description`, …) |
| `scripts/staging_preview_server.py` | Preview local sin GDAL → `http://127.0.0.1:8055/` |
| `explorer/views_staging_local.py` | Vistas Django staging (requieren GDAL) |

En el VPS el código vive en `/root/medellin-project` (sincronizar con `scp`/`rsync` desde el repo local antes de retomar si hubo cambios).

Logs VPS: `/root/medellin-project/data/maps_shards/shard_N.log` y `.out`

---

## Bugs / lecciones (no repetir)

1. **Cola vacía falsa:** filtrar shard solo en Python tras un `LIMIT` chico → el worker cree que terminó con decenas de miles pendientes. **Fix:** filtro `md5(place_id)` en SQL dentro de `fetch_queue` (ya en el worker).
2. **Caída SSL del túnel:** el 2026-09-02 los 6 shards murieron por `SSL connection has been closed unexpectedly` y nadie los relanzó → ~5 días sin progreso con ~18k en cola. Al retomar: comprobar túnel + relanzar; ideal un watchdog/`cron` que reinicie si `pgrep` = 0 y cola > 0.
3. Tras 3 “cola vacía” seguidas el worker hace `end` (comportamiento normal cuando realmente no hay pendientes de su shard).

---

## Cómo retomar (checklist)

### 1) VPS libre y código al día

```bash
ssh root@89.167.92.76
# opcional: rsync/scp del repo local → /root/medellin-project
```

### 2) Túnel a Postgres prod

```bash
# si no escucha 5433:
ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=6 \
  -o ExitOnForwardFailure=yes \
  -L 5433:127.0.0.1:5432 Hserver3 &
# DATABASE_URL debe apuntar a 127.0.0.1:5433 (archivo histórico):
cat /tmp/vive_db_tunnel.url
```

### 3) Lanzar 6 shards

```bash
export DATABASE_URL="$(cat /tmp/vive_db_tunnel.url)"
export PYTHONPATH=/root/medellin-project
SHARDS=6 bash /root/medellin-project/scripts/launch_maps_shards.sh
# o el helper histórico:
# bash /tmp/relaunch_shards.sh
```

Parámetros usados en producción: `--batch 40 --pause 2.0 --wait-ms 6500`, 6 shards.

### 4) Verificar

```bash
pgrep -af run_maps_shard_worker.py
tail -1 /root/medellin-project/data/maps_shards/shard_0.log
# counts:
# details_ok / cola / last_fetch (queries en el propio worker o psycopg2 vía túnel)
```

### 5) Parar (como ahora)

```bash
pkill -f run_maps_shard_worker.py
# opcional limpiar Chromes de Playwright huérfanos
```

---

## Preview local (sin tocar prod scrape)

```bash
# en la máquina de desarrollo, con acceso DB si aplica:
python scripts/staging_preview_server.py
# → http://127.0.0.1:8055/  y  /d/<place_id>
```

---

## Siguiente trabajo (cuando vuelva el VPS)

1. Relanzar shards hasta vaciar cola (~17k al pausar; puede crecer si se descubren más IDs).
2. (Opcional) limpiar `photo_urls` históricas si quedaron de corridas viejas.
3. **Fase 2:** scrape de media solo para lugares seleccionados.
4. Más adelante: publicar staging → `Places` con curación.

---

## Contacto rápido en chat

Frases útiles: “cómo vamos”, “lánzalo”, “para el scraper”.  
Skill relacionada: `.cursor/skills/medellin-turismo-lifestyle/` (contenido turismo; no ops del scraper).
