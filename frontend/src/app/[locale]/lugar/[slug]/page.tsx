import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Globe, MapPin, Navigation, Phone, Tag } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { PlaceCard } from "@/components/places/PlaceCard";
import { PlaceFeatures } from "@/components/places/PlaceFeatures";
import { PlaceGallery } from "@/components/places/PlaceGallery";
import { PlaceHours } from "@/components/places/PlaceHours";
import { PlaceReviews } from "@/components/places/PlaceReviews";
import { RelatedPlacesTabs, type RelatedTab } from "@/components/places/RelatedPlacesTabs";
import { Badge } from "@/components/ui/Badge";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Container } from "@/components/ui/Container";
import { Rating } from "@/components/ui/Rating";
import type { AppLocale } from "@/i18n/routing";
import { ApiError, fetchRelatedPlaces, type RelatedKind } from "@/lib/api";
import { getPlaceDetailCached } from "@/lib/cached-api";
import { formatPrice, parseReviewCount } from "@/lib/format";
import { pickImage } from "@/lib/images";
import { localizedAlternates, localizedUrl } from "@/lib/seo";
import { SITE_NAME } from "@/lib/site";
import type { PlaceDetail } from "@/lib/types";

export const revalidate = 300;

type Props = {
  params: Promise<{ locale: string; slug: string }>;
};

