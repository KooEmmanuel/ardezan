import type { MetadataRoute } from "next";

import { serverApi } from "@/lib/server-api";
import { absoluteUrl } from "@/lib/site";

// Per-request rather than ISR — Googlebot crawls are infrequent and
// hitting the backend live keeps the sitemap from blocking the
// Vercel build when Railway is cold.
export const dynamic = "force-dynamic";

// Static, always-present routes. Try-on is the brand's front door, so it gets
// the highest priority after the home page.
const STATIC_ROUTES: { path: string; priority: number; changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"] }[] = [
  { path: "/", priority: 1.0, changeFrequency: "daily" },
  { path: "/try-on", priority: 0.9, changeFrequency: "weekly" },
  { path: "/catalog", priority: 0.8, changeFrequency: "daily" },
  { path: "/sizing", priority: 0.4, changeFrequency: "monthly" },
  { path: "/returns", priority: 0.4, changeFrequency: "monthly" },
  { path: "/contact", priority: 0.4, changeFrequency: "monthly" },
  { path: "/privacy", priority: 0.3, changeFrequency: "yearly" },
  { path: "/terms", priority: 0.3, changeFrequency: "yearly" },
];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();

  const staticEntries: MetadataRoute.Sitemap = STATIC_ROUTES.map((r) => ({
    url: absoluteUrl(r.path),
    lastModified: now,
    changeFrequency: r.changeFrequency,
    priority: r.priority,
  }));

  // Best-effort product pages. If the catalog API is unavailable at build/
  // revalidate time we still return the static routes rather than failing the
  // whole sitemap.
  let productEntries: MetadataRoute.Sitemap = [];
  try {
    const { items } = await serverApi.listProducts({ limit: 1000 });
    productEntries = items.map((p) => ({
      url: absoluteUrl(`/product/${p.slug}`),
      lastModified: now,
      changeFrequency: "weekly",
      priority: 0.7,
    }));
  } catch {
    // Swallow — partial sitemap is better than none.
  }

  return [...staticEntries, ...productEntries];
}
