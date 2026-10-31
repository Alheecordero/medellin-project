# Auditoría de datos — 31 oct 2026

Qué tenemos en la base de producción, qué está publicado y qué está sucio. Todo medido con
consultas de solo lectura; nada se cambió.

## Resumen

- **El sitio publica casi solo comida y noche.** De 12.749 fichas con fotos, 12.675 son
  restaurantes, cafés o bares. Turismo, cultura y alojamiento: 41 fichas.
- **Pero ya tenemos descargado mucho turismo.** En las fichas de Maps del valle hay 623
  atracciones y miradores, 130 museos, 770 parques, 85 agencias de tours y 2.151 hoteles. Casi
  nada está publicado, y la mayoría ya tiene fotos en R2.
- **Hay limpieza pendiente.** 101 pares de fichas duplicadas (56 con las dos indexables), 475
  lugares cerrados para siempre con la ficha abierta, 561 fichas viejas que nunca se refrescaron
  con Maps y 4.813 registros sin fotos que solo ocupan base.

## Qué hay en cada tabla

| Tabla | Qué es | Cantidad |
|---|---|---|
| `Places` | Fichas del sitio | 17.562 (12.749 con fotos, 4.565 indexables) |
| `GooglePlaceDetails` | Fichas de Maps descargadas | 89.098 (61.911 bien, 27.187 con error); 60.946 del valle |
| `PendingPlace` | Cola de lugares por publicar | 48.414 pendientes, 500 procesados, 1.157 descartados |
| `GooglePlaceId` | IDs descubiertos en los barridos | 97.212 |
| `PlacePartnerMenu` | Cartas de Rappi / DiDi | 2.008 |

Publicado por familia (con fotos / indexables): comida 10.054 / 3.759, noche 1.793 / 480,
café y postres 828 / 304, cultura y turismo 23 / 6, ocio 11 / 5, servicios 33 / 10.

## Turismo: lo que ya tenemos sin publicar

Fichas de Maps del valle, con calificación de 4,3 o más y 50 reseñas o más como filtro de calidad:

| Grupo | En Maps | 4,3+ y 50+ reseñas | Publicados | Los más reseñados |
|---|---|---|---|---|
| Atracciones y miradores | 623 | 165 | 2 | Piedra del Peñol (56.709), Plaza Botero (42.833), Tour Comuna 13 (41.278), Parque Arví, Plazoleta de los Zócalos |
| Museos | 130 | 40 | 1 | Jardín Botánico (45.061), Parque Explora, Museo El Castillo, Museo de Arte Moderno, Casa de la Memoria |
| Parques y naturaleza | 770 | 287 | 9 | Parque de Sabaneta, Parques del Río, Parque Arví, Parque de los Deseos, El Salado |
| Agencias y operadores de tours | 85 | 41 | 0 | Tours Guatapé SAS (2.330), Turismo en Medellín (1.904), Aquatour Guatapé, Graffitour, Fly Colombia (helicóptero) |
| Hoteles y hostales | 2.151 | 589 | 0 | Dann Carlton, Click Clack, Masaya, InterContinental |

Notas:

- Casi todas tienen 8–10 fotos ya subidas a R2, horario, teléfono y web.
- En la cola (`PendingPlace`) hay otros 3.159 de cultura y turismo, 2.225 de ocio y 2.045 de
  alojamiento sin ficha de Maps todavía.
- **"Agencias" exige cuidado al filtrar.** Una búsqueda por "turis" mete 80 "Tienda naturista";
  el filtro bueno es por categoría ("Agencia de viajes", "Agencia de excursiones…",
  "Operador turístico") o por tipo `travel_agency`.
- **La familia "ocio" está llena de ruido**: gimnasios, spas, esteticistas y centros
  comunitarios. Solo una parte sirve a un turista.
