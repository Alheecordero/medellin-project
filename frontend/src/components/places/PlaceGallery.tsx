"use client";

import { useCallback, useEffect, useState } from "react";
import useEmblaCarousel from "embla-carousel-react";
import { ChevronLeft, ChevronRight, Store } from "lucide-react";
import { useTranslations } from "next-intl";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { cn } from "@/lib/cn";
import { pickImage } from "@/lib/images";
import type { PlacePhoto } from "@/lib/types";

export function PlaceGallery({ photos, title }: { photos: PlacePhoto[]; title: string }) {
  const t = useTranslations("placeDetail.gallery");
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: photos.length > 1, align: "start" });
  const [selected, setSelected] = useState(0);

  const onSelect = useCallback(() => {
    if (emblaApi) setSelected(emblaApi.selectedScrollSnap());
  }, [emblaApi]);

  // El índice inicial de embla es 0, igual que el estado, así que basta suscribirse.
  useEffect(() => {
    if (!emblaApi) return;
    emblaApi.on("select", onSelect);
    emblaApi.on("reInit", onSelect);
    return () => {
      emblaApi.off("select", onSelect);
      emblaApi.off("reInit", onSelect);
    };
  }, [emblaApi, onSelect]);

  if (photos.length === 0) {
    return (
      <div className="grid aspect-[16/9] place-items-center rounded-2xl bg-gradient-to-br from-brand-800 via-slate-900 to-slate-950 text-accent-400/50">
        <Store className="size-12" aria-hidden />
      </div>
    );
  }

  return (
    <div className="relative overflow-hidden rounded-2xl bg-slate-900">
      <div ref={emblaRef} className="overflow-hidden">
        <div className="flex">
          {photos.map((photo, index) => (
            <div key={index} className="relative min-w-0 flex-[0_0_100%]">
              <div className="relative aspect-[16/10] sm:aspect-[16/9]">
                <RemoteImage
                  src={pickImage(photo)}
                  alt={photo.alt || title}
                  fill
                  priority={index === 0}
                  sizes="(max-width: 1024px) 100vw, 720px"
                  className="object-cover"
                  fallback={
                    <div className="grid size-full place-items-center bg-slate-900 text-accent-400/50">
                      <Store className="size-12" aria-hidden />
                    </div>
                  }
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {photos.length > 1 && (
        <>
          <button
            type="button"
            onClick={() => emblaApi?.scrollPrev()}
            aria-label={t("prev")}
            className="absolute left-2 top-1/2 grid size-9 -translate-y-1/2 place-items-center rounded-full bg-slate-950/55 text-white ring-1 ring-white/20 backdrop-blur transition hover:bg-slate-950/75"
          >
            <ChevronLeft className="size-5" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => emblaApi?.scrollNext()}
            aria-label={t("next")}
            className="absolute right-2 top-1/2 grid size-9 -translate-y-1/2 place-items-center rounded-full bg-slate-950/55 text-white ring-1 ring-white/20 backdrop-blur transition hover:bg-slate-950/75"
          >
            <ChevronRight className="size-5" aria-hidden />
          </button>

          <p className="absolute right-3 top-3 rounded-full bg-slate-950/60 px-2.5 py-1 text-xs font-semibold text-white ring-1 ring-white/15 backdrop-blur">
            {t("counter", { current: selected + 1, total: photos.length })}
          </p>

          <div className="absolute inset-x-0 bottom-0 flex justify-center gap-1.5 bg-gradient-to-t from-slate-950/70 to-transparent p-3">
            {photos.map((_, index) => (
              <button
                key={index}
                type="button"
                onClick={() => emblaApi?.scrollTo(index)}
                aria-label={t("counter", { current: index + 1, total: photos.length })}
                aria-current={index === selected}
                className={cn(
                  "h-1.5 rounded-full transition-all",
                  index === selected ? "w-6 bg-accent-500" : "w-1.5 bg-white/50 hover:bg-white/80",
                )}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
