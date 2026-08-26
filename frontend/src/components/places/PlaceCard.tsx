import { ArrowRight, MapPin, Store } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Badge } from "@/components/ui/Badge";
import { Rating } from "@/components/ui/Rating";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { formatDistanceKm, formatPrice, parseReviewCount } from "@/lib/format";
import { pickImage } from "@/lib/images";
import type { PlaceCard as PlaceCardData } from "@/lib/types";

const placeholder = (
  <div className="grid size-full place-items-center bg-gradient-to-br from-brand-800 via-slate-900 to-slate-950 text-accent-400/60">
    <Store className="size-10" aria-hidden />
  </div>
);

export async function PlaceCard({
  place,
  priority = false,
}: {
  place: PlaceCardData;
  priority?: boolean;
}) {
  const t = await getTranslations("placeCard");

  const image = pickImage(place);
  const reviewCount = parseReviewCount(place.total_reviews);
  const price = formatPrice(place.precio);
  const distance = formatDistanceKm(place.distancia ?? place.distancia_km);

  return (
    <Link
      href={{ pathname: "/lugar/[slug]", params: { slug: place.slug } }}
      className="group block h-full rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2"
      aria-label={t("viewAria", { title: place.nombre })}
    >
      <article className="relative flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[var(--shadow-card)] transition-all duration-300 group-hover:-translate-y-1 group-hover:border-brand-300/80 group-hover:shadow-[0_12px_40px_-12px_rgba(17,153,142,0.28)]">
        <span
          className="absolute inset-y-0 left-0 z-10 w-1 scale-y-0 bg-gradient-to-b from-accent-500 to-brand-600 transition duration-300 group-hover:scale-y-100"
          aria-hidden
        />

        <div className="relative aspect-[4/3] overflow-hidden bg-slate-100 sm:aspect-[3/2] lg:aspect-[5/3] lg:max-h-44">
          <RemoteImage
            src={image}
            alt={place.nombre}
            fill
            priority={priority}
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            className="object-cover transition duration-500 group-hover:scale-[1.04]"
            fallback={placeholder}
          />

          <div className="absolute inset-0 bg-gradient-to-t from-slate-950/75 via-slate-950/10 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-tr from-brand-900/35 via-transparent to-transparent" />

          <div className="absolute inset-x-3 top-3 flex flex-wrap justify-end gap-1.5">
            {place.es_exclusivo && <Badge tone="accent">{t("exclusive")}</Badge>}
            {place.es_destacado && !place.es_exclusivo && <Badge tone="brand">{t("featured")}</Badge>}
          </div>

          {(place.comuna || distance) && (
            <div className="absolute inset-x-3 bottom-3">
              <p className="inline-flex items-center gap-1.5 rounded-full bg-white/12 px-2.5 py-1 text-xs font-semibold text-white/90 ring-1 ring-white/15 backdrop-blur">
                <MapPin className="size-3" aria-hidden />
                {distance ?? place.comuna}
              </p>
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col px-4 pb-4 pt-3">
          <h3 className="line-clamp-2 font-bold leading-snug text-slate-900 transition-colors group-hover:text-brand-700">
            {place.nombre}
          </h3>

          {place.direccion && (
            <p className="mt-1 flex items-start gap-1.5 text-sm text-slate-500">
              <MapPin className="mt-0.5 size-3.5 shrink-0 text-slate-400" aria-hidden />
              <span className="line-clamp-2">{place.direccion}</span>
            </p>
          )}

          <div className="mt-1.5 flex items-center gap-2">
            <Rating rating={place.rating || null} reviewCount={reviewCount} className="text-sm" />
            {price && <span className="text-sm font-semibold text-slate-400">{price}</span>}
          </div>

          {place.tipo && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-semibold text-brand-800 ring-1 ring-brand-100">
                {place.tipo}
              </span>
            </div>
          )}

          <div className="mt-auto flex items-center justify-end gap-2 border-t border-brand-100/80 pt-3">
            <span className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-accent-500 to-accent-400 px-3 py-1.5 text-xs font-bold text-brand-900 shadow-[0_4px_14px_-4px_rgba(56,239,125,0.55)] transition group-hover:from-accent-400 group-hover:to-accent-300">
              {t("view")} <ArrowRight className="size-3.5" aria-hidden />
            </span>
          </div>
        </div>
      </article>
    </Link>
  );
}
