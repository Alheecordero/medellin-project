# Auditoría SEO e IA — 1 nov 2026

Segunda pasada tras `docs/AUDITORIA_SEO_2026-10-31.md`. Rastreo de 818 URLs contra el origen,
14 días de logs de nginx, Search Console por API, Cloudflare por API y revisión del dominio
anterior. Lo único que se cambió está en "Cambios aplicados hoy".

## Resumen

1. **El tráfico de antes estaba en `vivemedellin.co`, y ese dominio ya no apunta al sitio.** Se
   creó el 4 jul 2025. Desde el 10 sep 2026 tiene los DNS de ParkLogic (parking), sirve
   `Disallow: /` y lleva `clientRenewProhibited`: es el patrón de un dominio vencido en GoDaddy.
   Los 14 meses de enlaces y autoridad se quedaron allí. `.net` empezó de cero el 9 ago 2026.
2. **`.net` casi no tiene tráfico orgánico real.** En los logs hay 40.839 entradas con referer de
   Google en 14 días, contra 0 clics en Search Console. Son scrapers: referer falso
   `https://www.google.com/`, Chrome 132/133 y consultas `?cerca=1&lat=…&lng=…&tipo=…`. Desde la
   regla de Cloudflare de hoy bajaron de ~200 cada 10 min a 1.
3. **Google rastrea bien pero no indexa.** Las fichas que tenían impresiones están en
   "Rastreada: actualmente sin indexar" y `/lugares/` y `/guias/` siguen sin conocerse. Las causas
   probables: contenido derivado de Maps a escala, valoraciones de Google marcadas como propias y
   ninguna señal de autoría.

## Cifras

| Indicador | Valor |
|---|---|
| Search Console | datos desde 19 sep; máx. 2 clics/día; 0–3 impresiones/día desde el 17 oct; 13 consultas en 2 meses |
| Sitemaps | 12 secciones válidas; 2.998 fichas por idioma (antes 4.796) |
| Rastreo de 818 URLs | 0 URLs del sitemap con `noindex`, canonical ajena o error; 1 H1 por página; `lang` correcto |
| Velocidad en origen | TTFB + descarga mediana 0,11 s; HTML de ficha 129 KB (p90 177 KB); `/lugares/` 227 KB |
| Googlebot, 14 días | 6.812 peticiones a rutas de ViveMedellín, 94 % con 200; 2.037 el 31 oct tras el cambio de sitemap |
| Otros bots, 14 días | PerplexityBot 373.408 · Amazonbot 103.163 · Ahrefs/Semrush 60.152 · Bytespider 31.026 · Applebot 18.293 · Bingbot 8.688 · OAI-SearchBot 2.076 · ChatGPT-User 837 |
| Imágenes sin `alt` | 13.475 de 29.613 (45 %); 53 % en galerías de ficha; 100 % en tarjetas de home y guías |
| Fichas indexables enlazadas desde home, listado, zonas, guías o Qué hacer | 729 de 2.998 (cota inferior: el listado se rastreó en las páginas 1, 2, 3, 10 y 50) |

## Lo que ya está bien

Robots, sitemaps, canónicos y `hreflang` (es, en, x-default, recíprocos) están correctos.
Todas las páginas tienen título, descripción, Open Graph y Twitter Card. Las fichas tienen
`BreadcrumbList`, horario estructurado y `Menu` con platos en 220 de 426. La foto principal
tiene `preload` y no es lazy. El `noindex` coincide con el sitemap. Cloudflare no registra ningún desafío ni bloqueo a
Googlebot. Entre las 07:00 y las 07:15 (hora de España), con todas las reglas activas, pasaron
con 200 OAI-SearchBot (48), Applebot (22) y Bingbot (10).

El log de nginx mezcla los sitios del servidor, así que los conteos por bot de esta auditoría
se confirmaron en las analíticas de Cloudflare de la zona.

## Hallazgos priorizados

### P0 — deciden si el sitio puede crecer

1. **Recuperar `vivemedellin.co` (tarea del dueño).** Entrar en GoDaddy:
   - si el dominio sigue en la cuenta, renovarlo y pasar los DNS a Cloudflare;
   - si no está, buscarlo en GoDaddy Auctions y recomprarlo.

   Después: 301 ruta por ruta (`.co/lugares/x/` → `.net/lugares/x/`), verificar `.co` en Search
   Console y usar "Cambio de dirección". Es la palanca más rápida: recupera la autoridad sin
   esperar meses.
