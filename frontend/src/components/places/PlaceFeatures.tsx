import { Sparkles } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { iconFor } from "@/lib/icons";
import type { PlaceFeature } from "@/lib/types";

export async function PlaceFeatures({ features }: { features: PlaceFeature[] }) {
  if (features.length === 0) return null;
  const t = await getTranslations("placeDetail");

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[var(--shadow-card)] sm:p-5">
      <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
        <Sparkles className="size-4 text-brand-600" aria-hidden />
        {t("featuresTitle")}
      </h2>

      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {features.map((feature) => {
          const Icon = iconFor(feature.icon);
          return (
            <li
              key={feature.name}
              className="flex items-center gap-2.5 rounded-xl bg-brand-50/60 px-3 py-2 text-sm font-medium text-slate-700 ring-1 ring-brand-100"
            >
              <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-white text-brand-700 ring-1 ring-brand-100">
                <Icon className="size-4" aria-hidden />
              </span>
              {feature.name}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
