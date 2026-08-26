import { Star } from "lucide-react";
import { cn } from "@/lib/cn";
import { formatRating } from "@/lib/format";

type Props = {
  rating: number | null;
  reviewCount?: number | null;
  className?: string;
};

export function Rating({ rating, reviewCount, className }: Props) {
  const value = formatRating(rating);
  if (!value) return null;

  return (
    <span
      className={cn("inline-flex items-center gap-1 text-sm font-semibold text-slate-800", className)}
    >
      <Star className="size-4 fill-amber-400 text-amber-400" aria-hidden />
      {value}
      {reviewCount ? <span className="font-normal text-slate-400">({reviewCount})</span> : null}
    </span>
  );
}