- **1.049 fichas de Maps tienen el estado del momento en la categoría** ("Cerrado · Abre a las
  9") y otras guardan ahí el número de reseñas ("(42,868)") o el precio ("GBP 60"). Es un fallo
  del scraper al leer la categoría; hay que reclasificarlas con `types` antes de publicar.

## Duplicados

- **101 pares con el mismo nombre a menos de 150 m; en 56 las dos fichas son indexables.**
  Ninguno comparte `place_id`: es el mismo negocio importado dos veces con dos IDs de Google
  distintos. Lo delata el número de reseñas, casi igual. Ejemplos:
  - `gabo` y `restaurante-gabomde-poblado`: 7.863 y 7.857 reseñas.
  - `papa-johns-pizza-5` y `papa-johns-pizza-1`: 3.045 las dos.
  - `picadero-la-mayoria` y `la-mayoria`: 2.533 las dos.
  - `rooftop-garden-resto-bar` y `rooftop-garden`: 2.324 las dos.
  - `chorizos-la-76-1` y `chorizos-la-76`: 1.138 las dos.
- **Slugs que no cuadran con el nombre.** Ejemplos: `azabache` y `angus-brangus-parrilla-bar`
  con el mismo nombre; `los-colores-plazoleta` con dos "Khushbu donde Sam". Son fichas que
  cambiaron de nombre en Maps y conservaron el slug viejo.
- **534 slugs terminan en -N y su slug base también existe.** La mayoría son sucursales
  legítimas de cadenas; los duplicados reales son los 101 de arriba.

## Cerrados y datos viejos

| Problema | Fichas | Efecto |
|---|---|---|
| Cerrados para siempre según Maps, con ficha abierta | 475 (1 en una guía: Panorama Rooftop) | Ya llevan `noindex`, pero el visitante llega a un sitio que no existe |
| Cerrados temporalmente | 9 | Nada lo avisa en la ficha |
| Publicados sin ficha de Maps (importación de 2025 sin refrescar) | 561 (207 indexables) | Horario, rating y fotos sin actualizar |
| Contenido sin actualizar en 6 meses | 971 | Datos posiblemente viejos |
| Sin fotos | 4.813 | Dan 404; solo ocupan base y confunden los conteos |
| Sin rating | 1.064 | — |
| Fuera del valle | 6 | Incluye `don-carlos` (coordenadas en Asia) |

Todas las fichas se crearon en 2025 salvo las 500 del lote de octubre de 2026.

## Recomendación

1. **Limpiar antes de crecer (medio día).**
   - Fusionar los 101 duplicados: el slug que se queda recibe un 301 del otro.
   - Marcar los 475 cerrados con un aviso visible y sacarlos de listados y guías, o devolver
     410 si no tienen tráfico.
   - Refrescar las 561 fichas viejas con el hub de enriquecimiento.
   - Borrar o archivar los 4.813 registros sin fotos (pide tu confirmación).
2. **Una sección "Qué hacer" con turismo (1–2 días).**
   - Publicar como fichas las 165 atracciones, 40 museos y los parques útiles (unos 100, sin
     canchas ni gimnasios) que pasan el filtro de calidad. Ya tienen fotos.
   - La ficha necesita una variante sin carta ni "pedir en Rappi".
   - Guías nuevas con ese material: "Qué hacer en Medellín", "Comuna 13", "Museos", "Miradores",
     y Guatapé ampliada con el Peñol y las agencias.
3. **Agencias de tours, como bloque propio.** Son 41 con buena reputación. Encajan como "Tours
   y excursiones" dentro de Guías, con el mismo patrón de los centros comerciales. Es también la
   vía más directa para monetizar con afiliados.
4. **Hoteles, más adelante.** Son 589 buenos, pero es otro producto (reservas y precios) que
   compite con Booking y Airbnb. Lo dejaría para cuando el sitio tenga tráfico.

## Estado

**Limpieza hecha en código (31 oct, sin desplegar).**
- Campos nuevos en `Places` (migración 0042): `fusionado_en` y `cerrado_permanente`. El manager
  por defecto los esconde, así que salen de listados, buscador, sitemaps, centros comerciales y
  guías sin tocar cada consulta. El admin y los importadores usan `_base_manager` y ven todo.
- La URL de un duplicado fusionado redirige con 301 a la ficha que quedó; la de un cerrado da 410
  con un aviso y enlaces a su zona.
- Comando `limpiar_fichas` (con `--dry-run`, que no escribe):
  - marca cerrados según Maps y los desmarca si reabren;
  - fusiona duplicados seguros (mismo nombre a menos de 40 m y mismas reseñas o teléfono: 94
    pares de los 101); se queda la ficha con guía, indexable, carta y más reseñas, y le pasa su
    guía y su carta si no las tiene. Los 7 dudosos no se tocan;
  - corrige las coordenadas fuera del valle con el punto de Maps;
  - encola en `GooglePlaceId` las fichas sin ficha de Maps para que el scraper las refresque.
- `import_medellin_enrich` ya no pisa el horario semanal con el estado del momento (bug 6 de la
  auditoría de bugs).
- Pendiente de tu decisión: los 4.813 registros sin fotos. No se borra nada sin tu confirmación.

**Qué hacer hecho en código (31 oct, sin desplegar).**
- Tipos nuevos en `PLACE_TYPE_CHOICES` (museo, parque, iglesia, estadio, teatro…; migración 0043
  solo de estado) y `QUE_HACER` con cuatro categorías: lugares emblemáticos, museos y cultura,
  parques y naturaleza, miradores. Salen del buscador de comida y entran al índice por su propia
  regla (rating ≥ 4 con 50+ reseñas).
- Comando `publicar_que_hacer`: 252 lugares elegidos de las fichas de Maps (74 emblemáticos, 80 de
  museos y cultura, 74 de parques y naturaleza, 24 miradores). Mínimo de reseñas por tipo (parques
  1.000, iglesias 1.500, museos 100…), rating 4,3+, 3+ fotos, dentro de una de nuestras zonas, sin
  repetidos y sin lo que Maps clasifica mal (gimnasios, canchas, oficinas, un centro comercial…).
- Páginas `/que-hacer/` y `/que-hacer/<categoría>/` (`/en/things-to-do/…`), en el menú superior,
  en "Más" y en Guías. La ficha de un museo o un parque enlaza a su categoría en vez del buscador.
- Quedan para después: guías editoriales con este material (Comuna 13, museos, miradores) y el
  bloque de agencias de tours.

**Segunda tanda (31 oct, sin desplegar).**
- "Tours y excursiones", quinta categoría de Qué hacer (tipo `tour_agency`, schema
  `TravelAgency`). Comando `publicar_tours`: 26 operadores elegidos a mano entre las 89 fichas de
  "Agencia de…" del valle (fuera las que venden vuelos y paquetes), con rating 4,5+, 50+ reseñas
  y 3+ fotos. Graffitour ya estaba publicado: solo cambia de tipo. Enlace desde Guías.
- Cuatro borradores más en `crear_guias_que_hacer`: Qué hacer en Medellín (12 paradas), Planes
  con niños (10), Parques y naturaleza (9) y Teatros (8).
- `ampliar_guias_zona`: Envigado, Belén y Sabaneta suman su parque y su cultura delante de las
  mesas (de 3–4 a 6–7 paradas), así que pasan el mínimo de 5 y vuelven al índice y al sitemap.
- Aviso de "Cerrado temporalmente" en la ficha (2 fichas con fotos hoy).
