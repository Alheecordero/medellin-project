import { getPathname } from "@/i18n/navigation";
import { routing, type AppLocale } from "@/i18n/routing";
import { SITE_URL } from "./site";

type Href = Parameters<typeof getPathname>[0]["href"];

/** Django sirve con barra final; los canónicos deben coincidir. */
function withTrailingSlash(pathname: string): string {
  if (pathname.endsWith("/")) return pathname;
  return `${pathname}/`;
}

export function localizedPath(locale: AppLocale, href: Href): string {
  return withTrailingSlash(getPathname({ href, locale }));
}

export function localizedUrl(locale: AppLocale, href: Href): string {
  return `${SITE_URL}${localizedPath(locale, href)}`;
}

export function localizedAlternates(locale: AppLocale, href: Href) {
  const languages: Record<string, string> = {};
  for (const candidate of routing.locales) {
    languages[candidate] = localizedUrl(candidate, href);
  }
  languages["x-default"] = localizedUrl(routing.defaultLocale, href);

  return {
    canonical: localizedUrl(locale, href),
    languages,
  };
}

export function openGraphLocale(locale: AppLocale): string {
  return locale === "en" ? "en_GB" : "es_CO";
}
