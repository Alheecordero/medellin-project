import type { ComponentProps } from "react";
import { ChevronRight } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/cn";

type LinkHref = ComponentProps<typeof Link>["href"];

export type Crumb = { label: string; href?: LinkHref };

export function Breadcrumb({
  items,
  className,
  tone = "light",
  label,
}: {
  items: Crumb[];
  className?: string;
  tone?: "light" | "dark";
  label: string;
}) {
  return (
    <nav aria-label={label} className={className}>
      <ol className="flex flex-wrap items-center gap-1.5 text-sm">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${item.label}-${i}`} className="flex items-center gap-1.5">
              {item.href && !last ? (
                <Link
                  href={item.href}
                  className={cn(
                    "font-medium transition",
                    tone === "dark"
                      ? "text-slate-300 hover:text-white"
                      : "text-brand-700 hover:text-brand-800",
                  )}
                >
                  {item.label}
                </Link>
              ) : (
                <span className={tone === "dark" ? "text-white" : "font-semibold text-slate-600"}>
                  {item.label}
                </span>
              )}
              {!last && (
                <ChevronRight
                  className={cn("size-3.5", tone === "dark" ? "text-slate-500" : "text-brand-300")}
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
