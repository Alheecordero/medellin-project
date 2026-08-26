import type { LucideIcon } from "lucide-react";
import { SearchX } from "lucide-react";
import { cn } from "@/lib/cn";

type Props = {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
};

export function EmptyState({
  icon: Icon = SearchX,
  title,
  description,
  action,
  className,
}: Props) {
  return (
    <div
      className={cn("rounded-2xl border border-slate-200 bg-white px-6 py-14 text-center", className)}
    >
      <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-brand-50 text-brand-300">
        <Icon className="size-7" aria-hidden />
      </span>
      <h2 className="mt-4 text-xl font-bold text-slate-900">{title}</h2>
      {description && <p className="mx-auto mt-2 max-w-md text-slate-500">{description}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}
