// Canonical public origin for the storefront. Used to build absolute URLs for
// metadata (canonical, Open Graph), the sitemap, and robots.txt. Set
// NEXT_PUBLIC_SITE_URL per environment (e.g. https://ardezan.com in prod).

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"
).replace(/\/$/, "");

export const SITE_NAME = "Ardezan";

export function absoluteUrl(path = "/"): string {
  return `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