2. **Valoraciones de Google marcadas como propias.** 416 de 426 fichas rastreadas declaran
   `aggregateRating` con la nota y el número de reseñas de Google Maps. También lo hacen los
   `ItemList` del listado y de Qué hacer. Las pautas de Google piden que las valoraciones se
   recojan de los usuarios del propio sitio. Marcar las de otro sitio es motivo de acción manual
   por datos estructurados engañosos y resta confianza.
   **Arreglo:** quitar `aggregateRating` del JSON-LD y mantener la nota visible con "según Google
   Maps". El dueño debe revisar Search Console › Seguridad y acciones manuales.
3. **La verificación a todas las visitas también frena a las personas.** La regla copiada de
   menuradar desafía a todo visitante humano nuevo; en el navegador salió la casilla "Verify you
   are human". Funciona contra los scrapers, pero castiga a quien llega desde Google.
   **Propuesta:** reemplazarla por una regla dirigida. Desafiar solo:
   - las URLs con `lat=` o `cerca=`;
   - los Chrome antiguos (`Chrome/12`, `Chrome/13`);
   - las peticiones sin `Accept-Language`.

   Mantener la regla de datacenters. Medir una semana y comparar.

### P1 — descubrimiento y relevancia

4. **No hay páginas indexables por categoría.** "Bares en Medellín", "restaurantes en El Poblado"
   o "cafés en Laureles" solo existen como filtros con `noindex` (`/lugares/?tipo=bar`). En
   Search Console, "bares en medellin" aparece en la posición 68–70. Además, cada ficha enlaza 9
   URLs de filtro con `noindex`.
   **Arreglo:** crear páginas de categoría (`/lugares/bares/`) y de categoría × zona
   (`/lugares/el-poblado/bares/`) cuando haya ≥ 8 fichas indexables: 76 combinaciones según la
   auditoría anterior. Cada una con un párrafo propio, rango de precios desde las cartas e
   `ItemList`. Las fichas pasan a enlazar a estas páginas en lugar de a los filtros.
5. **Enlazado interno débil.** Solo ~24 % de las fichas indexables reciben un enlace desde una
   página central; el resto depende del sitemap y de "Similares". El punto 4 lo resuelve.
6. **Títulos y descripciones.**
   - **Guías de zona:** "Sabaneta | ViveMedellín" (también el `headline` del Article), igual en
     inglés. Proponer "Sabaneta: dónde comer y qué hacer" / "Sabaneta: where to eat and what to do".
   - **Listado paginado:** el mismo título y la misma descripción en todas las páginas. La
     descripción además está rota: "…ofrece la ciudad Ratings de Google…".
   - **Home y listado:** venden "ratings de Google", que le dice a Google que el contenido es suyo.
     Mejor destacar lo propio: cartas con precios, guías, zonas.
   - **Fichas:** 301 de 426 títulos pasan de 65 caracteres y 490 descripciones pasan de 165.
     Las sucursales repiten título (Papa Johns 1 y 2): añadir el barrio.
7. **Autoría y entidad (E-E-A-T).** Las guías tienen como autor una `Organization`; no hay
   ninguna persona. La `Organization` no tiene `sameAs` (redes sociales). "Nosotros" describe un
   "directorio", mientras `/guias/` promete "recomendaciones personales de un local".
   **Arreglo:** autor real (`Person` con su página y foto), perfiles sociales en `sameAs`, fecha
   de la visita en cada guía y una sección "cómo elegimos".

### P2 — técnico

8. **`alt` en imágenes.** Generarlo como "Nombre — tipo en zona" en galerías, tarjetas y guías.
9. **nginx sin IP real.** El bloque de `vivemedellin` no incluye `cloudflare-real-ip.conf` (sí lo
   hace inicialegal). `$remote_addr` es el nodo de Cloudflare, así que el límite de 30 r/s lo
   comparten todos los usuarios de ese nodo, y el log no permite verificar Googlebot ni contar
   visitantes. Incluirlo y añadir `$host` al formato del log.
10. **Bloqueo geográfico.** `vivemedellin-geo-block.conf` bloquea Venezuela, Filipinas, Indonesia
    y otros 26 países. Venezuela es público natural de una guía de Medellín. Revisar la lista.
11. **Rendimiento.** Siguen pendientes los 10 CSS externos que bloquean el render y el listado de
    227 KB. Hoy no se pudieron medir los Core Web Vitals: se agotó la cuota de PageSpeed y el
    navegador recibe el desafío. Revisar el informe de Core Web Vitals en Search Console.
12. **Bing e IndexNow.** ChatGPT y Copilot se apoyan en el índice de Bing. `BingSiteAuth.xml`
    existe; falta avisar a IndexNow cuando se publica o cambia una ficha o una guía.
