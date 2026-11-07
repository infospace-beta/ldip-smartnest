import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() {
    const production = process.env.NODE_ENV === "production";
    const origins = [process.env.NEXT_PUBLIC_API_URL, process.env.NEXT_PUBLIC_SUPABASE_URL]
      .filter(Boolean).map((value) => new URL(value!).origin);
    const policy = [
      "default-src 'self'", "base-uri 'self'", "object-src 'none'", "frame-ancestors 'none'",
      "form-action 'self'", "img-src 'self' data: blob: https:",
      "font-src 'self' data: https://fonts.gstatic.com",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      // Next's prerendered bootstrap uses inline scripts. Avoid unsafe-eval in production.
      `script-src 'self' 'unsafe-inline'${production ? "" : " 'unsafe-eval'"}`,
      `connect-src 'self' ${origins.join(" ")}${production ? "" : " http://localhost:8000 http://127.0.0.1:8000 ws://localhost:* ws://127.0.0.1:*"}`,
      ...(production ? ["upgrade-insecure-requests"] : []),
    ].join("; ");
    return [{ source: "/(.*)", headers: [
      { key: "Content-Security-Policy", value: policy },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      ...(production ? [{ key: "Strict-Transport-Security", value: "max-age=31536000" }] : []),
    ] }];
  },
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    root: process.cwd(),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
