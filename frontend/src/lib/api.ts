import type {
  HomeResponse,
  Locale,
  NearbyResponse,
  PlaceCard,
  PlaceDetailResponse,
  PlacesFilterResponse,
  RelatedPlacesResponse,
} from "./types";

/** En el servidor pegamos directo a Django; en el navegador usamos el rewrite /api. */
export function getApiBase(): string {
  if (typeof window === "undefined") {
    return process.env.DJANGO_API_ORIGIN || "http://127.0.0.1:8000";
  }
  return "";
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
  ) {
    super(`API ${path} respondió ${status}`);
    this.name = "ApiError";
  }
}

type FetchOptions = {
  locale?: Locale;
  revalidate?: number;
  /** Para peticiones del cliente que no deben cachearse. */
  noStore?: boolean;
};

async function fetchJson<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { locale = "es", revalidate = 600, noStore = false } = options;
  const separator = path.includes("?") ? "&" : "?";
  const url = `${getApiBase()}${path}${separator}lang=${locale}`;

  const res = await fetch(url, {
    // Accept-Language cubre los endpoints AJAX legacy, que no leen ?lang.
    headers: { Accept: "application/json", "Accept-Language": locale },
    ...(noStore ? { cache: "no-store" } : { next: { revalidate } }),
  });

  if (!res.ok) {
    throw new ApiError(res.status, path);
  }

  return (await res.json()) as T;
}

/** Datos de arranque de la home: imperdibles, bloques por zona y filtros. */
export function fetchHome(locale: Locale): Promise<HomeResponse> {
  return fetchJson<HomeResponse>("/api/v1/home/", { locale, revalidate: 600 });
}

/**
 * Campos booleanos que acepta /api/places-filter/. Se omite `reservable`
 * a propósito: la vista lo lista pero el modelo Places no tiene esa columna,
 * así que filtrar por él devuelve un 500.
 */
export const PLACE_FEATURE_FIELDS = [
  "delivery",
  "takeout",
  "dine_in",
  "outdoor_seating",
  "live_music",
  "good_for_groups",
  "good_for_children",
  "serves_cocktails",
  "serves_wine",
  "serves_coffee",
  "serves_dessert",
  "wheelchair_accessible_entrance",
  "allows_dogs",
  "accepts_credit_cards",
] as const;

export function isPlaceFeatureField(value: string): boolean {
  return (PLACE_FEATURE_FIELDS as readonly string[]).includes(value);
}

export type PlacesQuery = {
  area?: string;
  tipo?: string;
  page?: number;
  /** Campos booleanos del modelo Places, p. ej. outdoor_seating. */
  features?: string[];
};

export function buildPlacesSearchParams(query: PlacesQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.area) params.set("area", query.area);
  if (query.tipo) params.set("tipo", query.tipo);
  if (query.page && query.page > 1) params.set("page", String(query.page));
  for (const feature of query.features ?? []) {
    params.set(feature, "true");
  }
  return params;
}

/** Listado paginado (12 por página, fijo en el backend). */
export function fetchPlaces(query: PlacesQuery, locale: Locale): Promise<PlacesFilterResponse> {
  const params = buildPlacesSearchParams(query);
  const qs = params.toString();
  return fetchJson<PlacesFilterResponse>(`/api/places-filter/${qs ? `?${qs}` : ""}`, {
    locale,
    revalidate: 300,
  });
}

export function fetchPlaceDetail(slug: string, locale: Locale): Promise<PlaceDetailResponse> {
  return fetchJson<PlaceDetailResponse>(`/api/v1/places/${encodeURIComponent(slug)}/`, {
    locale,
    revalidate: 300,
  });
}

export type RelatedKind = "cercanos" | "similares" | "comuna";

export function fetchRelatedPlaces(
  slug: string,
  kind: RelatedKind,
  locale: Locale,
): Promise<RelatedPlacesResponse> {
  return fetchJson<RelatedPlacesResponse>(
    `/api/lugares/${encodeURIComponent(slug)}/${kind}/`,
    { locale, revalidate: 300 },
  );
}

export interface SemanticSearchResponse {
  success: boolean;
  query: string;
  total: number;
  lugares: (PlaceCard & { score?: number })[];
}

/**
 * Único endpoint de búsqueda por texto del backend (pgvector + Vertex AI).
 * Puede fallar si el entorno no tiene embeddings generados.
 */
export function fetchSemanticSearch(
  query: string,
  locale: Locale,
  top = 12,
): Promise<SemanticSearchResponse> {
  const params = new URLSearchParams({ q: query, top: String(top) });
  return fetchJson<SemanticSearchResponse>(`/api/semantic-search/?${params.toString()}`, {
    locale,
    revalidate: 300,
  });
}

export type NearbyQuery = {
  lat: number;
  lng: number;
  /** Radio en km. El backend usa 0.8 por defecto. */
  radio?: number;
  tipo?: string;
};

/** Se llama desde el cliente tras obtener permiso de geolocalización. */
export function fetchNearbyPlaces(query: NearbyQuery, locale: Locale): Promise<NearbyResponse> {
  const params = new URLSearchParams({
    lat: String(query.lat),
    lng: String(query.lng),
  });
  if (query.radio) params.set("radio", String(query.radio));
  if (query.tipo) params.set("tipo", query.tipo);

  return fetchJson<NearbyResponse>(`/api/lugares-cercanos/?${params.toString()}`, {
    locale,
    noStore: true,
  });
}