13. **Menores.** Qué hacer en inglés usa slugs en español (`/en/things-to-do/lugares-emblematicos/`);
    sin `site.webmanifest`; sin `llms.txt`.

## IA: cómo aparecer en ChatGPT, Perplexity, Claude y Google AI

| Buscador | Qué necesita | Estado |
|---|---|---|
| Google AI Overviews / AI Mode | Estar indexado (Googlebot) | Pasa, pero casi nada indexado |
| Gemini (app) | `Google-Extended` | Bloqueado en el robots.txt de Cloudflare (decisión del dueño) |
| ChatGPT search | OAI-SearchBot + índice de Bing | Pasan: 508 peticiones con 200 en 6 h |
| Perplexity | PerplexityBot | 373.408 peticiones en 14 días, sobre todo en la trampa de paginación corregida el 31 oct; 0 en las últimas 6 h |
| Claude | Claude-SearchBot | 0 visitas en las últimas 6 h; sin bloqueo registrado |

Qué hace que una IA cite una página: datos que nadie más tiene, dichos de forma directa y
verificable. ViveMedellín tiene uno: **72.410 platos con precio de 2.008 cartas**.

- **Página de datos "Cuánto cuesta comer en Medellín 2026":** mediana por zona, por tipo y por
  plato (bandeja paisa, hamburguesa, café). Es citable por IA y atrae enlaces.
- **Bloques de preguntas en las páginas centrales,** con respuestas de 2–3 frases ("¿Cuánto cuesta
  cenar en Provenza?", "¿Qué hacer en Medellín en un día?").
- **Mantener la `Content-Signal`** `search=yes, ai-train=no`: permite que te citen sin permitir
  el entrenamiento.

## Cambios aplicados hoy

- **Índice:** las fichas sin carta necesitan rating 4,3 con 300 reseñas (antes 4,0 con 50):
  4.796 → 2.998 por idioma (`4a26883f`). Sitemaps reenviados, con `sitemap-que-hacer.xml`.
- **AdSense apagado** con `ADSENSE_ENABLED=False` (`6b46919a`, `41d5ec6f`).
- **Cloudflare, como menuradar:**
  - bloqueo de crawlers SEO y scrapers;
  - desafío al tráfico de datacenters;
  - verificación a todas las visitas, con excepciones para la API, los estáticos, los sitemaps y
    las vistas previas de WhatsApp y redes;
  - robots.txt gestionado con `ai-train=no`;
  - `ai_bots_protection` en `only_on_ad_pages`, igual que menuradar. Estuvo en `block` unos
    20 minutos. Hoy solo bloquea crawlers de entrenamiento: Reflectionbot, PetalBot y
    Amazonbot.

## Qué tiene que hacer el dueño

1. GoDaddy: recuperar `vivemedellin.co` (P0 1).
2. Search Console:
   - revisar Acciones manuales y el informe de Core Web Vitals;
   - pedir indexación de home, `/lugares/`, `/guias/`, `/que-hacer/` y las guías principales
     (unas 10 al día).
3. Decidir entre la verificación a todas las visitas y la regla dirigida (P0 3).
4. Decidir si Gemini puede usar el contenido (`Google-Extended`).
5. Identidad: nombre y foto del autor, redes sociales del proyecto, comentarios de las 8 guías
   en borrador.
6. Enlaces: sello "Recomendado en ViveMedellín" para los lugares con carta, r/medellin, grupos de
   expats, blogs de viaje.

## Orden de trabajo

| Semana | Trabajo |
|---|---|
| 1 | Dominio `.co` y 301. Quitar `aggregateRating`. Títulos y descripciones (P1 6). `alt`. IP real en nginx. Regla de Cloudflare dirigida. |
| 2 | Páginas de categoría y categoría × zona, con enlazado desde las fichas (P1 4–5). IndexNow. |
| 3 | Autoría y entidad (P1 7). Página de precios. Preguntas en las páginas centrales. Publicar guías. |
| 4 | Medir en Search Console por sitemap; ajustar la vara del índice según lo que se indexe. |

## Metas a 30 días

- `.co` redirigiendo a `.net` con 301 por ruta y el cambio de dirección hecho.
- 0 `aggregateRating` con valoraciones de terceros; sin acciones manuales.
- `/lugares/`, `/guias/`, `/que-hacer/` y ≥ 20 páginas de categoría conocidas por Google.
- ≥ 300 fichas indexadas e impresiones diarias por encima de las de septiembre (~20).
