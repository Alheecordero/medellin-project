# Estructura Frontend Actual - ViveMedellin

Este documento describe la estructura frontend actual del proyecto Django `ViveMedellin`, con foco en templates, componentes reutilizables, estilos, JavaScript, i18n, AdSense y patrones de UI.

## Resumen Ejecutivo

El frontend esta construido principalmente con:

- Django templates con herencia desde `base.html`.
- Bootstrap 5, Bootstrap Icons y Google Fonts desde CDN.
- CSS propio en capas: `variables.css`, `style.css`, `components.css`.
- Mucho CSS/JS especifico embebido en templates grandes, especialmente `home.html`.
- Componentes reutilizables en `explorer/templates/components/`.
- Renderizado mixto: HTML de servidor + HTML generado por JavaScript para resultados AJAX.
- Monetizacion con AdSense manual + Auto Ads, controlada por `adsense_allowed` y slots desde settings.

La pieza mas importante y mas compleja del frontend es `explorer/templates/home.html`, que funciona como landing, buscador, filtro, seccion de imperdibles, resultados AJAX y contenedor de logica JS.

## Arbol de Templates

```text
explorer/templates/
├── base.html
├── home.html
├── about.html
├── footer.html
├── semantic_results.html
├── ads.txt
├── robots.txt
├── admin/
│   └── explorer/
│       └── initialgrid/
│           └── change_list.html
├── components/
│   ├── adsense_fixed_unit.html
│   ├── lang_switcher.html
│   ├── optimized_img.html
│   ├── place_card.html
│   ├── place_card_compact.html
│   ├── schema_org.html
│   └── share_buttons.html
├── guias/
│   ├── guias_index.html
│   └── guia_detail.html
├── legal/
│   ├── contact.html
│   ├── legal_styles.html
│   ├── privacy_policy.html
│   └── terms.html
├── lugares/
│   ├── admin_mapa_regiones.html
│   ├── buscar_autocompletar.html
│   ├── lugares_por_comuna.html
│   ├── places_detail.html
│   ├── places_list.html
│   ├── reviews_lugar.html
│   └── zonas_mapa.html
└── newsletter/
    ├── confirmation_error.html
    ├── confirmation_success.html
    └── unsubscribe_success.html
```

## Arbol de Archivos Estaticos

```text
explorer/static/
├── favicon.svg
├── robots.txt
├── site.webmanifest
├── css/
│   ├── README.md
│   ├── components.css
│   ├── modern-style.css
│   ├── style.css
│   └── variables.css
└── js/
    ├── home_filters.js
    └── optimizations.js
```

## Layout Global

### `base.html`

Responsabilidades principales:

- Define el shell HTML global.
- Carga `static`, `i18n` y metadatos SEO.
- Define bloques: `title`, `meta_description`, `og_*`, `twitter_*`, `navbar`, `content`, `extra_css`, `extra_js`.
- Configura canonical y alternates `hreflang`.
- Carga Google Analytics si existe `settings.GOOGLE_ANALYTICS_ID`.
- Carga AdSense si `adsense_allowed` esta activo.
- Carga CSS en este orden:
  - `variables.css`
  - `style.css`
  - `components.css`
- Carga JS global:
  - jQuery
  - Bootstrap bundle
  - `optimizations.js`
- Incluye `footer.html`.
- Renderiza el bloque global de AdSense con `components/adsense_fixed_unit.html`.

### Patron de Herencia

La mayoria de templates extienden `base.html`. Varias paginas vacian el bloque `navbar` y dibujan su propia navegacion superior dentro del contenido:

```django
{% block navbar %}{% endblock %}
```

Este patron aparece en paginas con experiencia tipo landing o secciones oscuras/fullscreen.

## Paginas Principales

### `home.html`

Es la vista frontend mas grande del proyecto. Actualmente contiene:

- Hero principal con fondo fotografico de Medellin.
- Navegacion superior interna: Inicio, Nosotros, selector ES/EN.
- H1 principal.
- Buscador semantico.
- Filtros por area, tipo y caracteristicas.
- Botones principales: Cerca de Mi y Ver Todos los Lugares.
- Seccion de lugares imperdibles con cards visuales.
- Burbujas de areas y municipios.
- Bloque de AdSense Home.
- Contenedor para resultados AJAX.
- Schema.org de website y organization.
- CSS inline extenso en `extra_css`.
- JavaScript inline extenso en `extra_js`.

