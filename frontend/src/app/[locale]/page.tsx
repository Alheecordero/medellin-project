import { getTranslations, setRequestLocale } from "next-intl/server";
import { HomeSectionsWithSuspense } from "@/components/home/HomeSections";
import { Container } from "@/components/ui/Container";
import type { AppLocale } from "@/i18n/routing";
import { HERO_IMAGE_SRC, HERO_IMAGE_SRCSET } from "@/lib/site";

export const revalidate = 600;

type Props = {
  params: Promise<{ locale: string }>;
};

export default async function HomePage({ params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("home");

  return (
    <>
      <section className="relative min-h-[20rem] overflow-hidden text-white sm:min-h-[22rem] lg:min-h-[26rem]">
        {/* Variantes estáticas pregeneradas: /_next/image no se cachea y penaliza el LCP. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={HERO_IMAGE_SRC}
          srcSet={HERO_IMAGE_SRCSET}
          sizes="100vw"
          alt=""
          fetchPriority="high"
          decoding="async"
          className="hero-mesh absolute inset-0 h-full w-full object-cover object-center"
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/20 via-transparent to-brand-900/65" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-[var(--color-surface)] to-transparent sm:h-20" />

        <Container className="relative flex min-h-[inherit] items-start justify-center px-4 pb-8 pt-8 sm:pt-10 lg:pt-11">
          <div className="animate-fade-up mx-auto w-full max-w-2xl text-center motion-safe:[text-shadow:0_1px_3px_rgba(0,0,0,0.4)]">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/90 sm:text-xs">
              {t("badge")}
            </p>
            <h1 className="mt-1.5 text-3xl font-extrabold leading-[1.12] sm:text-4xl lg:text-[2.5rem]">
              {t("title")}
            </h1>
          </div>
        </Container>
      </section>

      <HomeSectionsWithSuspense locale={locale as AppLocale} />
    </>
  );
}
