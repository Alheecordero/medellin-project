# Revisión de las guías — 9 nov 2026

Se comprobaron los diez problemas de la revisión pública contra el código y la base de producción
(solo lectura). Los diez se confirmaron. Las correcciones de datos están en
`manage.py corregir_guias` y no se han aplicado en producción.

## Problemas confirmados y su causa

| # | Problema | Causa | Arreglo |
|---|---|---|---|
| 1 | "Noche en Laureles y La 70" con Despecho Medellín, DANCEFREE y Donde Aquellos | Los tres están en El Poblado, fuera del polígono de Laureles-Estadio. La ficha `dulce-jesus-mio` se renombró a "Despecho Medellín" y conserva el slug viejo. Nada comprobaba la zona | Salen de la guía. Entra Dulcinea, que está en la zona y tiene web oficial. `revisar_guias` avisa de cualquier parada fuera de zona sin motivo explícito |
| 2 | Barrio Sur en "Bares en El Poblado" | Está en Envigado | Sale |
| 3 | Hatoviejo en "Centro de día" | Se eligió la sede Palmas (Buenos Aires) y no la de Junín | Cambio a `restaurante-hatoviejo-centro`. La revisión sugiere la sede que sí está en la zona |
| 4 | La Matriarca como "Cafetería de perros" | El clasificador prefería `dog_cafe`, que venía del barrido de descubrimiento, a `restaurant`, porque los cafés estaban antes en la prioridad. Maps dice "Restaurante colombiano" | Los tipos de nicho (`dog_cafe`, `cat_cafe`, `internet_cafe`) quedan detrás de restaurante, bar y café. La ficha pasa a `restaurant`. La etiqueta pasa a "Café con perros" |
| 5 | Purple Club en el top LGBTQ | La dirección de la ficha (Cl 10A #36-29) es la del hotel Haven, donde está 360 Rooftop. Su Instagram oficial está activo pero no da dirección. Una reseña de 2017 habla de traslado y otra de 2023 dice "No está ahí" | Sale hasta confirmar la dirección. No se quitó por la nota |
| 6 | La numeración de los rooftops saltaba del 6 al 8 | El número era `posicion` de la base. La parada 7 (Panorama) estaba cerrada y oculta | Numeración continua sobre lo visible (`utils.guias.numerar`), y solo en rankings y recorridos. Panorama sale |
| 7 | El Tesoro: 33 en el índice y 32 en su página | El índice mostraba `total_lugares`, guardado por el importador con un criterio que no excluía los tipos que la página oculta. También pasaba con Santafé (23/22) y Monterrey (16/15) | Un solo criterio, `lugar_de_centro()`. El índice cuenta en vivo con él y el importador guarda ese mismo número |
| 8 | Recomendaciones genéricas ("Japonés.", "Mariscos.", "Nota muy alta.") | Textos de relleno, o justificados con la nota de Google | `revisar_guias` las marca. 35 pasan a notas internas: no se pierden y no se publican |
| 9 | "Un día en Guatapé" solo tiene restaurantes | El título prometía un día completo | El título visible pasa a "Dónde comer en Guatapé" y la URL no cambia. El itinerario de un día está en el borrador `un-dia-en-guatape-ampliada` |
| 10 | El texto de la guía se repite en la ficha | `_notas_guia` copiaba el comentario de la parada. "Bar para seguir en Laureles" salía en Donde Aquellos, que está en El Poblado | La ficha solo copia la frase si la guía tiene fecha de revisión editorial. Si no, muestra solo el enlace |

Hay una causa común a 6, 7 y 10: cada vista decidía por su cuenta qué parada es visible. Ahora todas usan
`parada_visible()`: ficha con fotos, no cerrada y no fusionada. Eso incluye la página, el índice, el
sitemap, el contador de la guía y el número mínimo para indexar.

## Qué cambió en el código

- **Modelo (migración `0045_guias_editorial`):**
  - La guía gana: `formato` (selección, ranking o recorrido), `para_quien`, `criterio`, `consejos`,
    `autor`, `revisado_en` (la fecha de revisión editorial, que las sincronizaciones no cambian) y
    `relacionadas`.
  - Cada parada gana: `diferencia`, `ocasion`, `presupuesto`, `fuente_url`, `verificado_en`,
    `fuera_de_zona_motivo` y `notas_editoriales` (no se publican). También la versión en inglés de
    `como_llegar` y `advertencia`.
  - Tabla nueva `UbicacionEnCentro` con piso, local, referencia, fuente y fecha. Solo se publica
    verificada. Es una tabla aparte para no alterar la de fichas.
- **Datos que cambian:** el presupuesto y el aviso de "Antes de ir" solo se publican con
  `verificado_en`. Si no hay presupuesto verificado, se muestra el rango real de la carta con su
  fuente ("según la carta en Rappi").
- **Plantilla:**
  - Bloques nuevos: para quién es, cómo elegimos, firma solo con revisión real, comparativa (solo si
    aporta datos), mapa, recorrido, consejos, guías relacionadas y "Avísanos" para reportar cambios.
  - Una selección se marca como `<ul>`, sin números. El ranking y el recorrido van en `<ol>`.
  - El mapa (Leaflet) se descarga al acercarse a la pantalla. En el móvil, la comparativa se apila.
- **JSON-LD:**
  - `dateModified` sale solo de `revisado_en`; antes usaba la fecha de cualquier guardado.
  - El autor es una `Person` solo si hay autor real.
  - `ItemListUnordered` para las selecciones.
- **Protección editorial:**
  - `import_guias_borrador` ya no sobrescribe el texto de una guía con `revisado_en` ni el de una
    parada con `verificado_en`.
  - `ampliar_guias_zona` no toca guías revisadas.
- **Revisión:**
  - `manage.py revisar_guias` y el bloque "Avisos" en el admin avisan de: paradas fuera de zona,
    posibles sedes equivocadas, misma marca dos veces, paradas ocultas, tipo de nicho distinto al de
    Maps, menos de 20 reseñas, reseñas que hablan de traslado o cierre, recomendaciones genéricas,
    datos variables sin fecha y guías publicadas sin revisión.
  - El inline del admin pasa a apilado, con todos los campos nuevos.
- **Pruebas:** `explorer/test_guias.py` tiene 26 pruebas sin base de datos: zonas, numeración,
  contadores, preservación editorial, datos variables y clasificación.

## Fuentes consultadas (9 nov 2026)

Solo se publica texto que dice la fuente oficial, citada en `fuente_url`. Las fuentes secundarias van
a `notas_editoriales`. Nada se presenta como visitado.

| Lugar | Fuente oficial | Qué confirma |
|---|---|---|
| Bar Chiquita | barchiquita.com | Bar gay, drag todas las noches, Cra. 37 #8a-88, horario, reservas por WhatsApp |
| Purple Club | instagram.com/purpleclub_medellin | Activo, club gay, viernes y sábado. No da dirección |
| Dulcinea Discoteca | discotecadulcinea.com | Cl 44 #69-96, Laureles; música; jueves a sábado; cover y consumo mínimo variables; código de vestimenta; mayores de 18 |
| La Tienda de la 70 | instagram.com/latiendadela70 | Rumba con comida montañera y shows en vivo |
| Son Havana | sonhavana.co | Salsa y son cubano (solo el título de la web es legible) |
| Inzolente Rooftop | instagram.com/inzolenterooftop | Azotea del hotel Hashtag98, mayores de 18 |
| The Up Garden | instagram.com/theupgardenrooftop | Azotea del Art Hotel, reservas por mensaje directo o WhatsApp |
| Lavocadería Laureles | linktr.ee/lavocaderia, lavocaderia.co | Sexto piso del Hotel Mythical, Cra 66B #34-86; horario; reservas en línea |
| 37 Park | instagram.com/37parkmedellin | No muestra terraza en altura. Sale de la guía de rooftops |

**Sin fuente oficial legible:** Club Oráculo, Industry, Donde Aquellos, Envy, 360 Rooftop, La Deriva,
Mal de Ojo, Mamba Negra, El Tíbiri y la terraza de Zarzo. Su texto pasó a notas con lo que falta
verificar.

## Pasos para publicar

1. **Desplegar el código** con `scripts/desplegar.sh`. La migración solo añade columnas a las tablas
   de guías y crea dos tablas.
2. **Corregir las guías:**
   1. `manage.py corregir_guias`: vista previa, no guarda nada.
   2. `manage.py corregir_guias --aplicar`.
   3. `manage.py revisar_guias --publicadas`.
3. **Contadores de centros comerciales:** `manage.py importar_centros_comerciales --dry-run` y luego
   sin `--dry-run`, para que `total_lugares` quede con el criterio nuevo. El índice ya cuenta en vivo,
   así que este paso no es urgente.
4. **Revisión editorial:** el editor revisa cada guía en el admin y, solo entonces, pone `autor` y
   `revisado_en`.

**Efecto esperado:** "Lugares LGBTQ" y "Noche en Laureles" quedan con 4 lugares visibles, por debajo
del mínimo de 5. Salen del índice y llevan `noindex` hasta que se añadan lugares verificados. No se
rellenan con lugares sin evidencia.

## Pendiente de verificación editorial

- **LGBTQ:**
  - Purple Club: dirección actual (secundarias: Av. 33 #78-107). Al confirmarla, corregir la ficha y
    volver a añadirlo.
  - Club Oráculo, Industry y Donde Aquellos: buscar una fuente oficial legible. Industry: confirmar si
    está en Barrio Colombia o en El Poblado.
- **Rooftops:** confirmar terraza y vista de Envy, 360, La Deriva, Mal de Ojo, Mamba Negra y Zarzo.
  Las fuentes secundarias apuntan a terrazas de hotel.
- **Laureles:**
  - Fuente oficial de El Tíbiri y dirección de Son Havana.
  - Candidatos a sumar con verificación: Del Patio (su Instagram no da dirección), Cacique, Melodía
    para dos, Julieta, La Charcu y Barbur.
- **Todas las guías:** las 45 paradas sin recomendación necesitan el porqué, la diferencia y la
  ocasión, escritos por alguien que conozca el lugar o con fuente. Se ven en `revisar_guias`.

## Nuevas guías (backlog, sin publicar)

Orden por demanda probable y datos ya disponibles. Ninguna se publica sin autor, `revisado_en` y
texto con fuente.

| Prioridad | Guía | Formato | Base con la que se cuenta | Qué falta |
|---|---|---|---|---|
| 1 | Medellín por primera vez: 1, 2 y 3 días | Recorrido (tres guías o una con tres días) | Borradores `que-hacer-en-medellin`, `comuna-13`, `museos-de-medellin`, `miradores-de-medellin`; 278 lugares de Qué hacer | Orden real de las paradas, tiempos de traslado (metro, metrocable), horarios oficiales y días de cierre de los museos |
| 2 | Dónde comer comida paisa | Selección | Fichas con carta: platos como bandeja paisa y mondongo con precio | Elegir por carta y fuente, no por nota; el rango de precio sale de la carta |
| 3 | Qué hacer cuando llueve | Selección | Museos, teatros (borrador `teatros-de-medellin`) y centros comerciales | Confirmar que cada plan es bajo techo y su horario |
| 4 | Planes gratis y económicos | Selección | Parques, miradores, museos con entrada gratuita | Tarifas y días gratis en la fuente oficial, con fecha. Es el dato que más cambia |
| 5 | Cafés de especialidad y brunch | Selección | Cafés con carta y tipos de brunch | Confirmar café de especialidad con la fuente del lugar; los horarios de brunch cambian |
| 6 | Planes en pareja | Selección | Rooftops verificados, miradores, teatros | Criterio explícito (vista, ambiente tranquilo) con fuente; evitar adjetivos sin respaldo |
| 7 | Planes con niños | Selección | Borrador `planes-con-ninos` (10 paradas), Parque Explora, Parque Norte, Jardín Botánico | Edades, tarifas y accesibilidad de la fuente oficial |
