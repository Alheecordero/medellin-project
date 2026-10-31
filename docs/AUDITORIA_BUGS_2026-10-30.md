# Auditoría de errores y bugs — 30 oct 2026

Cinco frentes, todos en solo lectura: logs de gunicorn de 7 días (612.727 líneas), rastreo del
sitio en vivo (~590 peticiones, 287 páginas del sitemap), revisión del código de vistas, modelos,
plantillas y comandos, integridad de la base de producción, y crons y configuración del servidor.

Cada hallazgo indica cómo se verificó: **reproducido** (se provocó el error en vivo o con el
`Client` de Django contra producción), **medido** (consulta a la base) o **leído** (solo código).

## Resumen

El sitio está sano en lo que ve Google: las 287 páginas del sitemap responden 200, canonical y
hreflang cuadran, el JSON-LD de esas páginas parsea y no hay restos de plantilla. En 7 días solo
hubo 4 respuestas 500, todas explicadas.

Los problemas reales están en los bordes: parámetros que no se validan y dan 500, la IP del
cliente que se puede falsear, consultas de más en los listados, datos sucios (coordenadas,
duplicados, precios) y textos en español en `/en/`.

| Gravedad | Hallazgos |
|---|---|
| Alta | 6 |
| Media | 13 |
| Baja | 10 |

## Alta

1. **`/api/v1/places/<slug>/` da 500 en todas las fichas.** `select_related("comuna")`, pero
   `comuna` es una propiedad, no una FK (`explorer/api_v1.py:115`). *Reproducido.* Ya está
   arreglado en la copia local (sin commit ni deploy).
2. **`/lugares/?comuna=abc` y `/en/places/?comuna=abc` dan 500.** `comuna_osm_id` es entero y el
   valor llega sin validar (`views.py:685`, también 916). `_query_limpia` lo deja pasar porque
   `comuna` está en la lista blanca. *Reproducido.*
3. **`/api/semantic-search/?top=abc` o `top=-1` dan 500** (`int()` sin `try`; `qs[:-1]`), y
   `top=100000` devuelve todo con una consulta de foto por lugar (`views.py:2623`). *Reproducido.*
4. **Coordenadas en Asia en una ficha indexable.** `don-carlos` (Laureles) está en
   (25.39, 62.61): mapa, distancia y `geo` del JSON-LD mal. Dos fichas no indexables comparten el
   mismo punto (`ke-parche`, `super-picadas-y-perritos`) y tres caen fuera del valle. *Medido.*
5. **La IP del cliente se puede falsear.** La app toma el primer valor de `X-Forwarded-For`
   (`views.py:81` y `2486`, la segunda pisa a la primera), y el nginx de producción no fija
   `X-Real-IP` ni limpia esa cabecera. Consecuencias: todos los `@rate_limit` se saltan cambiando
   la cabecera, y en `newsletter_subscribe` un `X-Forwarded-For: foo` intenta guardar "foo" en una
   columna `inet` y da 500. *Leído; config de nginx comprobada.* Arreglo: leer `CF-Connecting-IP`
   (el tráfico entra por Cloudflare) y validar con `ipaddress`.
6. **El hub de enriquecimiento puede pisar horarios semanales con el estado del momento.**
   `import_medellin_enrich._refresh_place` copia `hours_text` a `horario_texto` sin mirar qué es;
   en los JSON de galería suele ser "Abierto · Cierra a las 9 p.m.". El hub corre cada 20 s por
   cron. Hoy hay 0 horarios así (los borró `completar_fichas_maps`), pero volverán con el próximo
   lote. *Leído; log del hub revisado.* Arreglo: ignorar texto que case `HORARIO_INSTANTANEO`.

## Media

7. **N+1 de fotos en los listados.** `Foto` no tiene `Meta.ordering`, así que `fotos.first()`
   ordena por `pk`, ignora el prefetch y consulta. `/lugares/?tipo=bar`: 28 consultas, 25 de
   fotos; `/guias/`: 13 de fotos. También en las vistas AJAX (`views.py:1749, 1923, 2340, 2653`).
   *Medido.* Arreglo: `ordering = ["id"]` en `Foto.Meta` o `cached_fotos` en todas partes.
