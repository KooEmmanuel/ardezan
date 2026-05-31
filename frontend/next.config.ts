import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

// Origin of the backend API (same value the browser uses for fetches). The
// CSP must allow connecting to it and loading images served from it.
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Content-Security-Policy.
//
// Pragmatic, allow-listed policy rather than a strict nonce-based one — Next's
// inline bootstrap + Tailwind's injected styles need 'unsafe-inline', and a
// nonce pipeline (middleware-injected per request) is a Phase 2 hardening item.
// Stripe's Payment Element needs js.stripe.com (script + frame),
// api.stripe.com / m.stripe.network (connect), and *.stripe.com (img). Image
// origins mirror next.config `images.remotePatterns`.
const csp = [
  `default-src 'self'`,
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""} https://js.stripe.com`,
  `style-src 'self' 'unsafe-inline'`,
  `img-src 'self' data: blob: ${apiBase} https://*.backblazeb2.com https://*.stripe.com https://picsum.photos`,
  `font-src 'self' data:`,
  `connect-src 'self' ${apiBase} https://api.stripe.com https://m.stripe.network${isDev ? " ws: http://localhost:*" : ""}`,
  `frame-src https://js.stripe.com https://hooks.stripe.com https://m.stripe.network`,
  `frame-ancestors 'none'`,
  `base-uri 'self'`,
  `form-action 'self'`,
  `object-src 'none'`,
]
  .map((directive) => directive.replace(/\s+/g, " ").trim())
  .join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
  // HSTS only matters over HTTPS; emit it in production builds where the site
  // is served over TLS. On localhost http the browser ignores it anyway.
  ...(isDev
    ? []
    : [
        {
          key: "Strict-Transport-Security",
          value: "max-age=63072000; includeSubDomains; preload",
        },
      ]),
];

const nextConfig: NextConfig = {
  reactStrictMode: true,

  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },

  images: {
    // Disable the next/image optimizer when running against local storage
    // (the dev default). Two reasons:
    //   1. The optimizer refuses URLs that resolve to private/loopback IPs
    //      as a security default in recent Next versions — our local-storage
    //      URLs all point at 127.0.0.1:8000, so it would reject every
    //      product image with "resolved to private ip".
    //   2. The original local files are already on disk near full resolution
    //      and don't need AVIF/WebP transcoding during dev.
    //
    // Set NEXT_PUBLIC_STORAGE_BACKEND=b2 in the frontend env to enable
    // optimization when deploying against a CDN-backed bucket.
    unoptimized: (process.env.NEXT_PUBLIC_STORAGE_BACKEND ?? "local") === "local",

    // Backblaze B2 serves catalog + site images at f005.backblazeb2.com.
    // Allowlisted so the optimizer can transcode B2-hosted PNGs to AVIF/WebP
    // when the backend is set to b2.
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.backblazeb2.com",
        pathname: "/file/**",
      },
      // Local storage backend serves files via the API at /api/v1/storage/*.
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
        pathname: "/api/v1/storage/**",
      },
      // Picsum placeholders for unseeded site-media slots.
      {
        protocol: "https",
        hostname: "picsum.photos",
      },
    ],

    // AVIF + WebP for the B2 case — cuts payload by 60–80% vs PNG originals.
    formats: ["image/avif", "image/webp"],

    // Cache optimized variants on disk for 7 days. Matches our signed URL
    // refresh cadence (URLs are stable for 12h+ thanks to backend caching).
    minimumCacheTTL: 60 * 60 * 24 * 7,
  },
};

export default nextConfig;
