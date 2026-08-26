export type Locale = "es" | "en";

/** Card de lugar. Shape de _serialize_place_card en explorer/api_v1.py. */
export interface PlaceCard {
  nombre: string;
  slug: string;
  rating: number;
  total_reviews: number | null;
  tipo: string;
  /** Variante pedida (thumb o medium según el endpoint). */
  imagen?: string | null;
  /** Original. */
  imagen_full?: string | null;
  es_destacado?: boolean;
  es_exclusivo?: boolean;
  precio?: string | null;
  direccion?: string | null;
  comuna?: string | null;
  /** URL de Django. El frontend construye sus enlaces con next-intl, no con esto. */
  url?: string | null;
  /** Solo en /api/lugares-cercanos/ y en los relacionados por proximidad. */
  distancia?: number;
  distancia_km?: number;
}

/** RegionOSM: comuna de Medellín (admin_level 8) o municipio (admin_level 6). */
export interface Zone {
  osm_id: number;
  name: string;
  slug: string;
  admin_level?: string | null;
}

export interface ZoneChip {
  osm_id: number;
  name: string;
  slug: string;
}

export interface PlaceTypeOption {
  value: string;
  name: string;
}

export interface PlaceCategoryGroup {
  name: string;
  /** Clase de Bootstrap Icons, p. ej. "bi-cup-hot". */
  icon: string;
  color: string;
  subcategorias: PlaceTypeOption[];
}

export interface FeatureOption {
  /** Nombre del campo booleano en el modelo Places. */
  field: string;
  name: string;
  icon: string;
}

export interface FeatureGroup {
  name: string;
  icon: string;
  opciones: FeatureOption[];
}

export interface HomeFilters {
  areas: Zone[];
  comunas_medellin_chips: ZoneChip[];
  otras_regiones_chips: ZoneChip[];
  categorias: PlaceCategoryGroup[];
  etiquetas: FeatureGroup[];
}

export interface ZoneBlock {
  nombre: string;
  slug: string;
  es_municipio: boolean;
  lugares: PlaceCard[];
}

export interface HomeResponse {
  success: boolean;
  lang: string;
  lugares_imperdibles: PlaceCard[];
  comuna_con_lugares: ZoneBlock[];
  filtros: HomeFilters;
}

export interface Pagination {
  pagina_actual: number;
  total_paginas: number;
  tiene_anterior: boolean;
  tiene_siguiente: boolean;
  pagina_anterior: number | null;
  pagina_siguiente: number | null;
}

export interface AppliedFilters {
  area: { slug: string; name: string; osm_id: number } | null;
  tipo: string | null;
  tipo_label: string | null;
  caracteristicas: { key: string; label: string }[];
}

export interface PlacesFilterResponse {
  success: boolean;
  total: number;
  lugares: PlaceCard[];
  mensaje: string;
  filtros_aplicados: AppliedFilters;
  paginacion: Pagination;
}

/** Devuelto por PlaceDetailView._get_caracteristicas: icono + etiqueta. */
export interface PlaceFeature {
  icon: string;
  name: string;
}

export interface PlaceSchedule {
  dia: string;
  horario: string;
}

export interface PlacePhoto {
  imagen?: string | null;
  imagen_full?: string | null;
  alt?: string;
}

/** Reseña cruda de Google Places; los campos varían según la versión de la API. */
export interface PlaceReview {
  author_name?: string;
  authorAttribution?: { displayName?: string; photoUri?: string };
  rating?: number;
  text?: string | { text?: string };
  relative_time_description?: string;
  relativePublishTimeDescription?: string;
  profile_photo_url?: string;
}

export interface PlaceDetail extends PlaceCard {
  descripcion?: string | null;
  telefono?: string | null;
  sitio_web?: string | null;
  horario_json?: Record<string, string> | null;
  horarios: PlaceSchedule[];
  caracteristicas: PlaceFeature[];
  lat: number | null;
  lng: number | null;
  tags: string[];
  fotos: PlacePhoto[];
  reviews: PlaceReview[];
  adsense_allowed?: boolean;
}

export interface PlaceDetailResponse {
  success: boolean;
  lang: string;
  lugar: PlaceDetail;
  endpoints: {
    cercanos: string;
    similares: string;
    comuna: string;
  };
}

export interface RelatedPlacesResponse {
  lugares: PlaceCard[];
  comuna_nombre?: string;
}

export interface NearbyResponse {
  success: boolean;
  total: number;
  lugares: PlaceCard[];
  mensaje: string;
  ubicacion_usuario?: { lat: number; lng: number; radio: number };
}