#### Logica de "Imperdibles"

La lista se genera desde `HomeView._get_lugares_imperdibles()` en `explorer/views.py`.

Flujo:

1. Se crea un pool cacheado por idioma.
2. El pool incluye lugares con:
   - `tiene_fotos=True`
   - `slug` valido
   - `rating >= 4.4`
   - senales de popularidad: `show_in_home`, `es_destacado` o `total_reviews >= 60`
3. Se excluye contenido sensible para AdSense.
4. Se obtienen thumbnails y fallback de imagen.
5. En cada request se devuelve una muestra aleatoria de hasta 8 lugares.

Esto permite rotacion por request sin recalcular toda la consulta en cada visita.

### `lugares/places_list.html`

Responsabilidades:

- Pagina principal de listado de lugares.
- Filtros por area, tipo y caracteristicas.
- Render inicial desde servidor.
- Render dinamico via AJAX.
- Uso de `components/place_card.html`.
- AdSense manual top/mid/bottom.
- JavaScript inline para reconstruir cards en cliente.

Riesgo actual:

- Existe duplicacion entre `place_card.html` y la funcion JS que genera cards dinamicas. Si cambia el diseno de card, hay que actualizar ambos.

### `lugares/places_detail.html`

Responsabilidades:

- Ficha detallada de un lugar.
- Hero con imagenes/carousel.
- Informacion de rating, direccion, caracteristicas, horarios, contacto, mapas y acciones.
- Bloques relacionados cargados por AJAX:
  - cercanos
  - similares
  - misma comuna/zona
- AdSense en detalle.
- Control de contenido sensible mediante `adsense_allowed`.

Riesgo actual:

- Mucha logica JS inline y generacion dinamica de cards compactas.

### `lugares/reviews_lugar.html`

Responsabilidades:

- Muestra reviews de un lugar.
- Permite traduccion de reseñas via API.
- Incluye AdSense entre secciones/reviews.
- Usa `adsense_allowed` para no mostrar anuncios en contenido sensible.

### `guias/guias_index.html` y `guias/guia_detail.html`

Responsabilidades:

- Sistema local de guias curadas.
- Indice de guias con cards.
- Detalle editorial con mapa, rankings y lugares seleccionados.
- Usa datos i18n del modelo de guias.

Nota:

- Esta parte existe localmente en el arbol actual, pero debe tratarse con cuidado en deploy si todavia no esta lista para produccion.

### `semantic_results.html`

Responsabilidades:

- Render de resultados semanticos.
- Usa una estructura visual parecida a listados de lugares.
- Puede beneficiarse del mismo estandar de `place-card`.

## Componentes Reutilizables

### `components/place_card.html`

Componente principal de lugar.

Incluye:

- Foto con `src`, `srcset` y `sizes`.
- Fallback de imagen.
- Rating.
- Badges:
  - tipo
  - destacado
  - exclusivo
  - top
- Precio.
- Direccion.
- Comentario editorial opcional.
- CTA a detalle.

Clases principales:

- `place-card`
- `place-card__media`
- `place-card__img`
- `place-card__body`
- `place-card__title`
- `place-card__badges`
- `place-card__cta`

### `components/place_card_compact.html`

Componente compacto alternativo. Existe en el arbol, pero su uso parece limitado o posiblemente no conectado en todos los templates.

### `components/adsense_fixed_unit.html`

Componente para unidades manuales de AdSense.

Incluye:

- `<ins class="adsbygoogle adsense-manual">`
- `data-ad-client`
- `data-ad-slot`
- `data-ad-format="auto"`
- `data-full-width-responsive="true"`
- `push({})` de AdSense.
- Ocultacion del wrapper si Google marca `data-ad-status="unfilled"`.

### `components/lang_switcher.html`

Selector de idioma.

Usa:

- `set_language`
- helper `translate_url_to`
- forms POST por idioma.

### `components/schema_org.html`

