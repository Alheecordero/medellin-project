export const SITE_NAME = "ViveMedellín";

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://vivemedellin.net"
).replace(/\/$/, "");

export const BRAND_FAVICON_SRC = "/favicon.svg";
export const BRAND_ICON_SRC = "/brand/icon-512.png";
export const BRAND_OG_SRC = "/brand/og-image.jpg";

/** Imagen del hero de la home, con variantes pregeneradas cacheables en el edge. */
export const HERO_IMAGE_SRC = "/home/hero-medellin-1440.webp";
export const HERO_IMAGE_SRCSET =
  "/home/hero-medellin-640.webp 640w, /home/hero-medellin-960.webp 960w, /home/hero-medellin-1440.webp 1440w";

/** Zonas destacadas del footer (slugs de RegionOSM). */
export const FOOTER_ZONES = [
  { slug: "el-poblado", name: "El Poblado" },
  { slug: "laureles-estadio", name: "Laureles - Estadio" },
  { slug: "envigado", name: "Envigado" },
  { slug: "belen", name: "Belén" },
  { slug: "sabaneta", name: "Sabaneta" },
] as const;

/**
 * Páginas que aún sirve Django (about, legal, contacto). Se enlazan en absoluto
 * para que funcionen también con el frontend corriendo en :3000.
 */
export const DJANGO_PAGES = {
  about: { es: "/nosotros/", en: "/en/about-us/" },
  privacy: { es: "/politica-de-privacidad/", en: "/politica-de-privacidad/" },
  terms: { es: "/terminos-y-condiciones/", en: "/terminos-y-condiciones/" },
  contact: { es: "/contacto/", en: "/contacto/" },
} as const;

export function djangoPageUrl(page: keyof typeof DJANGO_PAGES, locale: "es" | "en"): string {
  return `${SITE_URL}${DJANGO_PAGES[page][locale]}`;
}
