"use client";

import { TriangleAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { Container } from "@/components/ui/Container";

export default function LocaleError({ reset }: { error: Error; reset: () => void }) {
  const t = useTranslations("common");

  return (
    <Container className="flex flex-col items-center justify-center py-20 text-center">
      <span className="grid size-20 place-items-center rounded-3xl bg-amber-50 text-amber-600">
        <TriangleAlert className="size-9" aria-hidden />
      </span>
      <h1 className="mt-6 text-2xl font-extrabold text-slate-900">{t("errorTitle")}</h1>
      <p className="mx-auto mt-2 max-w-sm text-slate-500">{t("errorDescription")}</p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 inline-flex items-center rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"
      >
        {t("retry")}
      </button>
    </Container>
  );
}
