import type { NextConfig } from "next";

const djangoOrigin = process.env.DJANGO_API_ORIGIN || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "img.vivemedellin.co",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "storage.googleapis.com",
        pathname: "/vivemedellin-bucket/**",
      },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${djangoOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
