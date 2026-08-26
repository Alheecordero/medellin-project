import type { Metadata } from "next";
import { Store } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { PlaceCard } from "@/components/places/PlaceCard";
import { PlaceFilters } from "@/components/places/PlaceFilters";
import { ApiErrorBanner } from "@/components/ui/ApiErrorBanner";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import type { AppLocale } from "@/i18n/routing";
import { fetchPlaces, fetchSemanticSearch, isPlaceFeatureField } from "@/lib/api";
import { getHomeCached } from "@/lib/cached-api";
import { localizedAlternates } from "@/lib/seo";
import type { HomeResponse, PlaceCard as PlaceCardData, Pagination as PaginationData } from "@/lib/types";

export const revalidate = 300;

type SearchParams = Record<string, string | string[] | undefined>;

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<SearchParams>;
};

function firstValue(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

function parseSearchParams(searchParams: SearchParams) {
  const page = Number.parseInt(firstValue(searchParams.page), 10);

  return {
    area: firstValue(searchParams.area),
    tipo: firstValue(searchParams.tipo),
    query: firstValue(searchParams.q).trim(),
    page: Number.isFinite(page) && page > 0 ? page : 1,
    features: Object.keys(searchParams).filter(
      (key) => isPlaceFeatureField(key) && firstValue(searchParams[key]) === "true",
    ),
  };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "places" });

  return {
    title: t("title"),
    description: t("subtitle"),
    alternates: localizedAlternates(locale as AppLocale, "/lugares"),
  };
}

export default async function PlacesPage({ params, searchParams }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const appLocale = locale as AppLocale;

  const t = await getTranslations("places");
  const tSearch = await getTranslations("search");
  const tBreadcrumb = await getTranslations("breadcrumb");

  const { area, tipo, query, page, features } = parseSearchParams(await searchParams);

  let filters: HomeResponse["filtros"] | null = null;
  try {
    filters = (await getHomeCached(appLocale)).filtros;
  } catch {
    filters = null;
  }

  let places: PlaceCardData[] = [];
  let total = 0;
  let pagination: PaginationData | null = null;
  let apiError = false;
  let searchUnavailable = false;

  if (query) {
    // El backend solo ofrece búsqueda semántica; no devuelve paginación.
    try {
      const response = await fetchSemanticSearch(query, appLocale);
      places = response.lugares;
      total = response.total;
    } catch {
      searchUnavailable = true;
    }
  } else {
    try {
      const response = await fetchPlaces({ area, tipo, page, features }, appLocale);
      places = response.lugares;
      total = response.total;
      pagination = response.paginacion;
    } catch {
      apiError = true;
    }
  }

  const hasFilters = Boolean(area || tipo || features.length || query);

  return (
    <>
      <section className="hero-mesh relative overflow-hidden text-white">
        <Container className="relative py-8 sm:py-10">
          <Breadcrumb
            label={tBreadcrumb("aria")}
            tone="dark"
            items={[{ label: tBreadcrumb("home"), href: "/" }, { label: t("title") }]}
          />
          <h1 className="mt-3 text-3xl font-extrabold leading-tight sm:text-4xl">
            {query ? tSearch("resultsFor", { query }) : t("title")}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-300 sm:text-base">{t("subtitle")}</p>
          {!apiError && !searchUnavailable && (
            <p className="mt-3 inline-flex items-center rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-accent-300 ring-1 ring-white/15">
              {t("resultsCount", { count: total })}
            </p>
          )}
        </Container>
      </section>

      <Container className="py-6 sm:py-8">
        {apiError && <ApiErrorBanner className="mb-4" />}

        {searchUnavailable && (
          <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
            {tSearch("unavailable")}
          </div>
        )}

        {filters && (
          <PlaceFilters
            zones={filters.areas}
            categories={filters.categorias}
            featureGroups={filters.etiquetas}
            activeArea={area}
            activeType={tipo}
            activeFeatures={features}
            query={query}
          />
        )}

        <div className="mt-6">
          {places.length > 0 ? (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {places.map((place, index) => (
                <PlaceCard key={place.slug} place={place} priority={index < 3} />
              ))}
            </div>
          ) : (
            !apiError && (
              <EmptyState
                icon={Store}
                title={t("empty.title")}
                description={t("empty.description")}
                action={
                  hasFilters ? (
                    <Link
                      href="/lugares"
                      className="inline-flex h-10 items-center rounded-full bg-brand-600 px-5 text-sm font-semibold text-white transition hover:bg-brand-700"
                    >
                      {t("filters.clear")}
                    </Link>
                  ) : null
                }
              />
            )
          )}
        </div>

        {pagination && (
          <Pagination
            page={pagination.pagina_actual}
            totalPages={pagination.total_paginas}
            hasPrev={pagination.tiene_anterior}
            hasNext={pagination.tiene_siguiente}
            hrefForPage={(target) => ({
              pathname: "/lugares",
              query: {
                ...(area ? { area } : {}),
                ...(tipo ? { tipo } : {}),
                ...Object.fromEntries(features.map((feature) => [feature, "true"])),
                ...(target > 1 ? { page: String(target) } : {}),
              },
            })}
          />
        )}
      </Container>
    </>
  );
}
