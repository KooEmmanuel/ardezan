// Server component — data is fetched at render time on the server. The HTML
// the browser receives already contains real product tiles + signed image
// URLs, so there's no client-side fetch waterfall. ISR (60s) keeps the
// rendered HTML warm across visitors.

import Link from "next/link";
import Image from "next/image";

import { HomeHero } from "@/components/home-hero";
import { TryOnButton } from "@/components/try-on-button";
import { formatMoney } from "@/lib/api";
import { serverApi } from "@/lib/server-api";
import type {
  ProductListItem,
  SiteMediaResponse,
  SiteMediaSlot,
} from "@/lib/types";

// Rendered per request, not at build time. ISR (revalidate=60) would
// pre-fetch from the API during ``next build`` and fail the Vercel
// build whenever the backend is cold, slow, or unreachable. Per-request
// rendering is fast enough — SSR over a warm backend is sub-200ms —
// and survives backend hiccups during deploys.
export const dynamic = "force-dynamic";

// Picsum fallbacks for slots the admin hasn't generated yet.
const PICSUM_FALLBACK: Record<SiteMediaSlot, string> = {
  hero_look_01:         "https://picsum.photos/seed/atelier-look-01/600/750?grayscale",
  hero_look_02:         "https://picsum.photos/seed/atelier-look-02/600/750?grayscale",
  hero_look_03:         "https://picsum.photos/seed/atelier-look-03/600/750?grayscale",
  hero_look_04:         "https://picsum.photos/seed/atelier-look-04/600/750?grayscale",
  hero_look_05:         "https://picsum.photos/seed/atelier-look-05/600/750?grayscale",
  hero_look_06:         "https://picsum.photos/seed/atelier-look-06/600/750?grayscale",
  hero_mobile:          "https://picsum.photos/seed/atelier-look-mobile/720/480?grayscale",
  category_women:       "https://picsum.photos/seed/cat-women/720/480?grayscale",
  category_men:         "https://picsum.photos/seed/cat-men/720/480?grayscale",
  category_new:         "https://picsum.photos/seed/cat-new/720/480?grayscale",
  category_accessories: "https://picsum.photos/seed/cat-acc/720/480?grayscale",
  editorial_no_01:      "https://picsum.photos/seed/atelier-editorial/720/900?grayscale",
};

const CATEGORY_TILES: { label: string; href: string; slot: SiteMediaSlot }[] = [
  { label: "Women",       href: "/catalog?cat=women",       slot: "category_women" },
  { label: "Men",         href: "/catalog?cat=men",         slot: "category_men" },
  { label: "New",         href: "/catalog?cat=new",         slot: "category_new" },
  { label: "Accessories", href: "/catalog?cat=accessories", slot: "category_accessories" },
];

