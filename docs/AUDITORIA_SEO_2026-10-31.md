# Auditoría profunda de ViveMedellín — 31 oct 2026

Cuatro auditorías en solo lectura: SEO técnico en vivo (curl como Googlebot), Search Console
por API, calidad de datos en la base de producción y rendimiento/infraestructura (Cloudflare,
servidor, Django). Complementa `docs/PLAN_INCORPORACION_GOOGLE.md`.

## Resumen

El sitio no tiene un bloqueo técnico: robots, canónicos, hreflang y fetch están bien, y Google
elige los mismos canónicos que declaramos. El problema es de **confianza y calidad a escala**
en un dominio de 12 semanas, agravado por tres fallos que mandan señales malas:

1. **Una trampa de rastreo** en la paginación consume ~65 % de las peticiones de Django.
2. **~15.000 fichas delgadas siguen pidiendo `index`**: la regla `indexable` solo se aplica al sitemap.
3. **El sitemap también promueve fichas de 1★, barberías y lavanderías** que entran por tener carta.

Google descubre las fichas solo por sitemap (no por enlaces), rastrea y descarta. Nada
editorial (guías, comunas, listados) está en el índice.

## Cifras

| Indicador | Valor |
|---|---|
| Datos en GSC | desde 19 sep (42 días): 5 clics, 449 impresiones, posición 8,0 |
| Impresiones/día | 14,6 (17 sep–16 oct) → 0,8 (17–30 oct), −97 % |
| Páginas con impresiones | 283 (máx. 12 impresiones; ~97 % de consultas ocultas = nombres de locales) |
| Inspección de 90 URLs | indexadas solo `/` y `/en/`; las 15 fichas que tenían impresiones: "rastreada, sin indexar" |
| Guías, comunas, listados | 0 de 19 conocidas por Google |
| Fichas publicadas / indexables (sitemap) | 17.562 / 4.786 |
| Fichas con `descripcion` propia | 0 % |
| Fichas con texto propio en inglés | 0 (solo las 12 guías están traducidas) |
| Cartas / platos | 2.008 / 72.410 (99,99 % con precio) |
| Peticiones Django en 24 h | 189.508, de ellas 122.526 de PerplexityBot |
| HTML cacheado en Cloudflare | 0 % (TTFB 0,45–1,1 s) |
| Disco del servidor | 90 % (372/436 GB; ViveMedellín usa 1,9 GB, el resto es UK/SPAIN/Postgres) |

## Hallazgos priorizados

### P0 — dañan el sitio hoy

1. **Trampa de rastreo en la paginación.** `lugares/places_list.html:241,249` concatena
   `&{{ filtros_url }}` y `views.py:1025` copia todo `GET` salvo `page`. Las claves basura
   (`amp;`) se vuelven a codificar en cada visita: `?page=3&amp%3B=` crece sin fin. PerplexityBot
   pidió ~100.000 URLs así en un día (220 KB y ~1 s de origen cada una). También gasta el
   presupuesto de rastreo de Google en URLs inútiles.
   **Arreglo:** lista blanca de parámetros (`q`, `tipo`, `area`, `comuna`, filtros especiales,
   `lat`/`lng`/`radio`/`cerca`) y 301 a la URL limpia si llega uno desconocido. Regla WAF de
   rate limiting para PerplexityBot, Amazonbot y Bytespider.

2. **Las fichas no indexables piden `index`.** `lugares/places_detail.html` no define
   `{% block meta_robots %}` y hereda `index, follow` de `base.html:16`. De 12.472 fichas
   enlazadas desde `/lugares/`, 7.731 no están en el sitemap pero piden índice (×2 con inglés).
   **Arreglo:** la vista calcula `es_indexable` con la misma regla que `Places.objects.indexables()`
   y la plantilla pone `noindex, follow` si no lo es.

3. **`indexables()` acepta cualquier ficha con carta** (`models.py:161`). Entran 29 fichas con
   rating < 3, barberías, lavandería, coworking, salones de eventos y 113 lugares **cerrados
   permanentemente** (detectables por `GooglePlaceDetails.category` que empieza por "Cerrado").
   **Arreglo:** carta solo cuenta con rating ≥ 3,5 (o sin rating pero con ≥ 10 platos) y tipo de
   comida, café o noche; excluir cerrados y `tipo='otros'`.

4. **`vivemedellin.co` está aparcado** (ParkLogic, `Disallow: /`) y no redirige. Fue el dominio
   anterior (jul 2025) y todavía aparece como referente. Si sigue siendo nuestro: 301 por ruta a
   `.net` y "Cambio de dirección" en GSC.

### P1 — impiden que Google confíe y descubra

5. **Descubrimiento solo por sitemap.** Google no llega a las fichas por enlaces. Faltan enlaces
   en HTML: ficha → su guía (la nota de guía hoy es texto sin enlace, `places_detail.html:107`),
   ficha → su comuna, home y lista → guías y comunas. Pedir indexación a mano de `/lugares/`,
   `/guias/` y las 12 guías (tarea manual en GSC).

6. **HTML imposible de cachear.**
   - `components/lang_switcher.html:8,14` pone `{% csrf_token %}` en todas las páginas →
     `Set-Cookie: csrftoken` + `Vary: Cookie`. Cambiar a dos enlaces `<a>` (el idioma va por prefijo).
     El formulario de newsletter (`home_v4.html:193`) pide el token por fetch.
   - `base.html:4` versiona los estáticos con `{% now "YmdHi" %}`: la URL de los CSS cambia cada
     minuto. Usar una versión fija por deploy.
   - Luego: regla de Cache Rules "HTML anónimo 10 min" (sin cookie `sessionid`/`csrftoken`,
     excluye `/admin`, `/api/`, `/i18n/`) y activar Early Hints.

