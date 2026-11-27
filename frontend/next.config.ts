import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL || "http://127.0.0.1:8765";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/backend-api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
