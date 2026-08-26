"use client";

import { ArrowRight, MapPin, Star, Store } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { formatDistanceKm, formatRating, parseReviewCount } from "@/lib/format";
import { pickImage } from "@/lib/images";
import type { PlaceCard as PlaceCardData } from "@/lib/types";

/** Variante cliente de PlaceCard, para secciones que se cargan tras un fetch en el navegador. */
export function PlaceCardCompact({ place }: { place: PlaceCardData }) {
  const t = useTranslations("placeCard");

  const image = pickImage(place);
  const rating = formatRating(place.rating || null);
  const reviewCount = parseReviewCount(place.total_reviews);
  const distance = formatDistanceKm(place.distancia ?? place.distancia_km);

  return (
    <Link
      href={{ pathname: "/lugar/[slug]", params: { slug: place.slug } }}
      className="group flex gap-3 rounded-2xl border border-slate-200/90 bg-white p-2.5 transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-[0_10px_28px_-14px_rgba(17,153,142,0.35)]"
      aria-label={t("viewAria", { title: place.nombre })}
    >
      <div className="relative size-20 shrink-0 overflow-hidden rounded-xl bg-slate-100">
        <RemoteImage
          src={image}
          alt={place.nombre}
          fill
          sizes="80px"
          className="object-cover transition duration-500 group-hover:scale-105"
          fallback={
            <div className="grid size-full place-items-center bg-gradient-to-br from-brand-700 to-slate-900 text-accent-400/60">
              <Store className="size-6" aria-hidden />
            </div>
          }
        />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <h3 className="line-clamp-2 text-sm font-bold leading-snug text-slate-900 transition-colors group-hover:text-brand-700">
          {place.nombre}
        </h3>

        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-500">
          {rating && (
            <span className="inline-flex items-center gap-1 font-semibold text-slate-800">
              <Star className="size-3.5 fill-amber-400 text-amber-400" aria-hidden />
              {rating}
              {reviewCount ? <span className="font-normal text-slate-400">({reviewCount})</span> : null}
            </span>
          )}
          {place.tipo && <span className="truncate">{place.tipo}</span>}
        </div>

        <div className="mt-auto flex items-center justify-between gap-2 pt-1.5">
          {distance ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-accent-50 px-2 py-0.5 text-[11px] font-bold text-accent-800 ring-1 ring-accent-200">
              <MapPin className="size-3" aria-hidden />
              {distance}
            </span>
          ) : (
            <span className="truncate text-[11px] text-slate-400">{place.comuna}</span>
          )}
          <ArrowRight
            className="size-3.5 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-brand-600"
            aria-hidden
          />
        </div>
      </div>
    </Link>
  );
}
