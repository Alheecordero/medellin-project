import { defineRouting } from "next-intl/routing";

export const locales = ["es", "en"] as const;
export type AppLocale = (typeof locales)[number];

export const routing = defineRouting({
  locales,
  defaultLocale: "es",
  /**
   * Español sin prefijo, inglés bajo /en — mismo contrato que
   * i18n_patterns(prefix_default_language=False) en Django.
   */
  localePrefix: "as-needed",
  /** Sin cookie de idioma: el HTML queda cacheable en el edge. */
  localeDetection: false,
  localeCookie: false,
  /** Los slugs de ruta se traducen igual que en locale/en/LC_MESSAGES/django.po. */
  pathnames: {
    "/": "/",
    "/lugares": { es: "/lugares", en: "/places" },
    "/lugar/[slug]": { es: "/lugar/[slug]", en: "/place/[slug]" },
    "/guias": { es: "/guias", en: "/guides" },
    "/guias/[slug]": { es: "/guias/[slug]", en: "/guides/[slug]" },
  },
});

export type AppPathname = keyof typeof routing.pathnames;
