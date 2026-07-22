export type Locale = "es" | "en";

export interface PlaceCard {
  nombre: string;
  slug: string;
  rating: number;
  total_reviews: number;
  tipo: string;
  imagen?: string;
  imagen_miniatura?: string;
  imagen_mediana?: string;
  es_destacado?: boolean;
  es_exclusivo?: boolean;
  precio?: string | null;
  direccion?: string | null;
  comuna?: string | null;
  url?: string;
}

export interface HomeResponse {
  success: boolean;
  lang: string;
  lugares_imperdibles: PlaceCard[];
  comuna_con_lugares: Array<{
    nombre: string;
    slug: string;
    es_municipio: boolean;
    lugares: PlaceCard[];
  }>;
  filtros: {
    areas: Array<{ osm_id: number; name: string; slug: string; admin_level: string }>;
    comunas_medellin_chips: Array<{ osm_id: number; name: string; slug: string }>;
    otras_regiones_chips: Array<{ osm_id: number; name: string; slug: string }>;
    categorias: unknown[];
    etiquetas: unknown[];
  };
}

export interface PlaceDetailResponse {
  success: boolean;
  lang: string;
  lugar: PlaceCard & {
    descripcion?: string;
    telefono?: string;
    sitio_web?: string;
    horarios?: unknown;
    caracteristicas?: string[];
    lat?: number | null;
    lng?: number | null;
    tags?: string[];
    fotos?: Array<{ imagen?: string; imagen_mediana?: string; imagen_miniatura?: string; alt?: string }>;
    reviews?: unknown[];
    adsense_allowed?: boolean;
  };
  endpoints: Record<string, string>;
}

export interface PlacesFilterResponse {
  success: boolean;
  total: number;
  lugares: PlaceCard[];
  has_next?: boolean;
  has_previous?: boolean;
  page?: number;
  total_pages?: number;
}
