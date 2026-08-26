/**
 * La API ya devuelve las fotos resueltas contra el CDN (explorer/utils/media_urls.py),
 * pero algunas filas legacy pueden seguir apuntando al bucket de GCS.
 */
const GCS_MARKER = "googleapis.com/vivemedellin-bucket/";

const CDN_BASE = (
  process.env.NEXT_PUBLIC_R2_PUBLIC_BASE_URL || "https://img.vivemedellin.co"
).replace(/\/$/, "");

export function canonicalImageUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim();
  if (!trimmed) return null;

  const markerAt = trimmed.indexOf(GCS_MARKER);
  if (markerAt !== -1) {
    return `${CDN_BASE}/${trimmed.slice(markerAt + GCS_MARKER.length)}`;
  }

  return trimmed;
}

/**
 * Elige la mejor variante disponible. La API expone `imagen` (según el tamaño
 * pedido) e `imagen_full` (original).
 */
export function pickImage(
  source: { imagen?: string | null; imagen_full?: string | null } | null | undefined,
): string | null {
  if (!source) return null;
  return canonicalImageUrl(source.imagen) || canonicalImageUrl(source.imagen_full);
}
