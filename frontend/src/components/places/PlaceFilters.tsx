"use client";

import { useMemo } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { Label, Select } from "@/components/ui/Field";
import { iconFor } from "@/lib/icons";
import { cn } from "@/lib/cn";
import type { FeatureGroup, PlaceCategoryGroup, Zone } from "@/lib/types";

type Props = {
  zones: Zone[];
  categories: PlaceCategoryGroup[];
  featureGroups: FeatureGroup[];
  activeArea: string;
  activeType: string;
  activeFeatures: string[];
  query: string;
};

export function PlaceFilters({
  zones,
  categories,
  featureGroups,
  activeArea,
  activeType,
  activeFeatures,
  query,
}: Props) {
  const t = useTranslations("places.filters");
  const router = useRouter();

  const features = useMemo(
    () => featureGroups.flatMap((group) => group.opciones),
    [featureGroups],
  );

  const hasFilters = Boolean(activeArea || activeType || activeFeatures.length || query);

  function navigate(next: {
    area?: string;
    tipo?: string;
    features?: string[];
    q?: string;
  }) {
    const area = next.area ?? activeArea;
    const tipo = next.tipo ?? activeType;
    const selected = next.features ?? activeFeatures;
    const q = next.q ?? query;

    const params: Record<string, string> = {};
    if (area) params.area = area;
    if (tipo) params.tipo = tipo;
    if (q) params.q = q;
    for (const feature of selected) params[feature] = "true";

    router.push({ pathname: "/lugares", query: params });
  }

  function toggleFeature(field: string) {
    const next = activeFeatures.includes(field)
      ? activeFeatures.filter((item) => item !== field)
      : [...activeFeatures, field];
    navigate({ features: next });
  }

  return (
    <div className="rounded-2xl border border-brand-100 bg-white/95 p-4 shadow-[var(--shadow-card)] backdrop-blur">
      <div className="flex items-center justify-between gap-3">
        <p className="inline-flex items-center gap-2 text-sm font-bold text-slate-900">
          <SlidersHorizontal className="size-4 text-brand-600" aria-hidden />
          {t("legend")}
        </p>
        {hasFilters && (
          <button
            type="button"
            onClick={() => router.push({ pathname: "/lugares", query: {} })}
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 transition hover:border-brand-300 hover:text-brand-700"
          >
            <X className="size-3" aria-hidden />
            {t("clear")}
          </button>
        )}
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <Label>{t("area")}</Label>
          <Select value={activeArea} onChange={(event) => navigate({ area: event.target.value })}>
            <option value="">{t("allAreas")}</option>
            {zones.map((zone) => (
              <option key={zone.slug} value={zone.slug}>
                {zone.name}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <Label>{t("type")}</Label>
          <Select value={activeType} onChange={(event) => navigate({ tipo: event.target.value })}>
            <option value="">{t("allTypes")}</option>
            {categories.map((group) => (
              <optgroup key={group.name} label={group.name}>
                {group.subcategorias.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
        </div>
      </div>

      {features.length > 0 && (
        <div className="mt-4">
          <Label>{t("features")}</Label>
          <div className="flex flex-wrap gap-1.5">
            {features.map((feature) => {
              const Icon = iconFor(feature.icon);
              const active = activeFeatures.includes(feature.field);

              return (
                <button
                  key={feature.field}
                  type="button"
                  onClick={() => toggleFeature(feature.field)}
                  aria-pressed={active}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition",
                    active
                      ? "border-accent-500 bg-accent-500 text-brand-900 shadow-[0_4px_14px_-6px_rgba(56,239,125,0.6)]"
                      : "border-slate-200 bg-white text-slate-600 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700",
                  )}
                >
                  <Icon className="size-3.5" aria-hidden />
                  {feature.name}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
