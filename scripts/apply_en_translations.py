#!/usr/bin/env python3
"""Apply English translations to locale/en/LC_MESSAGES/django.po"""
from __future__ import annotations

import polib
from pathlib import Path

PO_PATH = Path(__file__).resolve().parents[1] / "locale/en/LC_MESSAGES/django.po"

# Spanish msgid -> English msgstr
TRANSLATIONS: dict[str, str] = {
    "Cambiar idioma": "Change language",
    "Guía completa de bares, restaurantes, rooftops y vida nocturna en Medellín, Colombia": (
        "Complete guide to bars, restaurants, rooftops and nightlife in Medellín, Colombia"
    ),
    "Guía turística digital de Medellín con información real de bares, restaurantes y lugares de entretenimiento": (
        "Digital travel guide to Medellín with real information on bars, restaurants and entertainment venues"
    ),
    "Abrir menú": "Open menu",
    "Explorar": "Explore",
    "Menú mobile": "Mobile menu",
    "ViveMedellín — Inicio": "ViveMedellín — Home",
    "Guía local de bares, restaurantes y vida nocturna en Medellín. Datos reales para explorar como un local.": (
        "Local guide to bars, restaurants and nightlife in Medellín. Real data to explore like a local."
    ),
    "Explorar lugares": "Explore places",
    "Medellín, Colombia": "Medellín, Colombia",
    "Vida nocturna": "Nightlife",
    "Música en vivo": "Live music",
    "Con terraza": "Outdoor seating",
    "Zonas": "Areas",
    "El Poblado": "El Poblado",
    "Laureles": "Laureles",
    "Envigado": "Envigado",
    "Belén": "Belén",
    "Sabaneta": "Sabaneta",
    "Ver todas": "View all",
    "Empresa": "Company",
    "Privacidad": "Privacy",
    "Términos": "Terms",
    "Enlaces legales": "Legal links",
    "La guía local para vivir Medellín": "The local guide to experience Medellín",
    "Encuentra los mejores lugares para vivir Medellín": "Find the best places to experience Medellín",
    "Busca restaurantes, bares, cafés, cultura y planes por zona o cerca de ti.": (
        "Search restaurants, bars, cafés, culture and plans by area or near you."
    ),
    "¿Qué buscas? Ej. bares en El Poblado": "What are you looking for? e.g. bars in El Poblado",
    "Buscar cerca de mí": "Search near me",
    "Explorar por zonas": "Explore by area",
    "Explorar por intención": "Explore by intent",
    "Terrazas": "Outdoor seating",
    "Pet friendly": "Pet friendly",
    "Zonas populares": "Popular areas",
    "+ Ver más": "+ See more",
    "Filtros avanzados": "Advanced filters",
    "Publicidad": "Advertisement",
    "Imperdibles ahora": "Must-visit now",
    "Ver todos": "View all",
    "Explora por zonas": "Explore by area",
    "Ver menos": "See less",
    "Ver más": "See more",
    "Contáctanos en ViveMedellín. Preguntas sobre lugares en Medellín, sugerencias o reportar información incorrecta.": (
        "Contact us at ViveMedellín. Questions about places in Medellín, suggestions, or to report incorrect information."
    ),
    "Hablemos": "Let's talk",
    "¿Tienes preguntas, sugerencias o encontraste un error? Nos encantaría escucharte.": (
        "Have questions, suggestions, or found an error? We'd love to hear from you."
    ),
    "Creador de ViveMedellín": "Creator of ViveMedellín",
    "Escríbenos": "Write to us",
    "Correo electrónico": "Email",
    "Respondemos en menos de 48 horas": "We reply within 48 hours",
    "Medellín, Antioquia": "Medellín, Antioquia",
    "Colombia": "Colombia",
    "¿Cómo podemos ayudarte?": "How can we help?",
    "Propietarios:": "Business owners:",
    "Actualiza o reclama tu establecimiento": "Update or claim your business",
    "Errores:": "Errors:",
    "Reporta información incorrecta": "Report incorrect information",
    "Sugerencias:": "Suggestions:",
    "Propón nuevos lugares o funciones": "Suggest new places or features",
    "Publicidad:": "Advertising:",
    "Consultas comerciales": "Commercial inquiries",
    "Privacidad:": "Privacy:",
    "Solicitudes sobre tus datos": "Data-related requests",
    "Enviar correo": "Send email",
    "Páginas legales": "Legal pages",
    "Política de privacidad de ViveMedellín. Información sobre cómo recopilamos, usamos y protegemos tus datos personales, incluyendo el uso de cookies y publicidad de Google AdSense.": (
        "ViveMedellín privacy policy. How we collect, use and protect your personal data, including cookies and Google AdSense advertising."
    ),
    "Documento legal": "Legal document",
    "Última actualización:": "Last updated:",
    "Términos y condiciones de uso de ViveMedellín. Conoce las reglas que rigen el uso de nuestro directorio de lugares en Medellín.": (
        "ViveMedellín terms of use. Learn the rules for using our Medellín places directory."
    ),
    "No se encontraron lugares": "No places found",
    "Limpiar características": "Clear features",
    "Resultados inteligentes para": "Smart results for",
    "Escribe una consulta en el buscador principal para ver resultados.": (
        "Enter a query in the main search bar to see results."
    ),
    "Intenta ajustar tus palabras clave o usar otros filtros en el buscador principal.": (
        "Try adjusting your keywords or using other filters in the main search bar."
    ),
    "Medellín": "Medellín",
    "Lugares que coinciden con tu búsqueda en %(ubicacion)s": "Places matching your search in %(ubicacion)s",
    "en Medellín": "in Medellín",
    "%(desc)s en la zona de %(comuna)s": "%(desc)s in the %(comuna)s area",
    "Descubre los mejores %(tipo)s en la zona de %(comuna)s": "Discover the best %(tipo)s in the %(comuna)s area",
    'Resultados para "%(query)s" en %(comuna)s': 'Results for "%(query)s" in %(comuna)s',
    "Lugares que coinciden con tu búsqueda en %(comuna)s": "Places matching your search in %(comuna)s",
    "No encontramos %(tipo)s en %(area)s": "We couldn't find any %(tipo)s in %(area)s",
    "No encontramos %(tipo)s": "We couldn't find any %(tipo)s",
    "No encontramos lugares en %(area)s": "We couldn't find places in %(area)s",
    "No encontramos lugares con estos filtros": "We couldn't find places with these filters",
    "ViveMedellín - Tu Guía de la Ciudad": "ViveMedellín - Your City Guide",
    "Descubre los mejores bares, discotecas, restaurantes y lugares turísticos de Medellín.": (
        "Discover the best bars, clubs, restaurants and attractions in Medellín."
    ),
    "Medellín, turismo, lugares, bares, restaurantes, discotecas, que hacer en Medellín": (
        "Medellín, tourism, places, bars, restaurants, clubs, things to do in Medellín"
    ),
    "Descubre los mejores lugares de Medellín, la ciudad de la eterna primavera.": (
        "Discover the best places in Medellín, the city of eternal spring."
    ),
    "Hecho con cariño para locales y viajeros que quieren vivir la ciudad a profundidad.": (
        "Made with care for locals and travelers who want to experience the city in depth."
    ),
    "Con Delivery": "With delivery",
    "Restaurantes Laureles": "Restaurants in Laureles",
    "Explorar Todo": "Explore all",
    "Todos los derechos reservados.": "All rights reserved.",
    "Inicio | ViveMedellín": "Home | ViveMedellín",
    "Bienvenido a ViveMedellín: descubre los mejores bares, discotecas, rooftops y restaurantes de Medellín, organizados por comunas. ¡Explora como un local!": (
        "Welcome to ViveMedellín: discover the best bars, clubs, rooftops and restaurants in Medellín, organized by neighborhood. Explore like a local!"
    ),
    "ViveMedellín, bares Medellín, discotecas Medellín, restaurantes Medellín, comunas Medellín, vida nocturna Medellín": (
        "ViveMedellín, bars Medellín, clubs Medellín, restaurants Medellín, neighborhoods Medellín, nightlife Medellín"
    ),
    "ViveMedellín | Descubre los mejores lugares por comuna": "ViveMedellín | Discover the best places by neighborhood",
    "Navega los mejores sitios para salir en Medellín. Desde El Poblado hasta Laureles, descubre lugares únicos en cada comuna.": (
        "Browse the best places to go out in Medellín. From El Poblado to Laureles, discover unique spots in every neighborhood."
    ),
    "Busca bares, restaurantes, lugares...": "Search bars, restaurants, places...",
    "Cerca de Mí": "Near me",
    "Ver todas las áreas": "View all areas",
    "Radio": "Radius",
    "Información": "Information",
    "Teléfono": "Phone",
    "Sitio Web": "Website",
    "Visitar": "Visit",
    "Explóralo:": "Explore it:",
    "Ver": "View",
    "lugares Medellín, bares Medellín, restaurantes Medellín, sitios para salir en Medellín": (
        "places Medellín, bars Medellín, restaurants Medellín, going out Medellín"
    ),
    "Descubre lugares con calificaciones reales en Medellín.": "Discover places with real ratings in Medellín.",
    "Mostramos una selección de reseñas destacadas para ofrecer una visión equilibrada de la experiencia de nuestros visitantes.": (
        "We show a selection of featured reviews to offer a balanced view of visitor experiences."
    ),
    "Sitio web": "Website",
    "No especificado": "Not specified",
    "Cafeterías y café de especialidad": "Cafés and specialty coffee",
    "Bienestar y spa": "Wellness and spa",
    "Otros lugares": "Other places",
    "Descubre los mejores %(tipo)s recomendados en %(area)s": "Discover the best recommended %(tipo)s in %(area)s",
    "Descubre los sitios más destacados de %(area)s": "Discover the top spots in %(area)s",
    "Encontramos %(count)s %(tipo)s en un radio de %(dist)s": "We found %(count)s %(tipo)s within %(dist)s",
    "Encontramos %(count)s lugar en un radio de %(dist)s": "We found %(count)s place within %(dist)s",
    "Lugares que coinciden con tu búsqueda en Medellín": "Places matching your search in Medellín",
    "Image": "Image",
    "mar": "Tue",
    "apr": "Thu",
    "dec": "Sun",
    "No year specified": "No year specified",
    "No month specified": "No month specified",
    "No day specified": "No day specified",
    "No week specified": "No week specified",
    "Recibe las mejores recomendaciones de lugares directamente en tu correo": (
        "Get the best place recommendations straight to your inbox"
    ),
    "Suscribirme": "Subscribe",
    "100%% libre de spam • Cancela cuando quieras": "100%% spam-free • Unsubscribe anytime",
    "Experiencias Destacadas": "Featured experiences",
    "Zonas Premium": "Premium areas",
    "Tu guía definitiva para descubrir los mejores lugares de la Ciudad de la Eterna Primavera": (
        "Your ultimate guide to the best places in the City of Eternal Spring"
    ),
    "Error de Geolocalización": "Geolocation error",
    "Descubre <span class=\"text-white\">Medellín</span><br>Como Nunca Antes": (
        "Discover <span class=\"text-white\">Medellín</span><br>Like Never Before"
    ),
    "característica opcional": "optional feature",
    "Buscar Lugares": "Search places",
    "Explora Medellín por Comunas": "Explore Medellín by neighborhood",
    "Precisión GPS activa": "GPS precision active",
    "Foto de": "Photo of",
    "Sin fotos disponibles": "No photos available",
    "Abierto ahora": "Open now",
    "Tipo:": "Type:",
    "Visitar sitio web": "Visit website",
    "Rating:": "Rating:",
    "Rango de Precios:": "Price range:",
    "zona:": "area:",
    "Servicios y Características": "Services and features",
    "Área": "Area",
    "Restaurante General": "General restaurant",
    "Restaurante Gourmet": "Gourmet restaurant",
    "Restaurante Italiano": "Italian restaurant",
    "Restaurante Mexicano": "Mexican restaurant",
    "Restaurante Chino": "Chinese restaurant",
    "Parrilla de Carnes": "Steakhouse",
    "Bares & Vida Nocturna": "Bars & nightlife",
    "Bar de Vinos": "Wine bar",
    "Desayunos": "Breakfast",
    "Brunch": "Brunch",
    "Limpiar todos": "Clear all",
    "Descubrir": "Discover",
    "Todos los Lugares": "All places",
    "Explora nuestra colección completa": "Explore our full collection",
    "Los mejores sabores de la ciudad": "The city's best flavors",
    "Bares & Discotecas": "Bars & clubs",
    "Vida nocturna en Medellín": "Nightlife in Medellín",
    "Cultura cafetera paisa": "Paisa coffee culture",
    "Resultados para:": "Results for:",
    "Horario no disponible": "Hours not available",
    "Manual de uso": "User guide",
    "Explora Medellín como un local con ViveMedellín": "Explore Medellín like a local with ViveMedellín",
    "ViveMedellín es tu mapa curado de restaurantes, bares y planes en la ciudad. Aquí te mostramos, en minutos, cómo sacarle el máximo provecho.": (
        "ViveMedellín is your curated map of restaurants, bars and plans in the city. Here's how to get the most out of it in minutes."
    ),
    "Lugares con fotos reales": "Places with real photos",
    "Zonas de la ciudad": "City areas",
    "Tipos de experiencias": "Types of experiences",
    "Cómo usar ViveMedellín en 4 pasos": "How to use ViveMedellín in 4 steps",
    "Elige la zona que quieres explorar": "Choose the area you want to explore",
    "Desde la pantalla de inicio, usa las burbujas de comunas (El Poblado, Laureles, Centro, etc.) o el filtro de “Área” para centrarte en la parte de la ciudad que te interesa.": (
        "From the home screen, use neighborhood bubbles (El Poblado, Laureles, Centro, etc.) or the “Area” filter to focus on the part of the city you care about."
    ),
    "En desktop, verás filtros tipo “chips” y una tarjeta principal por comuna.": (
        "On desktop you'll see chip-style filters and a main card per neighborhood."
    ),
    "En móvil, desliza horizontalmente las cards para descubrir más zonas.": (
        "On mobile, swipe horizontally through cards to discover more areas."
    ),
    "Filtra por tipo de lugar y características": "Filter by place type and features",
    "ViveMedellín solo muestra lugares con fotos y datos curados.": (
        "ViveMedellín only shows places with photos and curated data."
    ),
    "Cuantos más filtros uses, más precisa será la lista de resultados.": (
        "The more filters you use, the more accurate the results list will be."
    ),
    "Escribe lo que tengas en mente: “restaurante italiano romántico en Laureles”, “rooftop con buena vista en El Poblado” o “bar tranquilo para trabajar con café”.": (
        "Type what you have in mind: “romantic Italian restaurant in Laureles”, “rooftop with a great view in El Poblado” or “quiet bar to work with coffee”."
    ),
    "Nuestro motor semántico entiende el contexto, no solo palabras sueltas.": (
        "Our semantic engine understands context, not just isolated words."
    ),
    "Obtendrás una grilla de cards con recomendaciones ordenadas según afinidad.": (
        "You'll get a grid of cards with recommendations ranked by relevance."
    ),
    "Abre la ficha de detalle y decide": "Open the detail page and decide",
    "En cada card, haz clic en “Ver detalles” para entrar a una vista con fotos, reseñas, mapa y servicios. Desde ahí puedes abrir Google Maps o Waze con un solo toque.": (
        "On each card, click “View details” for photos, reviews, map and services. From there you can open Google Maps or Waze with one tap."
    ),
    "Revisa el rating, servicios (terraza, música en vivo, etc.) y rango de precios.": (
        "Check the rating, services (outdoor seating, live music, etc.) and price range."
    ),
    "Explora lugares cercanos o similares sin salir del detalle.": (
        "Explore nearby or similar places without leaving the detail page."
    ),
    "Pensado para desktop y móvil": "Built for desktop and mobile",
    "En desktop": "On desktop",
    "En pantallas grandes, ViveMedellín se comporta como un panel de control visual: filtros en la parte superior y listados horizontales de lugares con cards detalladas.": (
        "On large screens, ViveMedellín works like a visual control panel: filters on top and horizontal listings with detailed cards."
    ),
    "Cards horizontales con imagen a la izquierda y contenido a la derecha.": (
        "Horizontal cards with image on the left and content on the right."
    ),
    "Secciones bien separadas: filtros, resultados, detalle y lugares relacionados.": (
        "Clear sections: filters, results, detail and related places."
    ),
    "En móvil": "On mobile",
    "En tu teléfono, todo se convierte en carruseles y cards a pantalla completa para que puedas decidir rápido con el pulgar.": (
        "On your phone, everything becomes carousels and full-screen cards so you can decide quickly with your thumb."
    ),
    "Carruseles horizontales para explorar zonas y lugares sin perder el contexto.": (
        "Horizontal carousels to explore areas and places without losing context."
    ),
    "Botones grandes y legibles para llamar, abrir mapas o compartir por WhatsApp.": (
        "Large, readable buttons to call, open maps or share on WhatsApp."
    ),
    "Preguntas rápidas": "Quick questions",
    "Mostramos principalmente restaurantes, bares, cafés y experiencias que tienen fotos, ubicación clara y datos suficientes para que puedas decidir.": (
        "We mainly show restaurants, bars, cafés and experiences with photos, clear location and enough data for you to decide."
    ),
    "¿De dónde salen las calificaciones?": "Where do ratings come from?",
    "Las puntuaciones y reseñas se basan en fuentes externas verificadas (como Google Maps) y se actualizan de forma periódica.": (
        "Scores and reviews come from verified external sources (such as Google Maps) and are updated periodically."
    ),
    "¿Puedo guardar mis lugares favoritos?": "Can I save my favorite places?",
    "En esta versión nos centramos en descubrir y decidir. Funciones como listas personales o favoritos llegarán en futuras actualizaciones.": (
        "In this version we focus on discovery and decisions. Features like personal lists or favorites will come in future updates."
    ),
    "Puedes alternar entre español e inglés desde los botones ES / EN en la esquina superior del home, del listado y de cada ficha de detalle.": (
        "You can switch between Spanish and English using the ES / EN buttons at the top of the home page, listings and each detail page."
    ),
    "%(count)s reseñas en Google": "%(count)s Google reviews",
    "Rating %(rating)s/5 calculado por Google sobre %(count)s opiniones verificadas": (
        "Rating %(rating)s/5 calculated by Google from %(count)s verified reviews"
    ),
    "Google proporciona hasta 5 reseñas destacadas por lugar. El rating %(rating)s/5 representa el promedio real de las %(total)s opiniones totales.": (
        "Google provides up to 5 featured reviews per place. The %(rating)s/5 rating is the real average of all %(total)s reviews."
    ),
    "Mostrando todas las %(count)s reseñas disponibles": "Showing all %(count)s available reviews",
    "Guía #1 de Medellín: más de 7,000 bares, restaurantes, rooftops y discotecas con ratings reales. Explora El Poblado, Laureles, Envigado y más.": (
        "#1 Medellín guide: 7,000+ bars, restaurants, rooftops and clubs with real ratings. Explore El Poblado, Laureles, Envigado and more."
    ),
    "Descubre más de 7,000 lugares en Medellín: bares, restaurantes, rooftops y discotecas. Ratings de Google, horarios y ubicación exacta.": (
        "Discover 7,000+ places in Medellín: bars, restaurants, rooftops and clubs. Google ratings, hours and exact location."
    ),
    "Guías": "Guides",
    "mejores lugares": "best places",
    "recomendaciones": "recommendations",
    "Política de Privacidad": "Privacy Policy",
    "Nosotros | ViveMedellín": "About | ViveMedellín",
    "Volver al inicio": "Back to home",
    "Volver arriba": "Back to top",
    "Contacto": "Contact",
    "Nosotros": "About",
    "Inicio": "Home",
    "Restaurantes": "Restaurants",
    "Bares": "Bars",
    "Cafés": "Cafés",
    "Info": "Info",
    "La guía local para descubrir lo mejor de la ciudad": "The local guide to discover the best of the city",
}

