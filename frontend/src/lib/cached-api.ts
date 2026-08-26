import { cache } from "react";
import { fetchHome, fetchPlaceDetail } from "./api";
import type { Locale } from "./types";

/**
 * Deduplica las llamadas dentro de un mismo render: la home y el detalle se
 * consultan tanto en generateMetadata como en el componente de página.
 */
export const getHomeCached = cache((locale: Locale) => fetchHome(locale));

export const getPlaceDetailCached = cache((slug: string, locale: Locale) =>
  fetchPlaceDetail(slug, locale),
);
