import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type ButtonVariant = "brand" | "accent" | "outline" | "ghost" | "dark" | "subtle";
export type ButtonSize = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-full font-semibold whitespace-nowrap transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 disabled:opacity-60 disabled:pointer-events-none";

const variants: Record<ButtonVariant, string> = {
  brand: "bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:scale-[0.98]",
  // El acento #38ef7d exige texto oscuro para ser legible.
  accent: "bg-accent-500 text-brand-900 shadow-sm hover:bg-accent-400 active:scale-[0.98]",
  outline: "border border-slate-300 bg-white text-slate-800 hover:border-brand-400 hover:text-brand-700",
  ghost: "text-slate-700 hover:bg-slate-100",
  dark: "bg-slate-900 text-white hover:bg-slate-800 active:scale-[0.98]",
  subtle: "bg-brand-50 text-brand-700 hover:bg-brand-100",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-9 px-4 text-sm",
  md: "h-11 px-5 text-sm",
  lg: "h-14 px-7 text-base",
};

export function buttonClasses({
  variant = "brand",
  size = "md",
  className,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
} = {}) {
  return cn(base, variants[variant], sizes[size], className);
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

export function Button({ variant, size, className, ...props }: Props) {
  return <button className={buttonClasses({ variant, size, className })} {...props} />;
}