Genera datos estructurados para SEO. Se usa en Home y otras paginas importantes.

### `components/share_buttons.html`

Botones de compartir, usado principalmente en detalle.

### `components/optimized_img.html`

Helper visual para imagenes optimizadas.

## Sistema CSS

### `variables.css`

Define design tokens:

- Colores principales.
- Gradientes.
- Opacidades.
- Espaciado.
- Radios.
- Sombras.
- Z-index.
- Transiciones.

El archivo `explorer/static/css/README.md` documenta el uso esperado de estas variables.

### `style.css`

Responsabilidades:

- Estilos base del sitio.
- Navbar/footer y estilos generales.
- Reglas de contencion para Auto Ads y AdSense.
- Ajustes responsive globales.
- Estilos historicos de multiples secciones.

Incluye reglas importantes para:

- `adsense-fixed-unit`
- `adsense-mobile-only`
- `adsense-desktop-only`
- `google-auto-placed`
- contencion de overflow horizontal.

### `components.css`

Responsabilidades:

- Componentes reutilizables.
- Sistema actual de cards principales.
- Variantes compactas.
- Aliases legacy usados por templates/JS antiguos.
- Utilidades de pagina y componentes.

Este archivo es la fuente principal para estandarizar cards en todo el frontend.

### `modern-style.css`

Existe en disco, pero no se detecta como parte del pipeline principal de carga desde `base.html`. Puede ser CSS huérfano o experimental.

## JavaScript

### JS Inline

Gran parte de la logica vive dentro de templates, sobre todo:

- `home.html`
- `places_list.html`
- `places_detail.html`
- `reviews_lugar.html`

Uso principal:

- AJAX de busqueda semantica.
- AJAX de filtros.
- Render dinamico de cards.
- Geolocalizacion / Cerca de Mi.
- Traduccion de reviews.
- Carga progresiva de relacionados.

### `static/js/optimizations.js`

Responsabilidades detectadas:

- Autocomplete si existe jQuery UI.
- Smooth scroll.
- Helpers de galeria/modal.
- Compartir por WhatsApp.

Riesgo:

- Contiene señales de haber mezclado sintaxis Django dentro de archivo estatico. Los archivos estaticos no son procesados por Django templates.

### `static/js/home_filters.js`

Existe en disco, pero no se detecta como enlazado desde los templates principales. Puede ser archivo huérfano o una version anterior de la logica del Home.

## Internacionalizacion

El frontend usa:

- `{% trans %}`
- `{% blocktrans %}`
- `get_current_language`
- `pgettext_lazy('url', ...)` en rutas.
- `javascript-catalog` para traducciones JS.
- Helper `translate_url_to` para conservar cambio de idioma en URLs equivalentes.

Patron:

- Español sin prefijo.
- Ingles con `/en/`.

Riesgos:

- Algunas URLs se construyen manualmente en JS.
- Si una URL hardcodeada no considera `CURRENT_LANG`, puede romper equivalencias en ingles.

## AdSense y Monetizacion

La arquitectura actual combina:

- Script global de AdSense en `base.html`.
- Unidades manuales por slot:
  - Home
  - List
  - Detail
  - Global
  - Reviews
- Auto Ads desde configuracion de AdSense.
- `adsense_allowed` para apagar anuncios en paginas sensibles.

Puntos importantes:

- `components/adsense_fixed_unit.html` evita dejar huecos si Google devuelve `unfilled`.
- `style.css` contiene reglas para no romper layout con auto ads.
- Las paginas sensibles se filtran por `is_sensitive_for_ads`.

Riesgos:

- Demasiadas exclusiones `data-nosnippet` / `data-ad-layout="-exclude"` pueden reducir inventario.
- Muy poca contencion puede romper el layout en mobile.
- El balance actual debe revisarse con reportes de Active View, RPM e impresiones por unidad.

## Flujo General de UI

1. El usuario entra a Home.
2. `base.html` carga shell, SEO, CSS, analytics y AdSense.
3. `home.html` muestra hero, filtros, lugares imperdibles y areas.
4. El usuario puede:
   - buscar semanticamente
   - usar filtros
   - abrir un lugar imperdible
   - ir a listado completo
   - activar Cerca de Mi
