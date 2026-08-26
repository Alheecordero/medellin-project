"use client";

import { useParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing, type AppLocale } from "@/i18n/routing";
import { cn } from "@/lib/cn";

export function LanguageSwitcher({ className }: { className?: string }) {
  const t = useTranslations("language");
  const locale = useLocale() as AppLocale;
  const pathname = usePathname();
  const params = useParams();
  const router = useRouter();

  function switchTo(next: AppLocale) {
    if (next === locale) return;
    // Los pathnames dinámicos necesitan sus params para resolver el slug traducido.
    router.replace(
      // @ts-expect-error -- next-intl no puede inferir params genéricos de useParams
      { pathname, params },
      { locale: next },
    );
  }

  return (
    <div
      className={cn(
        "inline-flex items-center gap-0.5 rounded-lg bg-white/5 p-0.5 ring-1 ring-white/10",
        className,
      )}
      role="group"
    >
      {routing.locales.map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => switchTo(code)}
          aria-pressed={code === locale}
          aria-label={t("switchTo", { label: t(code) })}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-bold uppercase tracking-wide transition",
            code === locale
              ? "bg-brand-600 text-white shadow-sm"
              : "text-slate-400 hover:bg-white/10 hover:text-white",
          )}
        >
          {t(code)}
        </button>
      ))}
    </div>
  );
}
