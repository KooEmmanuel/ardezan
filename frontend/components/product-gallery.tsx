"use client";

import Image from "next/image";
import { useState } from "react";

/**
 * Storefront PDP thumbnail strip. Self-heals broken images:
 *   - Dedupes URLs to avoid the same hero appearing twice.
 *   - Hides any thumb whose underlying file 404s (orphan media assets
 *     left behind by older seed runs would otherwise render the
 *     browser's broken-image icon).
 */
export function ProductGallery({
  heroUrl,
  urls,
}: {
  heroUrl: string | null;
  urls: string[];
}) {
  const [brokenUrls, setBrokenUrls] = useState<Set<string>>(new Set());

  const filtered = Array.from(
    new Set(
      urls
        .filter((u): u is string => Boolean(u))
        .filter((u) => u !== heroUrl),
    ),
  )
    .filter((u) => !brokenUrls.has(u))
    .slice(0, 4);

  if (filtered.length === 0) return null;

  return (
    <div className="grid grid-cols-4 gap-2">
      {filtered.map((url) => (
        <div className="card-solid overflow-hidden" key={url}>
          <div className="ratio-11 relative">
            <Image
              alt=""
              className="object-cover"
              fill
              onError={() =>
                setBrokenUrls((prev) => {
                  const next = new Set(prev);
                  next.add(url);
                  return next;
                })
              }
              sizes="(max-width: 1024px) 25vw, 12vw"
              src={url}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
