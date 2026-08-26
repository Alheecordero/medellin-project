import { Suspense } from "react";
import { ArrowRight } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { HomeNearbySection } from "@/components/home/HomeNearbySection";
import { PlaceTypeChips } from "@/components/home/PlaceTypeChips";
import { ZoneTile } from "@/components/home/ZoneTile";
import { PlaceCard } from "@/components/places/PlaceCard";
import { SearchForm } from "@/components/search/SearchForm";
import { ApiErrorBanner } from "@/components/ui/ApiErrorBanner";
import { Container } from "@/components/ui/Container";
import { getHomeCached } from "@/lib/cached-api";
import { formatCount } from "@/lib/format";
import { pickImage } from "@/lib/images";
import type { HomeResponse, Locale } from "@/lib/types";

const sectionHeader =
  "flex items-center justify-between gap-3 border-b px-3 py-2.5 sm:px-4 sm:py-3";

const pillLink =
  "inline-flex shrink-0 items-center gap-1 rounded-full border border-brand-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-brand-700 transition hover:bg-brand-50 sm:px-3 sm:py-1.5 sm:text-xs";

export async function HomeSections({ locale }: { locale: Locale }) {
  const t = await getTranslations("home");

  let data: HomeResponse | null = null;
  try {
    data = await getHomeCached(locale);
  } catch {
    data = null;
  }

  const zones = data?.comuna_con_lugares ?? [];
  const categories = data?.filtros?.categorias ?? [];
  const mustSee = (data?.lugares_imperdibles ?? []).slice(0, 6);
  const searchZones = data?.filtros?.areas ?? [];

  const totalPlaces = zones.reduce((sum, zone) => sum + zone.lugares.length, 0);

  return (
    <section className="relative z-10 -mt-16 sm:-mt-20">
      <Container className="max-w-5xl px-4 pb-8 pt-0 sm:pb-10">
        <div className="mx-auto max-w-2xl text-center">
          {zones.length > 0 && (
            <p className="text-sm font-semibold text-white/95 [text-shadow:0_1px_3px_rgba(0,0,0,0.4)] sm:text-base">
              {t("quickStats", {
                places: formatCount(totalPlaces, locale),
                zones: formatCount(zones.length, locale),
              })}
            </p>
          )}

          <SearchForm
            className="mx-auto mt-3 max-w-xl"
            zones={searchZones}
            placeholder={undefined}
          />

          {!data && <ApiErrorBanner className="mt-3" />}
        </div>

        <div className="mt-4 space-y-3 sm:mt-5 sm:space-y-4">
          {categories.length > 0 && (
            <article className="rounded-2xl border border-brand-100/80 bg-white shadow-[0_8px_30px_-12px_rgba(17,153,142,0.18)]">
              <div className={`${sectionHeader} border-brand-100/70 bg-gradient-to-r from-brand-50/80 to-white`}>
                <div className="min-w-0 text-left">
                  <h2 className="text-sm font-bold text-slate-900 sm:text-base">
                    {t("placeTypesTitle")}
                  </h2>
                  <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">
                    {t("placeTypesSubtitle")}
                  </p>
                </div>
                <Link href="/lugares" className={pillLink}>
                  {t("placeTypesViewAll")}
                  <ArrowRight className="size-3" aria-hidden />
                </Link>
              </div>
              <div className="px-3 py-3 sm:px-4 sm:py-4">
                <PlaceTypeChips groups={categories} />
              </div>
            </article>
          )}

          <HomeNearbySection />

          {zones.length > 0 && (
            <article className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[var(--shadow-card)]">
              <div className={`${sectionHeader} border-slate-100`}>
                <div className="min-w-0 text-left">
                  <h2 className="text-sm font-bold text-slate-900 sm:text-base">
                    {t("zonesTitle")}
                  </h2>
                  <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">{t("zonesSubtitle")}</p>
                </div>
                <Link href="/lugares" className={pillLink}>
                  {t("viewAll")}
                  <ArrowRight className="size-3" aria-hidden />
                </Link>
              </div>
              <div className="grid grid-cols-2 gap-2 p-2.5 sm:grid-cols-3 sm:gap-2.5 sm:p-3 md:grid-cols-4 xl:grid-cols-6">
                {zones.map((zone, index) => (
                  <ZoneTile
                    key={zone.slug}
                    slug={zone.slug}
                    name={zone.nombre}
                    eager={index < 2}
                    image={pickImage(zone.lugares[0])}
                    countLabel={t("placesInZone", { count: zone.lugares.length })}
                  />
                ))}
              </div>
            </article>
          )}

          {mustSee.length > 0 && (
            <article className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[var(--shadow-card)]">
              <div className={`${sectionHeader} border-slate-100`}>
                <div className="min-w-0 text-left">
                  <h2 className="text-sm font-bold text-slate-900 sm:text-base">
                    {t("mustSeeTitle")}
                  </h2>
                  <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">
                    {t("mustSeeSubtitle")}
                  </p>
                </div>
              </div>
              <div className="grid gap-3 p-2.5 sm:grid-cols-2 sm:gap-4 sm:p-4 lg:grid-cols-3">
                {mustSee.map((place) => (
                  <PlaceCard key={place.slug} place={place} />
                ))}
              </div>
            </article>
          )}
        </div>
      </Container>
    </section>
  );
}

export function HomeSectionsFallback() {
  return (
    <section className="relative z-10 -mt-16 sm:-mt-20">
      <Container className="max-w-5xl px-4 pb-8 pt-0 sm:pb-10">
        <div className="mx-auto h-24 w-full max-w-xl animate-pulse rounded-2xl bg-white/20" />
        <div className="mt-4 space-y-3 sm:mt-5 sm:space-y-4">
          <div className="h-40 animate-pulse rounded-2xl bg-slate-100" />
          <div className="h-56 animate-pulse rounded-2xl bg-slate-100" />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
            {Array.from({ length: 12 }).map((_, index) => (
              <div key={index} className="aspect-[5/4] animate-pulse rounded-2xl bg-slate-100" />
            ))}
          </div>
        </div>
      </Container>
    </section>
  );
}

export function HomeSectionsWithSuspense({ locale }: { locale: Locale }) {
  return (
    <Suspense fallback={<HomeSectionsFallback />}>
      <HomeSections locale={locale} />
    </Suspense>
  );
}
