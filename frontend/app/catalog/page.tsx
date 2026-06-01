// Server-rendered catalog grid. Reads ?cat=<category> from the URL and
// fetches the matching products + the live category list from the backend.

import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { TryOnButton } from "@/components/try-on-button";
import { formatMoney } from "@/lib/api";
import {
  DESIGN_INSPIRATIONS,
  FABRIC_GRADIENTS,
  INSPIRATION_IMAGES,
} from "@/lib/design-inspirations";
import { serverApi } from "@/lib/server-api";
import type { ProductListItem } from "@/lib/types";

// Per-request rendering — see app/page.tsx for the rationale.
export const dynamic = "force-dynamic";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}): Promise<Metadata> {
  const { cat, q } = await searchParams;
  if (q) {
    // Search result pages shouldn't be indexed (thin/duplicate content).
    return {
      title: `Results for “${q}”`,
      robots: { index: false, follow: true },
    };
  }
  const label = cat ? CATEGORY_LABEL_OVERRIDES[cat.toLowerCase()] ?? cat : null;
  const title = label ? `${label} — The Catalog` : "The Catalog";
  return {
    title,
    description: label
      ? `Browse ${label} at Ardezan and see each piece on you with AI try-on.`
      : "Browse the full Ardezan catalog and see each piece on you with AI try-on.",
    alternates: { canonical: cat ? `/catalog?cat=${cat}` : "/catalog" },
  };
}

const CATEGORY_LABEL_OVERRIDES: Record<string, string> = {
  women: "Women",
  men: "Men",
  new: "New arrivals",
  bottoms: "Bottoms",
  tops: "Tops",
  outerwear: "Outerwear",
  accessories: "Accessories",
  dresses: "Dresses",
  skirts: "Skirts",
  trousers: "Trousers",
  bespoke: "Bespoke",
};

// Chip "active" check is case-insensitive so `cat=tops` lights up the
// Tops chip even though the live category list has it as "Tops".
function isActiveCat(active: string, candidate: string): boolean {
  return active.toLowerCase() === candidate.toLowerCase();
}

type SearchParams = { cat?: string; q?: string };

export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const { cat, q } = await searchParams;

  // The Bespoke category is curated client-side from the design
  // inspirations — it doesn't go to the backend. Render its own
  // showcase instead of the standard product grid.
  const isBespoke = (cat ?? "").toLowerCase() === "bespoke";

  const [categoriesResp, productsResp] = await Promise.allSettled([
    serverApi.listCategories(),
    // Skip the product fetch when the customer asked for Bespoke —
    // there are no catalog products to return.
    isBespoke
      ? Promise.resolve({ items: [] as ProductListItem[] })
      : serverApi.listProducts({ category: cat, q, limit: 60 }),
  ]);

  const categories: string[] =
    categoriesResp.status === "fulfilled" ? categoriesResp.value.categories : [];
  const products: ProductListItem[] =
    productsResp.status === "fulfilled" ? productsResp.value.items : [];

  const activeCat = cat ?? "";

  return (
    <section className="max-w-[1280px] mx-auto px-5 py-10">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
            Spring · Summer
          </div>
          <h1 className="font-display text-4xl">
            {q
              ? `Results for “${q}”`
              : isBespoke
                ? "Bespoke"
                : "The Catalog"}
          </h1>
          {isBespoke ? (
            <p className="text-[color:var(--muted)] text-sm mt-1 max-w-xl">
              Made-to-order pieces, cut from a curated fabric library.
              Pick a starting point and we&apos;ll render it on you in seconds.
            </p>
          ) : null}
        </div>
        <Link className="btn-ghost underline underline-offset-4" href="/">
          ← Back to Try-On
        </Link>
      </div>

      <div className="flex gap-2 mb-6 text-sm overflow-x-auto pb-2 scrollbar-thin">
        <CategoryChip active={!activeCat} href="/catalog">
          All
        </CategoryChip>
        <CategoryChip
          active={isActiveCat(activeCat, "women")}
          href="/catalog?cat=women"
        >
          Women
        </CategoryChip>
        <CategoryChip
          active={isActiveCat(activeCat, "men")}
          href="/catalog?cat=men"
        >
          Men
        </CategoryChip>
        <CategoryChip
          active={isActiveCat(activeCat, "new")}
          href="/catalog?cat=new"
        >
          New arrivals
        </CategoryChip>
        <CategoryChip
          active={isActiveCat(activeCat, "bespoke")}
          href="/catalog?cat=bespoke"
        >
          Bespoke
        </CategoryChip>
        {categories.map((c) => (
          <CategoryChip
            active={isActiveCat(activeCat, c)}
            href={`/catalog?cat=${encodeURIComponent(c.toLowerCase())}`}
            key={c}
          >
            {CATEGORY_LABEL_OVERRIDES[c.toLowerCase()] ?? c}
          </CategoryChip>
        ))}
      </div>

      {isBespoke ? (
        <BespokeShowcase />
      ) : products.length === 0 ? (
        <div className="card-solid p-10 text-center">
          <div className="font-display text-2xl mb-2">Nothing here yet.</div>
          <p className="text-[color:var(--muted)]">
            Try a different category or search.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
          {products.map((p) => (
            <CatalogTile key={p.product_id} product={p} />
          ))}
        </div>
      )}
    </section>
  );
}

