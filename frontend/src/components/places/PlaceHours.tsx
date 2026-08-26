import { Clock } from "lucide-react";
import { getLocale, getTranslations } from "next-intl/server";
import { cn } from "@/lib/cn";
import { isClosedLabel, todayIndexInMedellin, weekdayLabel } from "@/lib/format";
import type { PlaceSchedule } from "@/lib/types";

export async function PlaceHours({ schedule }: { schedule: PlaceSchedule[] }) {
  const t = await getTranslations("placeDetail");
  const locale = await getLocale();
  const today = todayIndexInMedellin();

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[var(--shadow-card)] sm:p-5">
      <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
        <Clock className="size-4 text-brand-600" aria-hidden />
        {t("hoursTitle")}
      </h2>

      {schedule.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">{t("noHours")}</p>
      ) : (
        <dl className="mt-3 divide-y divide-slate-100 text-sm">
          {schedule.map((entry, index) => {
            const closed = isClosedLabel(entry.horario);
            const isToday = index === today;

            return (
              <div
                key={index}
                className={cn(
                  "flex items-baseline justify-between gap-4 py-1.5",
                  isToday && "-mx-2 rounded-lg bg-brand-50/70 px-2",
                )}
              >
                <dt className={cn("text-slate-600", isToday && "font-bold text-brand-800")}>
                  {weekdayLabel(index, locale)}
                </dt>
                <dd
                  className={cn(
                    "text-right font-semibold tabular-nums",
                    closed ? "text-slate-400" : "text-slate-800",
                    isToday && !closed && "text-brand-800",
                  )}
                >
                  {closed ? t("closed") : entry.horario}
                </dd>
              </div>
            );
          })}
        </dl>
      )}
    </section>
  );
}
