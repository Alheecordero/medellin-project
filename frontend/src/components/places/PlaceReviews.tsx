import { Quote, Star } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { formatRating } from "@/lib/format";
import type { PlaceReview } from "@/lib/types";

function reviewText(review: PlaceReview): string {
  if (typeof review.text === "string") return review.text;
  return review.text?.text ?? "";
}

function reviewAuthor(review: PlaceReview): string {
  return review.author_name || review.authorAttribution?.displayName || "";
}

function reviewDate(review: PlaceReview): string {
  return review.relative_time_description || review.relativePublishTimeDescription || "";
}

export async function PlaceReviews({ reviews }: { reviews: PlaceReview[] }) {
  const usable = reviews.filter((review) => reviewText(review).trim().length > 0);
  if (usable.length === 0) return null;

  const t = await getTranslations("placeDetail");

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[var(--shadow-card)] sm:p-5">
      <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
        <Quote className="size-4 text-brand-600" aria-hidden />
        {t("reviewsTitle")}
      </h2>

      <ul className="mt-3 space-y-3">
        {usable.map((review, index) => {
          const rating = formatRating(review.rating ?? null);
          const author = reviewAuthor(review);
          const date = reviewDate(review);

          return (
            <li key={index} className="rounded-xl border border-slate-100 bg-slate-50/70 p-3.5">
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-sm font-bold text-slate-900">{author}</p>
                {rating && (
                  <span className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-slate-800">
                    <Star className="size-3.5 fill-amber-400 text-amber-400" aria-hidden />
                    {rating}
                  </span>
                )}
              </div>
              {date && <p className="mt-0.5 text-xs text-slate-400">{date}</p>}
              <p className="mt-2 line-clamp-5 text-sm leading-relaxed text-slate-600">
                {reviewText(review)}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
