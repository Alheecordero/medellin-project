import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const djangoOrigin = process.env.DJANGO_API_ORIGIN || "http://127.0.0.1:8000";

/** Hostname del CDN de imágenes (R2). */
function cdnHostname(): string {
  const base = process.env.NEXT_PUBLIC_R2_PUBLIC_BASE_URL || "https://img.vivemedellin.net";
  try {
    return new URL(base).hostname;
  } catch {
    return "img.vivemedellin.net";
  }
}

const nextConfig: NextConfig = {
  // Django sirve todas sus rutas con barra final; el frontend replica ese contrato.
  trailingSlash: true,

  // Evita soft-404 (HTTP 200 con UI de not-found) cuando notFound() salta en generateMetadata.
  htmlLimitedBots: /.*/,

  async headers() {
    const longCache = [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }];
    return [
      { source: "/brand/:path*", headers: longCache },
      { source: "/home/:path*", headers: longCache },
      { source: "/icons/:path*", headers: longCache },
    ];
  },

  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${djangoOrigin}/api/:path*`,
      },
    ];
  },

  images: {
    remotePatterns: [
      { protocol: "https", hostname: cdnHostname() },
      { protocol: "https", hostname: "img.vivemedellin.net" },
      { protocol: "https", hostname: "*.r2.dev" },
      { protocol: "https", hostname: "*.r2.cloudflarestorage.com" },
      { protocol: "https", hostname: "storage.googleapis.com", pathname: "/vivemedellin-bucket/**" },
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
      { protocol: "https", hostname: "*.googleapis.com" },
    ],
  },
};

export default withNextIntl(nextConfig);
