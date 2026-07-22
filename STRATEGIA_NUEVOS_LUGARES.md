# Estrategia para agregar nuevos lugares a ViveMedellín

Este documento describe el flujo recomendado para descubrir, filtrar y cargar nuevos lugares (restaurantes, bares, cafés, etc.) usando la API de Google Places.

---

## Resumen del pipeline

```
[1] GRILLA VIVE       →  [2] SCAN GRATIS (Text Search IDs)  →  PendingPlace
         ↓                              ↓
  generar_grilla_vive_medellin    scan_place_ids_gratis (~$0)
                                              ↓
                                    [3] DESCARTE (limpiar cola)
                                              ↓
                         [4] SCRAPE / PROCESAR selectivo (Place Details, solo los importantes)
                                              ↓
                                    Places + fotos + JSON
```

**Pipeline alternativo (de pago)** — descubrimiento más exhaustivo pero con cuota limitada:

```
Grilla → scan_nuevos_lugares (Nearby Search Pro) → PendingPlace → procesar_pendientes
```

- **Fase 1 gratis – Descubrir IDs**: grilla + Text Search `places.id` → `PendingPlace` (sin nombre, sin fotos, sin costo).
- **Fase 1 paga – Descubrir IDs (complemento)**: Nearby Search solo si Text Search dejó huecos (~5.000 gratis/mes, luego ~$32/1000).
- **Descarte**: marcar `processed` los ya en Places; `skipped` los tipos inútiles.
- **Fase 2 – Enriquecer**: Place Details + fotos **solo** para páginas con tráfico o cola priorizada.

---

## Cuándo usar cada comando

| Objetivo | Comando | Costo aprox. |
|----------|---------|--------------|
| Grilla Medellín + Envigado + Poblado/Laureles | `python manage.py generar_grilla_vive_medellin` | $0 |
| **Descubrir place_id gratis (recomendado)** | `python manage.py scan_place_ids_gratis` | **$0** |
| Ver progreso del scan gratis | `python manage.py scan_place_ids_gratis --status` | $0 |
| Exportar todos los IDs para scraper | `python manage.py scan_place_ids_gratis --export-ids ids.txt` | $0 |
| Descubrir IDs (complemento, Nearby) | `python manage.py scan_nuevos_lugares` | ~$32/1000 tras cuota gratis |
| Limpiar cola | `python manage.py descartar_pendientes_inutiles` | $0 |
| Enriquecer pendientes (Details + fotos) | `python manage.py procesar_pendientes --limit N` | ~$17/1000 details |
| Añadir lugar concreto por nombre | `python manage.py agregar_lugar_por_nombre "Nombre"` | 1 Text Search + Details |
| Verificar place_id existentes | `python manage.py verificar_place_ids_google --only-pending` | $0 |

---

## Estrategia recomendada (orden de ejecución)

### A) Descubrir todos los place_id gratis (Medellín + Envigado)

1. **Grilla densa** (Medellín, Envigado, Poblado, Laureles/La 70):
   ```bash
   python manage.py generar_grilla_vive_medellin --dry-run
   python manage.py generar_grilla_vive_medellin
   ```
2. **Scan gratis** (Text Search IDs Only — ~22 tipos × cada punto de grilla):
   ```bash
   python manage.py scan_place_ids_gratis --status
   python manage.py scan_place_ids_gratis --limit 10          # prueba
   python manage.py scan_place_ids_gratis                   # barrido completo
   ```
3. **Exportar IDs** para tu scraper:
   ```bash
   python manage.py scan_place_ids_gratis --export-ids data/place_ids_medellin.txt
   ```
4. **Limpiar cola** y enriquecer solo lo prioritario:
   ```bash
   python manage.py descartar_pendientes_inutiles
   python manage.py procesar_pendientes --limit 50
   ```

### B) Primera vez o grilla amplia (Nearby, de pago)

1. **Grilla** (si hace falta):
   ```bash
   python manage.py generar_grilla_medellin_huecos --dry-run   # ver cuántos puntos
   python manage.py generar_grilla_medellin_huecos            # crear puntos
   ```
2. **Fase 1 – Descubrir**:
   ```bash
   python manage.py scan_nuevos_lugares   # usa solo puntos no procesados
   ```
3. **Limpiar cola**:
   ```bash
   python manage.py descartar_pendientes_inutiles --dry-run   # revisar
   python manage.py descartar_pendientes_inutiles             # aplicar
   ```
4. **Ver costo y procesar**:
   ```bash
   python manage.py procesar_pendientes --status
   python manage.py procesar_pendientes   # o --limit 100 para probar
   ```
