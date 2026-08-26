import { Compass, MapPin } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Container } from "@/components/ui/Container";

export default async function LocaleNotFound() {
  const t = await getTranslations("common");
  const tPlaces = await getTranslations("places");

  return (
    <Container className="flex flex-col items-center justify-center py-20 text-center">
      <span className="grid size-20 place-items-center rounded-3xl bg-brand-50 text-brand-600">
        <MapPin className="size-9" aria-hidden />
      </span>
      <p className="mt-6 text-5xl font-extrabold tracking-tight text-slate-900">404</p>
      <h1 className="mt-3 text-xl font-semibold text-slate-700">{t("notFoundTitle")}</h1>
      <p className="mx-auto mt-2 max-w-sm text-slate-500">{t("notFoundDescription")}</p>

      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link
          href="/"
          className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700"
        >
          <Compass className="size-4" aria-hidden />
          {t("backHome")}
        </Link>
        <Link
          href="/lugares"
          className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 transition hover:border-brand-300 hover:text-brand-700"
        >
          <MapPin className="size-4" aria-hidden />
          {tPlaces("title")}
        </Link>
      </div>
    </Container>
  );
}
