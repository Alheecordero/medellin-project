import { Compass } from "lucide-react";
import { getLocale, getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Container } from "@/components/ui/Container";
import type { AppLocale } from "@/i18n/routing";
import { djangoPageUrl, FOOTER_ZONES, SITE_NAME } from "@/lib/site";

export async function SiteFooter() {
  const t = await getTranslations("footer");
  const locale = (await getLocale()) as AppLocale;
  const year = new Date().getFullYear();

  const externalLinks = [
    { href: djangoPageUrl("about", locale), label: t("about") },
    { href: djangoPageUrl("contact", locale), label: t("contact") },
    { href: djangoPageUrl("privacy", locale), label: t("privacy") },
    { href: djangoPageUrl("terms", locale), label: t("terms") },
  ];

  return (
    <footer className="mt-10 border-t border-accent-500/30 bg-slate-950 text-slate-400">
      <Container className="py-6 sm:py-8">
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <Link
                href="/"
                className="inline-flex shrink-0 items-center gap-2 font-extrabold text-white transition hover:opacity-90"
              >
                <span className="grid size-8 place-items-center rounded-xl bg-gradient-to-br from-brand-600 to-brand-800 text-accent-400">
                  <Compass className="size-4.5" aria-hidden />
                </span>
                <span className="text-base">
                  Vive<span className="text-accent-400">Medellín</span>
                </span>
                <span className="sr-only">{SITE_NAME}</span>
              </Link>
              <p className="mt-2 max-w-sm text-xs leading-relaxed sm:text-sm">{t("tagline")}</p>
            </div>

            <nav className="flex flex-wrap gap-x-4 gap-y-1 text-xs sm:justify-end sm:text-sm">
              <Link href="/lugares" className="transition hover:text-accent-400">
                {t("explore")}
              </Link>
              {externalLinks.map((link) => (
                <a key={link.href} href={link.href} className="transition hover:text-accent-400">
                  {link.label}
                </a>
              ))}
            </nav>
          </div>

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <span className="font-semibold text-slate-300">{t("zones")}</span>
            {FOOTER_ZONES.map((zone, index) => (
              <span key={zone.slug} className="inline-flex items-center">
                {index > 0 && <span className="mr-2 text-slate-700">&middot;</span>}
                <Link
                  href={{ pathname: "/lugares", query: { area: zone.slug } }}
                  className="transition hover:text-accent-400"
                >
                  {zone.name}
                </Link>
              </span>
            ))}
          </div>

          <div className="flex flex-col gap-1 border-t border-white/5 pt-4 text-[11px] leading-snug text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
            <p>{t("rights", { year })}</p>
            <p className="sm:text-right">{t("dataSource")}</p>
          </div>
        </div>
      </Container>
    </footer>
  );
}
