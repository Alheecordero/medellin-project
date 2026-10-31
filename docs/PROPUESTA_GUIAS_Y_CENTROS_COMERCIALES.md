# Propuesta: reorganizar Guías y añadir centros comerciales — 31 oct 2026

Datos medidos en la base de producción el 31 oct. Nada de esto está implementado.

## Qué hay hoy

- 12 guías publicadas, en 5 categorías: `sector`, `audiencia`, `actividad`, `daytrip` y
  `gastronomia`.
- `/guias/` muestra una sola rejilla plana. La vista agrupa las guías por categoría
  (`categorias`), pero la plantilla no usa ese agrupamiento.
- Ningún centro comercial existe como ficha: `Places` no tiene `shopping_mall`.

| Categoría | Guías | Lugares |
|---|---|---|
| actividad | Rooftops con vista al valle · Noche en Laureles y La 70 · Bares en El Poblado | 11 · 6 · 7 |
| audiencia | Top de lugares LGBTQ | 5 |
| daytrip | Un día en Guatapé | 4 |
| gastronomia | Dónde comer en Medellín · Comer en Laureles · Comer en El Poblado | 15 · 5 · 5 |
| sector | Envigado · Belén · Sabaneta · Centro de día | 4 · 3 · 3 · 5 |

## Por qué no tiene sentido lógico

1. **Las categorías mezclan dos preguntas.** "¿Dónde?" (sector) y "¿qué plan?" (actividad,
   gastronomía) son ejes distintos, pero están al mismo nivel. Por eso El Poblado aparece en dos
   categorías ("Bares en El Poblado" en actividad y "Comer en El Poblado" en gastronomía), y
   Laureles igual. Para ver todo lo de una zona hay que revisar las 12 tarjetas.
2. **Las guías de "sector" son las más flojas.** Tienen 3–4 lugares y se pisan con las de
   gastronomía de la misma zona. Tres de las cuatro guías con menos de 5 lugares son de este tipo.
3. **"Audiencia" tiene una sola guía.** Es una categoría vacía disfrazada.
4. **No hay sitio para lo que no es un plan curado**, como "dónde comer en Viva Envigado". Una
   guía hoy es un ranking personal, y un centro comercial no es eso.

## Estructura propuesta

`/guias/` con cuatro bloques, cada uno con su propia lógica:

| Bloque | Responde a | Qué contiene | Cómo se hace |
|---|---|---|---|
| **Por plan** | "Quiero salir de noche / un rooftop / comer bien" | Rooftops, Vida nocturna, LGBTQ, Dónde comer en Medellín | Curado (como hoy) |
| **Por zona** | "Voy a estar en Laureles" | Una tarjeta por zona; dentro, sus guías (comer, noche, de día) y el enlace al listado de la zona | Curado; agrupa lo que ya existe |
| **Centros comerciales** | "Estoy en el Tesoro, ¿dónde como?" | Un centro comercial por página, con sus lugares agrupados por tipo | Automático, con nota opcional |
| **Escapadas** | "Un día fuera de Medellín" | Guatapé (y las que vengan) | Curado |

Reparto de las 12 guías actuales:

| Guía | Hoy | Propuesta |
|---|---|---|
| Rooftops con vista al valle | actividad | Por plan |
| Top de lugares LGBTQ | audiencia | Por plan |
| Dónde comer en Medellín | gastronomia | Por plan |
| Bares en El Poblado, Comer en El Poblado | actividad, gastronomia | Por zona → El Poblado |
| Noche en Laureles y La 70, Comer en Laureles | actividad, gastronomia | Por zona → Laureles |
| Envigado, Belén, Sabaneta | sector | Por zona; se muestran cuando lleguen a 5 lugares (hasta entonces, `noindex` y fuera del índice) |
| Centro de día | sector | Por zona → La Candelaria |
| Un día en Guatapé | daytrip | Escapadas |

