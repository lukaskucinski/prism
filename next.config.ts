import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: false,
  experimental: {
    optimizePackageImports: ["lucide-react", "@radix-ui/react-icons"],
  },
  async headers() {
    return [
      {
        source: "/api/tiles/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400" },
          { key: "Access-Control-Allow-Origin", value: "*" },
        ],
      },
      {
        source: "/api/hex/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=60, s-maxage=300" },
        ],
      },
    ];
  },
};

export default nextConfig;