5. Los listados muestran `place-card` y permiten filtrar.
6. El detalle muestra ficha completa y carga relacionados progresivamente.
7. Reviews y guias extienden la experiencia de contenido.

## Deuda Tecnica Frontend

### 1. `home.html` es demasiado grande

Actualmente concentra:

- estructura
- CSS
- JS
- render dinamico
- UX de busqueda
- geolocalizacion
- cards
- traducciones JS

Recomendacion:

- Extraer CSS del Home a `static/css/home.css`.
- Extraer JS del Home a `static/js/home.js`.
- Mantener en template solo datos iniciales y bloques HTML.

### 2. Duplicacion de cards

La card existe:

- como template en `components/place_card.html`
- como HTML generado por JS en Home
- como HTML generado por JS en List
- como HTML generado por JS en Detail relacionados

Recomendacion:

- Mantener una especificacion unica de card.
- Si se sigue usando JS, crear un renderer JS compartido en `static/js/place_card_renderer.js`.
- Alternativamente, hacer que endpoints AJAX devuelvan HTML parcial renderizado por Django.

### 3. CSS legacy / archivos posiblemente huérfanos

Revisar:

- `modern-style.css`
- `home_filters.js`
- `place_card_compact.html`
- `lugares/buscar_autocompletar.html`

### 4. URLs hardcodeadas en JS

Riesgo para i18n.

Recomendacion:

- Exponer URLs desde templates en un objeto `window.VM_ROUTES`.
- Evitar strings como `/lugar/${slug}/` en archivos estaticos.

### 5. AdSense y CLS

Riesgo:

- Auto Ads puede insertar contenedores inesperados.
- Unidades manuales pueden generar huecos si no hay fill.

Recomendacion:

- Reservar espacio solo en ubicaciones estables.
- Seguir midiendo Active View por unidad.
- Evitar esconder inventario viable salvo zonas realmente sensibles.

## Recomendaciones de Organizacion

### Corto plazo

- Mantener todos los cambios visuales de cards en `components.css`.
- Documentar cualquier nuevo slot AdSense en este archivo o en una guia de monetizacion.
- No mezclar guias/pipeline con deploys pequeños de monetizacion o home.

### Mediano plazo

- Crear:

```text
explorer/static/css/home.css
explorer/static/js/home.js
explorer/static/js/place_card_renderer.js
```

- Reducir `home.html` a estructura y datos iniciales.
- Consolidar render de cards dinamicas.

### Largo plazo

- Separar areas funcionales:
  - `home`
  - `lugares`
  - `guias`
  - `ads`
  - `analytics`
- Crear documentacion de patrones UI: cards, filtros, secciones, anuncios, mapas.

## Archivos Clave para Futuras Mejoras

Si se trabaja en performance:

- `explorer/templates/home.html`
- `explorer/static/css/style.css`
- `explorer/static/css/components.css`
- `explorer/static/js/optimizations.js`

Si se trabaja en cards:

- `explorer/templates/components/place_card.html`
- `explorer/static/css/components.css`
- renderers JS dentro de `home.html`, `places_list.html`, `places_detail.html`

Si se trabaja en AdSense:

- `explorer/templates/base.html`
- `explorer/templates/components/adsense_fixed_unit.html`
- `explorer/static/css/style.css`
- `explorer/context_processors.py`
- `Medellin/settings.py`

Si se trabaja en i18n:

- `explorer/templates/components/lang_switcher.html`
- `explorer/templatetags/form_tags.py`
- `explorer/urls.py`
- `locale/*/LC_MESSAGES/django.po`

## Estado Actual

El frontend ya tiene una base visual fuerte y un sistema de componentes reconocible, especialmente alrededor de `place-card`. El mayor reto no es falta de diseño, sino organizacion: hay demasiada logica concentrada en templates grandes y varias piezas duplicadas entre Django templates y JavaScript.

La prioridad recomendada es estabilizar:

1. Cards como componente unico.
2. Home dividido en CSS/JS dedicados.
3. Estrategia de anuncios documentada por plantilla.
4. Limpieza de archivos estaticos no usados.