En el modelo, el cambio es pequeño:
- `categoria` pasa a tener `plan`, `zona`, `centro_comercial` y `escapada`.
- La zona ya está en `zona` (FK a `RegionOSM`).
- Se añade un `tema` corto (comer, noche, de día) para ordenar las guías dentro de una zona.
- Una migración de datos aplica la tabla de arriba.
- Las URLs `/guias/<slug>/` no cambian.

## Centros comerciales

### Los datos

- **718 fichas publicadas están dentro de 73 polígonos de centro comercial de OSM**
  (`planet_osm_polygon.shop = 'mall'`). Hay 31 centros con 8 fichas o más.
- **Los que más fichas tienen:** Viva Envigado 51, Unicentro 35, Arkadia 33, El Tesoro 33,
  Florida 28, Premium Plaza 26, San Lucas Plaza 25, Oviedo 25, Santafé 23, San Diego 22 y
  Mayorca (etapas I y II) 40.
- **Las direcciones** de 344 fichas mencionan un "C.C." o un "Centro Comercial". Sirven de
  respaldo para los locales cuyo punto cae justo fuera del polígono.

### Por qué un tipo propio y no una guía más

- **Una guía es una opinión con ranking; un centro comercial es un contenedor.** Su página
  responde a una pregunta práctica ("ya estoy aquí, ¿qué hay para comer?"), y su lista sale sola
  de la geometría, sin curar lugar a lugar.
- **Mezclarlos en la misma rejilla** es justo lo que hoy confunde.

### Cómo funcionaría

- **Modelo `CentroComercial`:**
  - Campos: `osm_id`, `nombre`, `slug`, `zona` (FK a `RegionOSM`), `geom`, `nota` y
    `nota_en` (opcionales) y `publicado`.
  - Los lugares no se guardan a mano: se calculan con `ST_Contains`, más la coincidencia de
    dirección como respaldo.
- **Comando `importar_centros_comerciales`:**
  - Lee los polígonos de OSM del valle y une las etapas (Mayorca I + II).
  - Corrige los nombres de OSM: "Unicentro Medelllín", "Centro Comercial ARKADIA".
  - Asigna la zona. Es idempotente y no borra nada.
- **Páginas:**
  - `/guias/centros-comerciales/`: centros agrupados por zona, con el número de lugares de
    cada uno.
  - `/guias/centros-comerciales/<slug>/`: nota corta, mapa del polígono y lugares agrupados
    en restaurantes, comidas rápidas, cafés y postres, y bares, con el orden de siempre
    (destacados y `weighted_rating`).
- **En la ficha del lugar:** un chip "Está en Viva Envigado" que enlaza a la página del
  centro. Son 718 enlaces internos hacia esas páginas.
- **Indexación:**
  - Se indexa solo si el centro tiene 8 fichas indexables o más; si no, `noindex` y fuera del
    sitemap.
  - Para empezar, los 10–12 más grandes, con una nota de 2–3 frases escrita a mano.
  - El resto, sin nota, queda en `noindex` hasta tenerla. Así no publicamos 31 páginas casi
    iguales.
- **JSON-LD:** `ShoppingCenter` con `containsPlace`, más el `ItemList` de los lugares.

### "Y etc."

El mismo mecanismo de contenedor sirve para plazas de mercado y mercados gastronómicos, pero hoy
los datos son pocos:

| Lugar | Fichas dentro |
|---|---|
| Central Mayorista | 20 |
| Mercado del Río | 7 |
| Plaza Minorista | 7 |
| Plaza de mercado de Envigado | 5 |

Recomiendo dejar el modelo listo para un `tipo` (centro comercial o mercado), lanzar solo
centros comerciales y añadir "Mercados y plazas" cuando haya al menos 3 con 8 fichas o más.

## Fases