5. **Post-procesamiento** (después de procesar):
   ```bash
   python manage.py asignar_regiones
   python manage.py calcular_weighted_rating
   python manage.py generar_miniaturas_gcs   # si usas variantes
   ```

### C) Añadir lugares que la grilla no trae (ej. Moresko, Purple Club)

- **Por nombre** (Text Search):
  ```bash
  python manage.py agregar_lugar_por_nombre "Moresko"
  python manage.py agregar_lugar_por_nombre "Purple Club Medellin"
  ```
- Luego ejecutar descarte (si hay muchos pendientes) y procesar:
  ```bash
  python manage.py descartar_pendientes_inutiles
  python manage.py procesar_pendientes
  ```

### D) Mantenimiento periódico (nuevos lugares en la ciudad)

1. Añadir más puntos de grilla si abriste nuevas zonas (`generar_grilla_medellin_huecos` o `generar_grilla_expansion`).
2. Ejecutar **scan** (solo procesa puntos de grilla aún no escaneados).
3. Ejecutar **descarte**.
4. Revisar con `procesar_pendientes --status` y luego **procesar** (todo o con `--limit`).

---

## Control de costos

### Text Search — IDs Only (gratis ilimitado)

Para **verificar** que el `place_id` de un lugar existente sigue siendo correcto:

```bash
python manage.py verificar_place_ids_google --dry-run    # ver qué haría
python manage.py verificar_place_ids_google --only-pending
python manage.py verificar_place_ids_google --resumen
```

- FieldMask: `places.id,nextPageToken` → tarifa **Text Search Essentials — IDs Only** (gratis ilimitado según facturación actual).
- Campos en `Places`: `google_match_status`, `google_match_confidence`, `google_match_checked_at`.
- `Places.place_id` **ya es** el Google Place ID (no hace falta un campo `google_place_id` aparte).

### Nearby Search (descubrir lugares desconocidos)

- **No se vuelve gratis** pidiendo solo `places.id`: sigue siendo **Nearby Search Pro** (~5.000 gratis/mes, luego ~$32/1000).
- Fase 1 del pipeline (`scan_nuevos_lugares`): ~$0.032 por punto de grilla (o cuota gratuita mensual).
- Usar Nearby **solo** para descubrir lugares que aún no tienes, no para emparejar registros existentes.

### Place Details + fotos (enriquecimiento selectivo)

- Fase 2 (`procesar_pendientes`): Place Details Pro 5.000 gratis/mes; después $17/1000. Fotos 1.000 gratis; después $7/1000.
- **Enriquecer solo páginas con tráfico**, no todos los pendientes de golpe.

### Text Search con nombre (bajo volumen)

- `agregar_lugar_por_nombre`: primero Text Search IDs Only (gratis); si hay candidatos nuevos, una segunda llamada con `displayName`/`location` para la cola.
- Usar solo para lugares concretos (Moresko, Purple Club, etc.).

Recomendación: usar siempre `--dry-run` o `--status` / `--resumen` antes de ejecutar scan o procesar.

---

## Tipos que se piden a Google (resumen)

- **Incluidos**: restaurantes, bar, pub, night_club, wine_bar, **lounge_bar**, **cocktail_bar**, **live_music_venue**, café, heladerías, panaderías, museos, etc. (ver `scan_nuevos_lugares.INCLUDED_TYPES`).
- **Excluidos**: hospital, gasolinera, banco, supermercado, colegio, etc. (ver `EXCLUDED_TYPES` y `EXTRA_EXCLUDED_TYPES`).

Si un lugar no aparece en el escaneo, puede ser: (1) clasificado por Google con un tipo que antes no estaba en incluidos (ya añadimos lounge_bar, cocktail_bar, live_music_venue), (2) fuera del radio de los puntos de grilla, o (3) fuera del top 20 por punto. En esos casos usar `agregar_lugar_por_nombre`.

---

## Comando todo-en-uno (opcional)

Para ejecutar el flujo completo en orden (descarte → scan → descarte → procesar con límite opcional):

```bash
python manage.py pipeline_nuevos_lugares --dry-run    # ver qué haría
python manage.py pipeline_nuevos_lugares             # ejecutar todo
python manage.py pipeline_nuevos_lugares --procesar-limit 50   # procesar solo 50
```

Ver ayuda del comando para más opciones.

### Lista curada de nombres (archivo)

Puedes mantener un archivo con nombres de lugares a buscar (uno por línea) y pasarlo al pipeline:

```bash
# Crear/editar explorer/management/commands/lugares_a_buscar.txt (una línea por nombre)
python manage.py pipeline_nuevos_lugares --from-file explorer/management/commands/lugares_a_buscar.txt --skip-scan
```

Las líneas que empiezan con `#` se ignoran.
