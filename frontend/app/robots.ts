import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/lib/site";

// Public catalog + try-on are crawlable; private/transactional surfaces and
// the API are not. Keeps personal data (orders, fitting room) and the admin
// console out of search indexes.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/admin",
        "/account",
        "/api",
        "/cart",
        "/checkout",
        "/order-confirmation",
        "/auth",
        "/try-on/jobs",
      ],
    },
    sitemap: absoluteUrl("/sitemap.xml"),
  };
}