7. **`lastmod` poco creíble.** 79 % de las fichas cambian de fecha en una semana (una foto nueva
   mueve `contenido_actualizado`, `models.py:1474`) y 581 tienen fecha de jul 2025, antes de
   que existiera `.net`. Solo contar cambios visibles relevantes (carta, nombre, horario,
   primera foto) y no fechar antes del 9 ago 2026.

8. **Horarios solo por JavaScript** (`places_detail.html:187-198`, "Cargando...") y
   `robots.txt:22-23` bloquea `/jsi18n/`. Pintar el horario en el servidor, añadir
   `openingHoursSpecification` al JSON-LD y desbloquear jsi18n.

### P2 — contenido único (Fase 2 del plan, con datos que ya existen)

9. **`hasMenu` + rango de precios real** desde la carta en 1.859 fichas indexables
   (`priceRange`, plato más barato y mediana). Hoy `precio` está vacío en 3.354 indexables.
10. **Párrafo generado desde datos** por ficha: tipo, zona, horario, rango de precio, secciones de
    la carta, atributos `serves_*` / `outdoor_seating` / `live_music` (hoy solo chips), y la frase
    de la guía si está en una.
11. **1–2 citas de reseñas** (3.885 indexables tienen JSON de reseñas; hoy solo se enlaza).
12. **Reparar las 500 fichas nuevas:** `publicar_pendientes_enriquecidos.py` no copió reseñas
    (227), amenities (301) ni horario estructurado. Backfill sin API.
13. **Comunas:** 252 indexables sin comuna (Bello, Rionegro, Envigado, Sabaneta). Completar
    `OSM_IDS_MEDELLIN` con los municipios y reasignar.
14. **Guías más largas** (hoy 24–97 palabras de texto propio, salvo LGBTQ+): 600+ palabras con
    datos de carta por parada, BreadcrumbList, y guías nuevas por comuna × tipo (76 combinaciones
    con ≥ 8 lugares, p. ej. bares en El Poblado 88, en Laureles 60).

### P3 — limpieza y pulido

15. **Inglés:** "Carta", "Lugares" (breadcrumb) y "Pedir en Rappi" salen en español en `/en/`
    (`locale/en/.../django.po`, `models.py:1391-1395`).
16. **Meta description y dirección** repiten la zona ("Laureles - Estadio, Medellín, Laureles");
    "Envigado, Medellín" mezcla municipios; 37 de 62 títulos pasan de 60 caracteres.
    `schema_org.html:76-78` declara `paymentAccepted: Cash` e `isAccessibleForFree` sin datos.
17. **Datos sucios:** 53 pares de duplicados a < 150 m (`qchimba` / `qchimba-1`), 359 nombres en
    mayúsculas, 73 nombres con relleno SEO, 7 con emojis.
18. **Duplicado `/about-us/`** sin `/en/` sirve `/nosotros/` en español con canonical propio
    (`Medellin/urls.py:141-142`). Paginación sin "· Página N" en el título.
19. **Front:** 11 CSS que bloquean el render y jQuery síncrono; imágenes sin `width`/`height`;
    foto LCP de la ficha de 168 KB en JPEG; 63 KB de CSS inline en la ficha.
20. **Servidor:** gunicorn con 4 workers sync (pasar a gthread); log de nginx sin `$host` ni
    `$request_time`; disco al 90 % por UK/SPAIN (riesgo para todos los sitios).

## Para la ola "top" (pendientes)

2.563 candidatos, 390 son contenedores (Éxito, Carulla, centros comerciales, parques, licoreras) y
10 están cerrados. Filtro propuesto sobre `GooglePlaceDetails`:

```python
contenedor = (
    Q(category__iregex=r'^(caf[eé]|cafeter[ií]a)s? [0-9]+$')
    | Q(category__regex=r'^\(')
    | Q(category__iregex=r'^(supermercado|centro comercial|tienda de alimentaci|tienda de licores|grandes almacenes|hipermercado|hotel|gasolinera)')
    | Q(category__istartswith='Cerrado')
    | Q(display_name__iregex=r'^(almacenes )?([eé]xito|carulla|euro supermercados|pricesmart|makro|jumbo|d1|ara|olimpica|dollarcity)\M')
    | Q(display_name__iregex=r'^(centro comercial|c\.? ?c\.? |mall |plazoleta|edificio|eds )|(centro comercial|\mmall)$|licorera|distribuidora|comercializadora')
)
```

Quedan ~2.163 limpios. Antes de otra ola: esperar 2–4 semanas y medir si las fichas con carta
se indexan.

## Orden de trabajo

| Semana | Trabajo |
|---|---|
| 1 | P0 (1–3) en un deploy; P1 6 y 7; pedir indexación manual; decidir `vivemedellin.co` |
| 2 | P1 5 y 8; P2 9, 12 y 13 |
| 3 | P2 10, 11 y 14; P3 15 y 16 |
| 4 | Medir en GSC por sitemap; decidir la siguiente ola (818 con carta, ~2.163 top) |
| Continuo | Enlaces externos (Fase 6 del plan): la palanca más fuerte para un dominio nuevo |

## Metas a 30 días

- 0 URLs con parámetros basura servidas (todas 301).
- `index` solo en las fichas del sitemap; sitemap sin cerrados, < 3,5★ ni otros rubros.
- ≥ 50 % del HTML anónimo servido desde caché de Cloudflare; TTFB < 0,3 s.
- Guías y comunas conocidas por Google; ≥ 300 fichas indexadas.
