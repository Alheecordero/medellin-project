"use client";

import { useState } from "react";
import { Compass, Search, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { SearchForm } from "@/components/search/SearchForm";
import { Container } from "@/components/ui/Container";
import { cn } from "@/lib/cn";
import { SITE_NAME } from "@/lib/site";

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const t = useTranslations("nav");
  const tSearch = useTranslations("search");

  return (
    <header className="sticky top-0 z-[var(--z-header)]">
      <div className="h-0.5 bg-gradient-to-r from-brand-700 via-accent-500 to-brand-700" />

      <div className="border-b border-slate-800/50 bg-slate-900/95 backdrop-blur-md">
        <Container className="flex h-14 items-center gap-2 py-0 sm:h-[3.75rem] sm:gap-3">
          <Link
            href="/"
            className="flex min-w-0 shrink-0 items-center gap-2 font-extrabold tracking-tight text-white transition hover:opacity-90"
            onClick={() => setOpen(false)}
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-brand-600 to-brand-800 text-accent-400 shadow-[var(--shadow-glow-sm)]">
              <Compass className="size-4.5" aria-hidden />
            </span>
            <span className="truncate text-sm sm:text-base">
              Vive<span className="text-accent-400">Medellín</span>
            </span>
            <span className="sr-only">{SITE_NAME}</span>
          </Link>

          <nav className="ml-auto hidden shrink-0 items-center gap-1 md:flex">
            <Link
              href="/lugares"
              className="rounded-full px-3 py-1.5 text-sm font-semibold text-slate-300 transition hover:bg-white/8 hover:text-white"
            >
              {t("places")}
            </Link>
          </nav>

          <SearchForm
            className="hidden w-64 lg:block xl:w-72"
            compact
            dark
            showZone={false}
            placeholder={tSearch("placeholder")}
            submitLabel={tSearch("submit")}
          />

          <LanguageSwitcher className="ml-auto shrink-0 md:ml-0" />

          <button
            type="button"
            className={cn(
              "grid size-9 shrink-0 place-items-center rounded-xl text-slate-300 transition hover:bg-white/8 hover:text-white lg:hidden",
              open && "bg-white/10 text-white",
            )}
            aria-label={open ? t("closeSearch") : t("openSearch")}
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <X className="size-5" /> : <Search className="size-5" />}
          </button>
        </Container>

        {open && (
          <div className="animate-fade-in border-t border-slate-800/50 bg-slate-900 lg:hidden">
            <Container className="pb-4 pt-3">
              <SearchForm
                compact
                dark
                showZone={false}
                placeholder={tSearch("placeholder")}
                submitLabel={tSearch("submitMobile")}
                onNavigate={() => setOpen(false)}
              />
            </Container>
          </div>
        )}
      </div>
    </header>
  );
}
