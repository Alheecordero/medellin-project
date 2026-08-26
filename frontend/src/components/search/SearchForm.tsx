"use client";

import { useState, type FormEvent } from "react";
import { MapPin, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { cn } from "@/lib/cn";
import type { Zone, ZoneChip } from "@/lib/types";

type Props = {
  zones?: (Zone | ZoneChip)[];
  defaultQ?: string;
  defaultZone?: string;
  className?: string;
  compact?: boolean;
  dark?: boolean;
  showZone?: boolean;
  placeholder?: string;
  submitLabel?: string;
  onNavigate?: () => void;
};

export function SearchForm({
  zones = [],
  defaultQ = "",
  defaultZone = "",
  className,
  compact,
  dark,
  showZone = true,
  placeholder,
  submitLabel,
  onNavigate,
}: Props) {
  const t = useTranslations("search");
  const router = useRouter();
  const [q, setQ] = useState(defaultQ);
  const [zone, setZone] = useState(defaultZone);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onNavigate?.();

    const query: Record<string, string> = {};
    const trimmed = q.trim();
    if (trimmed) query.q = trimmed;
    if (zone) query.area = zone;

    router.push({ pathname: "/lugares", query });
  }

  const fieldClass = cn(
    "flex items-center gap-2 rounded-xl px-3 ring-1 transition focus-within:ring-2",
    compact ? "h-10" : "h-12",
    dark
      ? "bg-white/18 ring-white/25 focus-within:bg-white/22 focus-within:ring-accent-300/70"
      : "bg-white ring-slate-200 focus-within:ring-brand-400",
  );

  const inputClass = cn(
    "w-full bg-transparent text-sm focus:outline-none",
    compact ? "h-10" : "h-12",
    dark ? "text-white placeholder:text-slate-300" : "text-slate-900 placeholder:text-slate-400",
  );

  return (
    <form onSubmit={handleSubmit} role="search" className={cn("relative", className)}>
      <div
        className={cn(
          "flex flex-col gap-2 rounded-2xl",
          compact ? "md:flex-row" : "sm:flex-row",
          compact ? "" : "bg-white p-2 shadow-2xl shadow-black/20",
          dark && compact ? "bg-transparent" : "",
        )}
      >
        <div className={cn(fieldClass, "flex-1")}>
          <Search
            className={cn("size-5 shrink-0", dark ? "text-slate-300" : "text-slate-400")}
            aria-hidden
          />
          <input
            name="q"
            type="search"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={placeholder ?? t("placeholder")}
            aria-label={t("ariaLabel")}
            className={inputClass}
          />
        </div>

        {showZone && zones.length > 0 && (
          <>
            <div
              className={cn(
                "hidden w-px",
                compact ? "md:block" : "sm:block",
                dark ? "bg-white/15" : "bg-slate-200",
              )}
            />
            <div className={cn(fieldClass, "flex-1")}>
              <MapPin
                className={cn("size-5 shrink-0", dark ? "text-slate-300" : "text-slate-400")}
                aria-hidden
              />
              <select
                name="area"
                value={zone}
                onChange={(event) => setZone(event.target.value)}
                className={cn(inputClass, "cursor-pointer")}
                aria-label={t("zoneAria")}
              >
                <option value="">{t("allZones")}</option>
                {zones.map((item) => (
                  <option key={item.slug} value={item.slug}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        <button
          type="submit"
          className={cn(
            "shrink-0 rounded-xl px-5 font-semibold transition active:scale-[0.98]",
            compact ? "h-10 text-sm" : "h-12",
            dark
              ? "bg-accent-500 text-brand-900 shadow-[0_4px_18px_rgba(56,239,125,0.35)] ring-1 ring-accent-300/50 hover:bg-accent-400"
              : "bg-brand-600 text-white hover:bg-brand-700",
          )}
        >
          {submitLabel ?? t("submit")}
        </button>
      </div>
    </form>
  );
}
