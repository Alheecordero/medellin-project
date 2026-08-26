import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Props = HTMLAttributes<HTMLDivElement> & {
  hover?: boolean;
};

export function Card({ hover = false, className, ...props }: Props) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-slate-200 bg-white shadow-[var(--shadow-card)]",
        hover &&
          "transition-all duration-200 hover:-translate-y-1 hover:border-brand-200 hover:shadow-[var(--shadow-card-hover)]",
        className,
      )}
      {...props}
    />
  );
}