PLURAL_TRANSLATIONS: dict[str, tuple[str, str]] = {
    "%(count)s %(tipo)s en %(area)s": (
        "%(count)s %(tipo)s in %(area)s",
        "%(count)s %(tipo)s in %(area)s",
    ),
    "%(count)s %(tipo)s encontrados": (
        "%(count)s %(tipo)s found",
        "%(count)s %(tipo)s found",
    ),
    "%(count)s lugar en %(area)s": (
        "%(count)s place in %(area)s",
        "%(count)s places in %(area)s",
    ),
    "%(count)s lugar encontrado": (
        "%(count)s place found",
        "%(count)s places found",
    ),
}


def main() -> None:
    po = polib.pofile(str(PO_PATH))
    updated = 0

    # Fix header
    meta = po.find("")
    if meta is not None:
        meta.msgstr = (
            'Project-Id-Version: ViveMedellín\n'
            'Report-Msgid-Bugs-To: \n'
            'Language: en\n'
            'MIME-Version: 1.0\n'
            'Content-Type: text/plain; charset=UTF-8\n'
            'Content-Transfer-Encoding: 8bit\n'
            'Plural-Forms: nplurals=2; plural=(n != 1);\n'
        )
        if "fuzzy" in meta.flags:
            meta.flags.remove("fuzzy")

    for entry in po:
        if not entry.msgid:
            continue

        if entry.msgid in PLURAL_TRANSLATIONS and entry.msgid_plural:
            s, p = PLURAL_TRANSLATIONS[entry.msgid]
            entry.msgstr_plural = {0: s, 1: p}
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
            updated += 1
            continue

        if entry.msgid in TRANSLATIONS:
            entry.msgstr = TRANSLATIONS[entry.msgid]
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
            updated += 1
        elif not entry.translated() and entry.msgid in PLURAL_TRANSLATIONS:
            pass
        elif "fuzzy" in entry.flags and entry.msgid in TRANSLATIONS:
            entry.msgstr = TRANSLATIONS[entry.msgid]
            entry.flags.remove("fuzzy")
            updated += 1

    # Second pass: any remaining untranslated identical proper nouns
    for entry in po:
        if entry.msgid and not entry.translated():
            entry.msgstr = TRANSLATIONS.get(entry.msgid, entry.msgid)
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
            updated += 1

    po.save(str(PO_PATH))
    print(f"Updated {updated} entries in {PO_PATH}")


if __name__ == "__main__":
    main()