8. **El sitemap de lugares carga las fotos de 5.000 lugares por página.** `indexables()` hereda el
   `prefetch_related("fotos")` del manager y el sitemap no las usa (`sitemaps.py:47`). Es el
   mismo riesgo de timeout que ya hizo quitar el sitemap de imágenes. *Leído.* Arreglo:
   `.prefetch_related(None)`.
9. **El JSON-LD `ItemList` del listado se rompe con la búsqueda.** `titulo_pagina` y
   `descripcion_pagina` van sin `escapejs` (`components/schema_org.html:93-94`). `?q=a\` produce
   JSON inválido y las comillas salen como `&quot;`. *Reproducido.*
10. **Posible XSS en la guía.** `markers_json|safe` con `json.dumps` sin escapar `</`
    (`views.py:3125`, `guias/guia_detail.html:180`). Un nombre de lugar con `</script>` ejecutaría
    código. Los nombres vienen de Google o del admin. *Leído.* Arreglo: `json_script`.
11. **XSS en el DOM del listado.** `/api/places-filter/?tipo=<script>` devuelve
    `"mensaje": "No encontramos <script>"` y el JS lo inserta con `.html()`. Hoy `tipo` no sale de
    la URL directamente, así que el riesgo es bajo, pero el sumidero existe. *Reproducido (la API).*
12. **Newsletter.** Está exento de CSRF y reactiva correos dados de baja (`activo=True`,
    `confirmado=True`) sin doble confirmación. Un correo de 255–320 caracteres pasa
    `validate_email` y revienta `varchar(254)` con 500 (`views.py:3014-3051`). *Leído.*
13. **El límite de traducciones es global.** `translate_review_api` cuenta por `REMOTE_ADDR`, que
    detrás del socket de nginx es el mismo para todos: 20 traducciones por minuto para todo el
    sitio (`views.py:2910`). *Leído.*
14. **`/semantic-search/` no tiene límite de peticiones y paga Vertex en cada GET.** Tampoco
    cachea el embedding ni excluye los tipos que el buscador oculta (`views.py:2671`). *Leído.*
15. **Fichas duplicadas con sufijo `-N`.** 45 pares a menos de 150 m con nombre casi igual; en 23
    las dos son indexables (`qchimba`/`qchimba-1`, `che-paco`/`che-paco-1`, `arka-619`/`arka-619-1`).
    Contenido duplicado ante Google. *Medido.*
16. **Precios de carta erróneos.** 96 platos a $0 (casi todos de Mimos), 59 por debajo de $500
    ("Limonadas $10") y "Bandeja con Carne de Res" a $15.900.000 en `restaurante-la-palenquera`.
    Se ven en la ficha y ahora entran en el rango de precios y en `hasMenu`. *Medido.*
17. **Miniaturas rotas.** Cerca del 2,5 % de las miniaturas `tourism/images/thumb/…` de fichas
    indexables dan 404 (2 de 80 en la muestra; ~1.000 de 40.750 si la proporción se mantiene).
    Ejemplo: `discoteca-el-suave-salsa-sabordisc`, 3 de 5 miniaturas. *Medido.* Además, 14.190
    fotos de indexables no tienen variantes mediana ni miniatura y sirven el original.
18. **Español en `/en/`.**
    - "Lugares en {zona}" en el 100 % de las fichas EN: la cadena que añadí en P1 no está en el `.po`.
    - "Pedir en Rappi" en el 45 % (`models.py:1393`, sin `_()`).
    - "Abierto 24 horas" en 2 de 100 horarios.
    - `_format_horarios` y `_get_caracteristicas` devuelven días y rasgos en español en `api_v1`.
    - `lugares_comuna_ajax` trae fijo el texto "esta zona" (`views.py:2604`).
    - Las secciones de carta salen en español dentro del resumen EN.
    *Reproducido.*
19. **Filtros del listado indexables.** `?tipo=…`, `?delivery=true` y `?cerca=1&lat=…` salen con
    `index, follow` (solo `q` y `page` ponen noindex), y cada ficha enlaza a
    `/lugares/?cerca=1&lat=X&lng=Y&tipo=Z`: miles de URLs únicas rastreables. Con un tipo
    inventado, el texto del usuario va al `<title>` de una página indexable
    (`?tipo=foo-bar` → "Mejores Foo-Bar en Medellín"). El canonical a `/lugares/` lo mitiga.
    *Reproducido.*

## Baja

20. **Página 404 por defecto de Django.** Son 179 bytes en inglés, sin marca ni navegación.
    Afecta a fichas, zonas y guías que no existen.
21. **Dirección duplicada** en el 38 % de las fichas: "…El Poblado, Medellín, El Poblado,
    Medellín, Antioquia". Ya estaba en el P3 16 de la auditoría SEO.
22. **Guía con un lugar cerrado.** `rooftops-con-vista-al-valle` incluye `panorama-rooftop-bar`
    ("Cerrado permanentemente"). Además hay 4 guías publicadas con menos de 5 lugares: Sabaneta,
    Belén, Envigado y Guatapé.
23. **`radio` sin acotar en "Cerca de mí".** `radio=1e9` recorre toda la tabla y `radio=-inf` da
    `OverflowError` (`views.py:2255, 2360`). *Leído.*
24. **Selector de idioma.** En `/en/semantic-search/` el enlace ES va a `/busqueda-semantica/`
    (404). La regex `rese[ñ%C3%B1]as` es una clase de un solo carácter y nunca casa con la ruta
    codificada (`templatetags/form_tags.py:44,46,84`). *Leído.*
25. **Las APIs AJAX devuelven `str(e)`.** `filtros_ajax_view` acepta cualquier lookup del ORM en
    `caracteristica` y el 500 lista los campos del modelo (`views.py:1741`). `?area=abc` da 500
    en vez de 400. *Leído.*
26. **`translate_review_api` da 500** con un cuerpo JSON que no es un objeto (`[1]`, `"x"`)
    (`views.py:2903`). *Leído.*
27. **Reseñas con tipos raros.** `citas_resenas` (P2) y `PlaceReviewsView` asumen que `rating` es
    número y `publishTime` texto: un "4.5" o un timestamp entero tumbaría la ficha. Hoy no hay
    datos así (todo es lista de dicts válida). Hay 231 indexables con reseñas sin texto, que la
    cita ya filtra. *Leído; datos medidos.*
28. **`/en/contacto/`, `/en/politica-de-privacidad/` y `/en/terminos-y-condiciones/`** son
    indexables, con slug en español y fuera del sitemap EN.
29. **Comando viejo roto y peligroso.** `importar_poligonos_especificos` llama a
    `ensure_both_geoms`, que no existe, y antes borra todas las zonas.

## Revisado y bien

- **Sitemap:** 9 archivos y 9.130 URLs. En las 287 páginas muestreadas, todo da 200 sin
  redirecciones y canonical y hreflang son correctos, sin noindex.
- **JSON-LD y plantillas:** el JSON-LD de la ficha no deja comas colgando y no hay restos de
  plantilla.
- **Fotos:** ninguna ficha con `tiene_fotos` está sin `Foto` y no hay fotos huérfanas. Una
  muestra de 61 originales, medianas y miniaturas dio 200.
- **Datos:** slugs únicos; ratings en 1–5; `item_count` cuadra en las 2.008 cartas;
  `contenido_actualizado` sin nulos ni fechas futuras; todas las zonas con slug único; ninguna
  indexable sin zona.
- **Seguridad y configuración:** `DEBUG=False`, HSTS con preload, cookies `Secure`,
  `X-Frame-Options: DENY`, `/__debug__/` da 404 y no hay redirecciones abiertas.
- **500 de `?cerca=` del 28 oct:** fueron 3 en el mismo segundo (un reinicio) y no se reproducen.
- **404 de `/lugar/…/reseñas/`:** ~2.300 de MJ12bot pidiendo la ñ en latin-1. Nuestro HTML
  enlaza bien (`rese%C3%B1as`).
- **404 de `/lugares/<zona>/?page=…`:** escaneos de inyección SQL. Responder 404 es correcto.

## Orden de arreglo

| Lote | Hallazgos | Esfuerzo |
|---|---|---|
| 1 — los 500 y la IP | 1, 2, 3, 5, 12 (largo del correo), 23, 25, 26 | medio día |
| 2 — datos | 4, 6, 16, 22, y decidir 15 (fusionar o noindex) | medio día |
| 3 — HTML y JSON | 9, 10, 11, 18, 19 | medio día |
| 4 — rendimiento | 7, 8, 17 | medio día |
| 5 — resto | 12 (reactivación), 13, 14, 20, 24, 28, 29 | un día |

## Estado

**Lote 1, arreglado en código (31 oct, sin desplegar).** Probado con el `Client` de Django en una
copia aislada en el servidor contra la base de producción.

- 1: sin `select_related("comuna")`; la API de ficha responde 200.
- 2: `comuna` se valida como entero; `?comuna=abc` da 200 y no filtra.
- 3: `top` se acota a 1–50 (12 si no es un número).
- 5: `get_client_ip` lee `CF-Connecting-IP` validado con `ipaddress`, si no `REMOTE_ADDR`, y si no
  hay ninguna válida devuelve `None`. Se quitó la segunda definición, que pisaba a la primera.
  También lo usa el límite de traducciones, con lo que el 13 queda resuelto.
- 12 (largo): un correo de más de 254 caracteres da 400.
- 23: `radio` se acota a 0,5–15 km; `inf` y `nan` dan 400.
- 25: `caracteristica` solo acepta `FILTROS_ESPECIALES` y `area` tiene que ser un entero (400
  si no). Las APIs AJAX ya no devuelven `str(e)`: registran el error y responden "Error en la búsqueda".
- 26: un cuerpo JSON que no es un objeto da 400 ("Texto vacío").

Queda: quien llegue directo al origen (sin pasar por Cloudflare) puede poner su propio
`CF-Connecting-IP`, porque el puerto 443 está abierto a todo el mundo. Para cerrarlo hay que dejar
pasar solo las IP de Cloudflare en ufw o usar `real_ip` de nginx con sus rangos.

**Hallazgo nuevo (30): la búsqueda semántica está caída en producción.** La cuenta de servicio
`vertex-express@vivemedellin.iam.gserviceaccount.com` de `vertex.json` ya no existe
(`invalid_grant: account not found`). `/api/semantic-search/` da 500 y `/semantic-search/` sale
sin resultados. Hace falta una clave nueva con permiso de Vertex AI.

**Lote 3, arreglado en código (31 oct, sin desplegar).** Probado con el `Client` contra la base de
producción en una copia aislada.

- 9: `name`, `description`, `url` e `image` del JSON-LD con `escapejs`; el `ItemList` parsea con
  `?q=a\` y con `"></script>`.
- 10: el mapa de la guía lee los puntos de `json_script`, sin `|safe`.
- 11: el mensaje de la API se escapa antes de ir al HTML en el listado y en la home.
- 18: 17 traducciones nuevas ("Lugares en…", "Pedir en Rappi", "Abierto 24 horas", rasgos del
  lugar, "esta zona", "En la guía «…»"…). Los rasgos y los días de la API salen en el idioma
  pedido. Quedan en español los nombres de las secciones de carta, que vienen así de Rappi.
- 19: cualquier filtro del listado (tipo, característica, cerca, búsqueda) lleva `noindex`;
  `robots.txt` bloquea `lat=` y `cerca=`; el enlace "Más … cerca" de la ficha va con `nofollow`.
