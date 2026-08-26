"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { canonicalImageUrl } from "@/lib/images";

type Props = {
  src: string | null | undefined;
  alt: string;
  className?: string;
  fill?: boolean;
  width?: number;
  height?: number;
  sizes?: string;
  priority?: boolean;
  fetchPriority?: "high" | "low" | "auto";
  fallback?: React.ReactNode;
  onLoad?: () => void;
};

/**
 * Imagen remota con fallback. Usa <img> nativo en lugar de next/image para no
 * depender de remotePatterns ni del optimizador con un CDN que ya sirve variantes.
 */
export function RemoteImage({
  src,
  alt,
  className,
  fill,
  width,
  height,
  sizes,
  priority,
  fetchPriority,
  fallback = null,
  onLoad,
}: Props) {
  const [failed, setFailed] = useState(false);
  const resolvedSrc = canonicalImageUrl(src);

  if (!resolvedSrc || failed) {
    return fallback;
  }

  const shared = {
    src: resolvedSrc,
    sizes,
    loading: priority ? ("eager" as const) : ("lazy" as const),
    decoding: "async" as const,
    fetchPriority: fetchPriority ?? (priority ? ("high" as const) : ("auto" as const)),
    referrerPolicy: "no-referrer" as const,
    onLoad,
    onError: () => setFailed(true),
  };

  if (fill) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        {...shared}
        alt={alt}
        className={cn("absolute inset-0 h-full w-full object-cover", className)}
      />
    );
  }

  // eslint-disable-next-line @next/next/no-img-element
  return <img {...shared} alt={alt} width={width} height={height} className={cn(className)} />;
}
