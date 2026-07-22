import type { Locale } from "./types";

export function placePath(locale: Locale, slug: string) {
  return locale === "en" ? `/en/place/${slug}/` : `/lugar/${slug}/`;
}

export function placesListPath(locale: Locale) {
  return locale === "en" ? "/en/places/" : "/lugares/";
}

export function comunaPath(locale: Locale, slug: string) {
  return locale === "en" ? `/en/places/${slug}/` : `/lugares/${slug}/`;
}

export function homePath(locale: Locale) {
  return locale === "en" ? "/en/" : "/";
}

export function aboutPath(locale: Locale) {
  return locale === "en" ? "/en/about-us/" : "/nosotros/";
}

export function switchLocalePath(currentPath: string, target: Locale): string {
  const isEn = currentPath.startsWith("/en");
  if (target === "en" && !isEn) {
    if (currentPath === "/") return "/en/";
    if (currentPath.startsWith("/lugares/")) return currentPath.replace("/lugares/", "/en/places/");
    if (currentPath.startsWith("/lugar/")) return currentPath.replace("/lugar/", "/en/place/");
    if (currentPath.startsWith("/nosotros")) return "/en/about-us/";
    return `/en${currentPath}`;
  }
  if (target === "es" && isEn) {
    if (currentPath === "/en/" || currentPath === "/en") return "/";
    if (currentPath.startsWith("/en/places/")) return currentPath.replace("/en/places/", "/lugares/");
    if (currentPath.startsWith("/en/place/")) return currentPath.replace("/en/place/", "/lugar/");
    if (currentPath.startsWith("/en/about-us")) return "/nosotros/";
    return currentPath.replace(/^\/en/, "") || "/";
  }
  return currentPath;
}
