import type { AppLocale } from "@/i18n/routing";

export function numberLocale(locale: string): string {
  return locale === "en" ? "en-GB" : "es-CO";
}

export function formatRating(rating: number | null | undefined): string | null {
  if (rating == null || Number.isNaN(rating)) return null;
  return rating.toFixed(1);
}

export function formatCount(value: number | null | undefined, locale: string): string {
  if (!value) return "0";
  return value.toLocaleString(numberLocale(locale));
}

export function formatDistanceKm(km: number | null | undefined): string | null {
  if (km == null || Number.isNaN(km)) return null;
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(1)} km`;
}

/** El backend guarda el rango de precio de Google como "$", "$$"… o texto libre. */
export function formatPrice(precio: string | null | undefined): string | null {
  if (!precio) return null;
  const trimmed = precio.trim();
  return trimmed && trimmed !== "$" ? trimmed : null;
}

/** Normaliza el conteo de reseñas, que a veces llega como string. */
export function parseReviewCount(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const parsed = parseInt(value.replace(/[^\d]/g, ""), 10);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
}

/**
 * _format_horarios devuelve los días en español y siempre en orden lunes→domingo,
 * así que el nombre localizado se deriva del índice, no de la cadena.
 */
export function weekdayLabel(index: number, locale: string): string {
  // 2024-01-01 fue lunes.
  const date = new Date(Date.UTC(2024, 0, 1 + index));
  const label = new Intl.DateTimeFormat(numberLocale(locale), {
    weekday: "long",
    timeZone: "UTC",
  }).format(date);
  return label.charAt(0).toLocaleUpperCase(numberLocale(locale)) + label.slice(1);
}

export function isClosedLabel(value: string): boolean {
  return value.trim().toLowerCase() === "cerrado";
}

/** Índice del día actual con lunes = 0, en la zona horaria de Medellín. */
export function todayIndexInMedellin(): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    timeZone: "America/Bogota",
  }).format(new Date());
  const order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const index = order.indexOf(parts);
  return index === -1 ? 0 : index;
}

export function isLocale(value: string): value is AppLocale {
  return value === "es" || value === "en";
}
