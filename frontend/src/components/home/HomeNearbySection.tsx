"use client";

import { useCallback, useState } from "react";
import { ArrowRight, LocateFixed, MapPin } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { PlaceCardCompact } from "@/components/places/PlaceCardCompact";
import {
  GeolocationDeniedError,
  GeolocationUnsupportedError,
  isInsideMedellin,
  requestCurrentPosition,
} from "@/lib/geolocation";
import { fetchNearbyPlaces } from "@/lib/api";
import type { Locale, PlaceCard } from "@/lib/types";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; places: PlaceCard[] }
  | { status: "empty" }
  | { status: "error"; reason: "denied" | "unsupported" | "outside" | "generic" };

/** Radios en km: se amplía hasta encontrar resultados. */
const RADII = [0.8, 2, 5];

export function HomeNearbySection() {
  const t = useTranslations("home.nearby");
  const locale = useLocale() as Locale;
  const [state, setState] = useState<State>({ status: "idle" });

  const load = useCallback(async () => {
    setState({ status: "loading" });

    let coords;
    try {
      coords = await requestCurrentPosition();
    } catch (error) {
      if (error instanceof GeolocationUnsupportedError) {
        setState({ status: "error", reason: "unsupported" });
      } else if (error instanceof GeolocationDeniedError) {
        setState({ status: "error", reason: "denied" });
      } else {
        setState({ status: "error", reason: "generic" });
      }
      return;
    }

    if (!isInsideMedellin(coords)) {
      setState({ status: "error", reason: "outside" });
      return;
    }

    try {
      for (const radio of RADII) {
        const response = await fetchNearbyPlaces({ ...coords, radio }, locale);
        if (response.lugares.length > 0) {
          setState({ status: "ready", places: response.lugares.slice(0, 6) });
          return;
        }
      }
      setState({ status: "empty" });
    } catch {
      setState({ status: "error", reason: "generic" });
    }
  }, [locale]);

  return (
    <article
      id="home-nearby"
      className="scroll-mt-[var(--sticky-below-header)] overflow-hidden rounded-2xl border border-emerald-100/90 bg-white shadow-[var(--shadow-card)]"
    >
      <div className="flex items-center justify-between gap-3 border-b border-emerald-100/80 bg-gradient-to-r from-emerald-50/80 to-white px-3 py-2.5 sm:px-4 sm:py-3">
        <div className="min-w-0 text-left">
          <h2 className="flex items-center gap-2 text-sm font-bold text-slate-900 sm:text-base">
            <MapPin className="size-4 shrink-0 text-emerald-600" aria-hidden />
            {t("title")}
          </h2>
          <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{t("subtitle")}</p>
        </div>

        {state.status === "ready" && (
          <Link
            href="/lugares"
            className="inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-emerald-800 transition hover:bg-emerald-50 sm:px-3 sm:py-1.5 sm:text-xs"
          >
            {t("viewAll")}
            <ArrowRight className="size-3" aria-hidden />
          </Link>
        )}
      </div>

      <div className="px-3 py-3 sm:px-4 sm:py-4">
        {state.status === "idle" && (
          <div className="py-6 text-center">
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-2 rounded-full bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 active:scale-[0.98]"
            >
              <LocateFixed className="size-4" aria-hidden />
              {t("cta")}
            </button>
          </div>
        )}

        {state.status === "loading" && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="h-24 animate-pulse rounded-2xl bg-slate-100" />
            ))}
          </div>
        )}

        {state.status === "ready" && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {state.places.map((place) => (
              <PlaceCardCompact key={place.slug} place={place} />
            ))}
          </div>
        )}

        {state.status === "empty" && (
          <p className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600">
            {t("empty")}
          </p>
        )}

        {state.status === "error" && (
          <div className="rounded-xl border border-amber-100 bg-amber-50 px-4 py-6 text-center text-sm text-amber-900">
            <p>{t(state.reason === "generic" ? "error" : state.reason)}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="mt-3 inline-flex items-center gap-2 rounded-full border border-amber-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-amber-900 transition hover:bg-amber-100"
            >
              <LocateFixed className="size-3.5" aria-hidden />
              {t("cta")}
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
