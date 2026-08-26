import type { Metadata } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";
import { notFound } from "next/navigation";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { routing, type AppLocale } from "@/i18n/routing";
import { localizedAlternates, localizedUrl, openGraphLocale } from "@/lib/seo";
import { BRAND_FAVICON_SRC, BRAND_ICON_SRC, BRAND_OG_SRC, SITE_NAME, SITE_URL } from "@/lib/site";
import "../globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["700", "800"],
  variable: "--font-jakarta",
  display: "swap",
});

type Props = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const appLocale = locale as AppLocale;
  const t = await getTranslations({ locale, namespace: "metadata" });

  return {
    metadataBase: new URL(SITE_URL),
    title: {
      default: t("siteTitle"),
      template: `%s | ${SITE_NAME}`,
    },
    description: t("siteDescription"),
    applicationName: SITE_NAME,
    icons: {
      icon: [
        { url: BRAND_FAVICON_SRC },
        { url: BRAND_ICON_SRC, type: "image/png", sizes: "512x512" },
      ],
      apple: [{ url: "/brand/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
    },
    alternates: localizedAlternates(appLocale, "/"),
    openGraph: {
      title: t("siteTitle"),
      description: t("siteDescription"),
      type: "website",
      url: localizedUrl(appLocale, "/"),
      siteName: SITE_NAME,
      locale: openGraphLocale(appLocale),
      alternateLocale: [openGraphLocale(appLocale === "es" ? "en" : "es")],
      images: [{ url: BRAND_OG_SRC, width: 1200, height: 630, alt: SITE_NAME }],
    },
    twitter: {
      card: "summary_large_image",
      title: t("siteTitle"),
      description: t("siteDescription"),
      images: [BRAND_OG_SRC],
    },
  };
}

export const viewport = {
  themeColor: "#11998e",
};

export default async function LocaleLayout({ children, params }: Props) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }

  setRequestLocale(locale);

  return (
    <html lang={locale} className={`${inter.variable} ${jakarta.variable}`}>
      <head>
        <link rel="dns-prefetch" href="https://img.vivemedellin.co" />
      </head>
      <body className="flex min-h-screen flex-col">
        <NextIntlClientProvider>
          <SiteHeader />
          <main className="flex-1">{children}</main>
          <SiteFooter />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