function CategoryChip({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      className="btn-secondary whitespace-nowrap"
      href={href}
      style={
        active
          ? { background: "var(--ink)", color: "var(--paper)", borderColor: "var(--ink)" }
          : undefined
      }
    >
      {children}
    </Link>
  );
}

function CatalogTile({ product }: { product: ProductListItem }) {
  const price = product.pricing.base_price_amount ?? product.pricing.price_amount;
  const compareAt = product.pricing.compare_at_price_amount;
  const onSale =
    typeof compareAt === "number" && typeof price === "number" && compareAt > price;
  return (
    <Link
      className="card-solid overflow-hidden product-card block"
      href={`/product/${product.slug}`}
    >
      <div className="ratio-45 relative overflow-hidden">
        {product.primary_image_url ? (
          <Image
            alt={product.title}
            className="object-cover"
            fill
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
            src={product.primary_image_url}
          />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center text-[color:var(--muted)] text-xs">
            {product.category}
          </span>
        )}
        {onSale ? (
          <span className="absolute top-2 right-2 pill pill-sale">Sale</span>
        ) : null}
        {product.try_on_eligible ? (
          <>
            <span className="absolute top-2 left-2 pill pill-outline">AI ready</span>
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
          <div className="text-sm flex items-baseline gap-1.5 shrink-0">
            {onSale ? (
              <span className="text-[color:var(--muted)] line-through text-xs">
                {formatMoney(compareAt, product.pricing.currency)}
              </span>
            ) : null}
            <span>{formatMoney(price, product.pricing.currency)}</span>
          </div>
        </div>
      </div>
    </Link>
  );
}

// ── Bespoke ─────────────────────────────────────────────────────────
// Curated made-to-order showcase. Each tile deep-links into the
// Design Me flow with the form pre-filled (?inspiration=<id>).
function BespokeShowcase() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {DESIGN_INSPIRATIONS.map((ins) => {
        const fab = FABRIC_GRADIENTS[ins.fabric_id];
        const gradient = ins.gradient ?? fab?.gradient;
        const fabricName = fab?.name ?? "";
        const heroUrl = INSPIRATION_IMAGES[ins.id];
        return (
          <Link
            className="card-solid overflow-hidden block product-card"
            href={`/try-on/design?inspiration=${encodeURIComponent(ins.id)}`}
            key={ins.id}
          >
            <div
              className="ratio-45 relative overflow-hidden"
              style={{ background: gradient ?? "var(--ivory)" }}
            >
              {heroUrl ? (
                // ``unoptimized`` skips Vercel's image optimizer for
                // these static, pre-sized PNGs. On mobile srcset, the
                // optimizer was throttling and the tiles fell back to
                // their gradient backdrop.
                <Image
                  alt={ins.title}
                  className="object-cover"
                  fill
                  sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                  src={heroUrl}
                  unoptimized
                />
              ) : null}
              <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-transparent" />
              <span className="absolute top-2 left-2 pill pill-outline bg-white/85">
                Bespoke
              </span>
              <div className="absolute bottom-3 left-3 right-3 text-white">
                <div className="text-[10px] uppercase tracking-[0.14em] opacity-80">
                  {fabricName}
                </div>
                <div className="font-display text-xl leading-tight">
                  {ins.title}
                </div>
              </div>
            </div>
            <div className="p-3">
              <div className="text-[12px] leading-snug text-[color:var(--ink-soft)]">
                {ins.tagline}
              </div>
              <div className="flex items-center justify-between mt-2 text-[11px] text-[color:var(--muted)]">
                <span className="capitalize">
                  {ins.piece_type} · {ins.complexity}
                </span>
                <span className="underline underline-offset-2">
                  Design this →
                </span>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
