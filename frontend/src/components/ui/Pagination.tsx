import type { ComponentProps } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";

type LinkHref = ComponentProps<typeof Link>["href"];

type Props = {
  page: number;
  totalPages: number;
  hasPrev: boolean;
  hasNext: boolean;
  hrefForPage: (page: number) => LinkHref;
};

function pageRange(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);

  const pages: (number | "ellipsis")[] = [1];
  if (current > 3) pages.push("ellipsis");
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) {
    pages.push(p);
  }
  if (current < total - 2) pages.push("ellipsis");
  pages.push(total);
  return pages;
}

const navBtn =
  "inline-flex h-10 min-w-[2.5rem] items-center justify-center gap-1 rounded-full border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 transition hover:border-brand-300 hover:text-brand-700";

export async function Pagination({ page, totalPages, hasPrev, hasNext, hrefForPage }: Props) {
  const t = await getTranslations("pagination");
  if (totalPages <= 1) return null;

  return (
    <nav className="mt-8 flex flex-wrap items-center justify-center gap-2" aria-label={t("aria")}>
      {hasPrev ? (
        <Link href={hrefForPage(page - 1)} className={navBtn}>
          <ChevronLeft className="size-4" aria-hidden />
          <span className="hidden sm:inline">{t("prev")}</span>
        </Link>
      ) : (
        <span className={`${navBtn} pointer-events-none opacity-40`} aria-hidden>
          <ChevronLeft className="size-4" />
          <span className="hidden sm:inline">{t("prev")}</span>
        </span>
      )}

      {pageRange(page, totalPages).map((p, i) =>
        p === "ellipsis" ? (
          <span key={`ellipsis-${i}`} className="px-1 text-sm text-slate-400">
            &hellip;
          </span>
        ) : p === page ? (
          <span
            key={p}
            aria-current="page"
            className="inline-flex h-10 min-w-[2.5rem] items-center justify-center rounded-full bg-brand-600 px-3 text-sm font-bold text-white"
          >
            {p}
          </span>
        ) : (
          <Link key={p} href={hrefForPage(p)} className={navBtn} aria-label={t("goTo", { page: p })}>
            {p}
          </Link>
        ),
      )}

      {hasNext ? (
        <Link href={hrefForPage(page + 1)} className={navBtn}>
          <span className="hidden sm:inline">{t("next")}</span>
          <ChevronRight className="size-4" aria-hidden />
        </Link>
      ) : (
        <span className={`${navBtn} pointer-events-none opacity-40`} aria-hidden>
          <span className="hidden sm:inline">{t("next")}</span>
          <ChevronRight className="size-4" />
        </span>
      )}
    </nav>
  );
}
