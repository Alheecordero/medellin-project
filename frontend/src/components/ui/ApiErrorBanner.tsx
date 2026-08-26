import { getTranslations } from "next-intl/server";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/cn";

export async function ApiErrorBanner({ className }: { className?: string }) {
  const t = await getTranslations("apiError");

  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-left text-sm text-amber-950",
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
      <div>
        <p className="font-semibold">{t("title")}</p>
        <p className="mt-1 text-amber-900/80">{t("description")}</p>
      </div>
    </div>
  );
}