async function loadPlace(slug: string, locale: AppLocale): Promise<PlaceDetail> {
  try {
    const response = await getPlaceDetailCached(slug, locale);
    return response.lugar;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
}

function directionsUrl(place: PlaceDetail): string | null {
  if (place.lat != null && place.lng != null) {
    return `https://www.google.com/maps/dir/?api=1&destination=${place.lat},${place.lng}`;
  }
  if (place.direccion) {
    return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(place.direccion)}`;
  }
  return null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale, slug } = await params;
  const appLocale = locale as AppLocale;
  const place = await loadPlace(slug, appLocale);

  const href = { pathname: "/lugar/[slug]" as const, params: { slug } };
  const image = pickImage(place.fotos[0]) ?? pickImage(place);
  const description =
    place.descripcion?.slice(0, 300) ||
    [place.tipo, place.comuna, place.direccion].filter(Boolean).join(" · ");

  return {
    title: place.nombre,
    description,
    alternates: localizedAlternates(appLocale, href),
    openGraph: {
      title: `${place.nombre} | ${SITE_NAME}`,
      description,
      type: "website",
      url: localizedUrl(appLocale, href),
      ...(image ? { images: [{ url: image, alt: place.nombre }] } : {}),
    },
  };
}

export default async function PlaceDetailPage({ params }: Props) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const appLocale = locale as AppLocale;

  const t = await getTranslations("placeDetail");
  const tBreadcrumb = await getTranslations("breadcrumb");
  const tPlaces = await getTranslations("places");
  const tCard = await getTranslations("placeCard");

  const place = await loadPlace(slug, appLocale);

  const relatedKinds: RelatedKind[] = ["cercanos", "similares", "comuna"];
  const relatedResults = await Promise.all(
    relatedKinds.map((kind) =>
      fetchRelatedPlaces(slug, kind, appLocale).catch(() => ({ lugares: [] })),
    ),
  );

  const tabLabels: Record<RelatedKind, string> = {
    cercanos: t("related.nearby"),
    similares: t("related.similar"),
    comuna: t("related.zone"),
  };

  const tabs: RelatedTab[] = relatedKinds.map((kind, index) => {
    const places = relatedResults[index].lugares.slice(0, 6);
    return {
      id: kind,
      label: tabLabels[kind],
      count: places.length,
      content: (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {places.map((related) => (
            <PlaceCard key={related.slug} place={related} />
          ))}
        </div>
      ),
    };
  });

  const reviewCount = parseReviewCount(place.total_reviews);
  const price = formatPrice(place.precio);
  const directions = directionsUrl(place);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: place.nombre,
    ...(place.descripcion ? { description: place.descripcion } : {}),
    ...(place.direccion
      ? { address: { "@type": "PostalAddress", streetAddress: place.direccion } }
      : {}),
    ...(place.telefono ? { telephone: place.telefono } : {}),
    ...(place.sitio_web ? { url: place.sitio_web } : {}),
    ...(pickImage(place.fotos[0]) ? { image: pickImage(place.fotos[0]) } : {}),
    ...(place.lat != null && place.lng != null
      ? { geo: { "@type": "GeoCoordinates", latitude: place.lat, longitude: place.lng } }
      : {}),
    ...(place.rating && reviewCount
      ? {
          aggregateRating: {
            "@type": "AggregateRating",
            ratingValue: place.rating,
            reviewCount,
          },
        }
      : {}),
  };

  const contactLinks = [
    place.sitio_web && { href: place.sitio_web, label: t("website"), icon: Globe },
    place.telefono && { href: `tel:${place.telefono}`, label: t("phone"), icon: Phone },
    directions && { href: directions, label: t("directions"), icon: Navigation },
  ].filter(Boolean) as { href: string; label: string; icon: typeof Globe }[];

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <section className="hero-mesh relative overflow-hidden text-white">
        <Container className="relative py-7 sm:py-9">
          <Breadcrumb
            label={tBreadcrumb("aria")}
            tone="dark"
            items={[
              { label: tBreadcrumb("home"), href: "/" },
              { label: tPlaces("title"), href: "/lugares" },
              { label: place.nombre },
            ]}
          />

          <h1 className="mt-3 text-3xl font-extrabold leading-tight sm:text-4xl">{place.nombre}</h1>

          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
            <Rating
              rating={place.rating || null}
              reviewCount={reviewCount}
              className="text-white [&_span]:text-slate-300"
            />
            {place.tipo && <Badge tone="muted">{place.tipo}</Badge>}
            {price && <Badge tone="muted">{price}</Badge>}
            {place.es_exclusivo && <Badge tone="accent">{tCard("exclusive")}</Badge>}
            {place.es_destacado && !place.es_exclusivo && (
              <Badge tone="accent">{tCard("featured")}</Badge>
            )}
          </div>

          {place.direccion && (
            <p className="mt-2 flex items-start gap-1.5 text-sm text-slate-300">
              <MapPin className="mt-0.5 size-4 shrink-0 text-accent-400" aria-hidden />
              <span>
                {place.direccion}
                {place.comuna && <span className="text-slate-400"> · {place.comuna}</span>}
              </span>
            </p>
          )}

          {contactLinks.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {contactLinks.map(({ href, label, icon: Icon }) => (
                <a
                  key={label}
                  href={href}
                  target={href.startsWith("http") ? "_blank" : undefined}
                  rel={href.startsWith("http") ? "noopener noreferrer nofollow" : undefined}
                  className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-2 text-sm font-semibold text-white ring-1 ring-white/20 backdrop-blur transition hover:bg-accent-500 hover:text-brand-900 hover:ring-accent-300"
                >
                  <Icon className="size-4" aria-hidden />
                  {label}
                </a>
              ))}
            </div>
          )}
        </Container>
      </section>

      <Container className="py-6 sm:py-8">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] lg:items-start">
          <div className="space-y-5">
            <PlaceGallery photos={place.fotos} title={place.nombre} />

            {place.descripcion && (
              <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[var(--shadow-card)] sm:p-5">
                <h2 className="text-base font-bold text-slate-900">{t("aboutTitle")}</h2>
                <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-600">
                  {place.descripcion}
                </p>
              </section>
            )}

            <PlaceReviews reviews={place.reviews} />
          </div>

          <aside className="space-y-5 lg:sticky lg:top-[var(--sticky-below-header)]">
            <PlaceHours schedule={place.horarios} />
            <PlaceFeatures features={place.caracteristicas} />

            {place.tags.length > 0 && (
              <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[var(--shadow-card)] sm:p-5">
                <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
                  <Tag className="size-4 text-brand-600" aria-hidden />
                  {t("tagsTitle")}
                </h2>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {place.tags.map((tag) => (
                    <Badge key={tag} tone="brand">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </section>
            )}
          </aside>
        </div>

        <section className="mt-8">
          <RelatedPlacesTabs tabs={tabs} emptyLabel={t("related.empty")} />
        </section>
      </Container>
    </>
  );
}