export default async function HomePage() {
  // Parallel fetches on the server — both finished before HTML is generated.
  const [productsResponse, siteMediaResponse] = await Promise.allSettled([
    serverApi.listProducts({ limit: 12 }),
    serverApi.getSiteMedia(),
  ]);

  const products: ProductListItem[] =
    productsResponse.status === "fulfilled" ? productsResponse.value.items : [];
  const siteMedia: SiteMediaResponse["slots"] =
    siteMediaResponse.status === "fulfilled"
      ? siteMediaResponse.value.slots
      : ({} as SiteMediaResponse["slots"]);

  const slotUrl = (slot: SiteMediaSlot): string =>
    siteMedia[slot] ?? PICSUM_FALLBACK[slot];

  const newThisWeek = products.slice(0, 4);
  const bestSellers = products.slice(4, 8);

  return (
    <>
      {/* Hero is interactive (form + cycling cascade) → client island */}
      <HomeHero
        initialSiteMedia={
          { ...PICSUM_FALLBACK, ...siteMedia } as Record<SiteMediaSlot, string | null>
        }
        picsumFallback={PICSUM_FALLBACK}
      />

      {/* ─── Shop by category ─── */}
      <section className="max-w-[1280px] mx-auto px-5 pt-14 pb-6">
        <div className="flex items-end justify-between gap-3 mb-5">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
              Or browse traditionally
            </div>
            <h2 className="font-display text-3xl sm:text-4xl">Shop by category</h2>
          </div>
          <Link
            className="text-sm text-[color:var(--ink-soft)] underline underline-offset-4 hidden sm:inline"
            href="/catalog"
          >
            See all →
          </Link>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {CATEGORY_TILES.map((tile) => (
            <Link
              className="card-solid overflow-hidden product-card"
              href={tile.href}
              key={tile.label}
            >
              <div className="ratio-32 relative overflow-hidden">
                <Image
                  alt={tile.label}
                  className="object-cover"
                  fill
                  sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
                  src={slotUrl(tile.slot)}
                />
                <div className="absolute inset-x-0 bottom-0 p-3 bg-gradient-to-t from-black/55 to-transparent text-white z-10">
                  <div className="font-display text-xl">{tile.label}</div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* ─── New this week ─── */}
      <ProductRow eyebrow="Spring · Summer" products={newThisWeek} title="New this week" />

      {/* ─── Editorial ─── */}
      <section className="bg-[color:var(--ivory)]">
        <div className="max-w-[1280px] mx-auto px-5 py-14 sm:py-20">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-14 items-center">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ink-soft)] mb-2">
                Story · No. 01
              </div>
              <h2 className="font-display text-4xl sm:text-5xl leading-[1.05] mb-4">
                A single photo,<br />a season of outfits.
              </h2>
              <p className="text-[color:var(--muted)] leading-relaxed mb-3">
                You spend twenty minutes in a fitting room to know if one pair of trousers will work.
                We turn a single photo into ten complete looks, drawn on your shape — drape, length,
                palette, and proportion.
              </p>
              <p className="text-[color:var(--muted)] leading-relaxed mb-5">
                The pieces are real. The fit is yours. The catalog only shows up if you want it.
              </p>
              <div className="grid grid-cols-1 sm:flex gap-2">
                <Link className="btn-primary" href="/try-on">Try it now</Link>
                <Link className="btn-secondary" href="/catalog">Or browse the catalog</Link>
              </div>
            </div>
            <div className="relative">
              <div className="card-solid overflow-hidden">
                <div className="ratio-45 relative">
                  <Image
                    alt=""
                    className="object-cover"
                    fill
                    sizes="(max-width: 1024px) 100vw, 50vw"
                    src={slotUrl("editorial_no_01")}
                  />
                </div>
              </div>
              <div className="absolute -bottom-4 left-4 sm:left-8 bg-white px-4 py-2.5 rounded-lg border border-[color:var(--line)] shadow-sm">
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
                  In ten looks
                </div>
                <div className="font-display text-base leading-tight">
                  Twilight Drape · Forest Tailor · Studio Day · +7
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Best sellers ─── */}
      <ProductRow eyebrow="Most styled" products={bestSellers} title="Pieces our customers chose" />
    </>
  );
}

// ─── Server-rendered product row ───────────────────────────────────
function ProductRow({
  title,
  eyebrow,
  products,
}: {
  title: string;
  eyebrow: string;
  products: ProductListItem[];
}) {
  return (
    <section className="max-w-[1280px] mx-auto px-5 py-12">
      <div className="flex items-end justify-between gap-3 mb-5">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
            {eyebrow}
          </div>
          <h2 className="font-display text-3xl sm:text-4xl">{title}</h2>
        </div>
        <Link
          className="text-sm text-[color:var(--ink-soft)] underline underline-offset-4 hidden sm:inline"
          href="/catalog"
        >
          View all →
        </Link>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {products.length === 0
          ? Array.from({ length: 4 }).map((_, i) => (
              <div className="card-solid overflow-hidden" key={i}>
                <div className="ratio-45 shimmer" />
                <div className="p-3">
                  <div className="h-3 w-2/3 bg-[color:var(--ivory)] rounded mb-2" />
                  <div className="h-3 w-1/3 bg-[color:var(--ivory)] rounded" />
                </div>
              </div>
            ))
          : products.map((p) => <ProductTile key={p.product_id} product={p} />)}
      </div>
    </section>
  );
}

function ProductTile({ product }: { product: ProductListItem }) {
  const price = product.pricing.base_price_amount ?? product.pricing.price_amount;
  const imageSrc =
    product.primary_image_url ??
    `https://picsum.photos/seed/${product.slug}/480/600?grayscale`;
  return (
    <Link className="card-solid overflow-hidden product-card block" href={`/product/${product.slug}`}>
      <div className="ratio-45 relative overflow-hidden">
        <Image
          alt={product.title}
          className="object-cover"
          fill
          sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
          src={imageSrc}
        />
        {product.try_on_eligible ? (
          <>
            <span className="absolute top-2 left-2 pill pill-outline z-10">AI ready</span>
            <TryOnButton
              productId={product.product_id}
              productSlug={product.slug}
              variant="icon"
            />
          </>
        ) : null}
      </div>
      <div className="p-3">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
          {product.category}
        </div>
        <div className="flex items-center justify-between gap-2 mt-1">
          <div className="font-display text-lg leading-tight truncate min-w-0">{product.title}</div>
          <div className="text-sm shrink-0">{formatMoney(price, product.pricing.currency)}</div>
        </div>
      </div>
    </Link>
  );
}