| Fase | Qué | Esfuerzo |
|---|---|---|
| 1 | Índice de guías en los cuatro bloques, migración de categorías, guías flojas en `noindex` | medio día |
| 2 | `CentroComercial`, comando de importación, hub y página por centro, chip en la ficha, sitemap | 1–2 días |
| 3 | Notas escritas para los 10–12 centros principales | tuyo; yo propongo borradores |
| 4 | Mercados y plazas, cuando haya datos | medio día |

## Decisiones que son tuyas

1. **¿Dónde viven las páginas de centros comerciales?** Recomiendo `/guias/centros-comerciales/`,
   dentro de Guías, para que el bloque tenga sentido. La alternativa es `/centros-comerciales/`
   en la raíz.
2. **¿Las guías de Envigado, Belén y Sabaneta** se completan hasta 5 lugares o se fusionan en su
   zona?
3. **¿Quién escribe las notas** de los centros principales?

## Qué no pude medir

- **Demanda de búsqueda:** Search Console tiene 13 consultas en 90 días, ninguna sobre centros
  comerciales. La apuesta se basa en que la pregunta es común, no en datos propios.
- **Datos del centro comercial:** no tenemos horario, parqueadero ni sitio web, porque no hay
  ficha de Google de ninguno.

## Estado

**Fase 1 hecha en código (31 oct, sin desplegar).**
- `categoria` pasa a `plan`, `zona` o `escapada`, y hay un `tema` nuevo (comer, noche, de día).
  La migración 0040 reparte las 12 guías como en la tabla y pone zona a "Bares en El Poblado" y a
  "Noche en Laureles y La 70".
- `/guias/` sale en tres bloques: por plan, por zona (una tarjeta por zona con sus guías) y
  escapadas.
- Las guías con menos de 5 lugares (Envigado, Belén, Sabaneta) salen del índice, de la home y del
  sitemap, y llevan `noindex, follow`. Siguen abiertas para los enlaces desde las fichas.
- Cambio respecto a la propuesta: las escapadas no tienen mínimo. Guatapé tiene 4 paradas, que
  para el recorrido de un día está bien.
- Las portadas del índice salen del prefetch, sin una consulta por tarjeta.

Probado en el servidor sin escribir en la base: la lógica de la migración sobre copias en memoria
de las guías reales, y la plantilla del índice renderizada en español e inglés. La migración
aplicada, la vista con sus consultas, el sitemap y el `noindex` de la ficha de guía solo se
pueden comprobar al desplegar.

**Fase 2 hecha en código (31 oct, sin desplegar).**
- Modelo `CentroComercial` (migración 0041) y `Places.centro_comercial`. El comando
  `importar_centros_comerciales` lee los polígonos `shop=mall` de OSM, une etapas (Mayorca I + II),
  limpia nombres y asigna lugares: 30 centros con 8 lugares o más, 579 lugares asignados.
  `publicar_pendientes_enriquecidos` asigna el centro a los lugares nuevos.
- Páginas `/guias/centros-comerciales/` (por zona) y `/guias/centros-comerciales/<slug>/`
  (`/en/guides/malls/…`): resumen con números, mapa del polígono, lugares por tipo, otros centros
  de la zona y JSON-LD `ShoppingCenter`. Indexables los que tienen 8+ fichas indexables (14 hoy);
  el resto, `noindex`. Sitemaps `malls` y `malls-en`.
- La ficha de un lugar dice "Está en X" y enlaza al centro.
- `/guias/` rediseñado con `static/css/guias.css`: tarjetas con foto, zonas con etiquetas de tema,
  banda oscura de centros comerciales y escapada a lo ancho.
- Arreglo de paso: el filtro que dejaba fuera del buscador los nombres con "Centro Comercial"
  también sacaba restaurantes (Hatoviejo Viva Envigado, Crepes & Waffles Oviedo…). Ahora solo
  aplica a lo que no es comida, café o noche.

Sin notas escritas a mano todavía: la página usa el resumen automático. Los contadores se ponen
al día volviendo a correr el importador.
