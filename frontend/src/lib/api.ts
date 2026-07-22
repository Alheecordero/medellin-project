import type { HomeResponse, Locale, PlaceDetailResponse, PlacesFilterResponse } from "./types";

function apiBase() {
  if (typeof window === "undefined") {
    return process.env.DJANGO_API_ORIGIN || "http://127.0.0.1:8000";
  }
  return "";
}

async function fetchJson<T>(path: string, locale: Locale = "es"): Promise<T> {
  const url = `${apiBase()}${path}${path.includes("?") ? "&" : "?"}lang=${locale}`;
  const res = await fetch(url, { next: { revalidate: 60 } });
  if (!res.ok) {
    throw new Error(`API ${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function getHome(locale: Locale) {
  return fetchJson<HomeResponse>("/api/v1/home/", locale);
}

export function getPlace(slug: string, locale: Locale) {
  return fetchJson<PlaceDetailResponse>(`/api/v1/places/${slug}/`, locale);
}

export function getPlaces(params: Record<string, string>, locale: Locale) {
  const qs = new URLSearchParams({ ...params, lang: locale });
  return fetchJson<PlacesFilterResponse>(`/api/places-filter/?${qs.toString()}`, locale);
}
