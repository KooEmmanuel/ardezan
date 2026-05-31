import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ProductBuyPanel } from "@/components/product-buy-panel";
import { ProductGallery } from "@/components/product-gallery";
import { serverApi } from "@/lib/server-api";
import type { ProductDetail } from "@/lib/types";

// Per-request rendering — see app/page.tsx for the rationale.
export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  let product: ProductDetail;
  try {
    product = await serverApi.getProduct(slug);
  } catch {
    return { title: "Product not found", robots: { index: false, follow: false } };
  }

  const description =
    product.description?.slice(0, 200) ??
    `Shop ${product.title} in ${product.category}. See it on you with AI try-on.`;
  const image = product.primary_image_url ?? product.media_urls?.[0];
  const canonical = `/product/${product.slug}`;

  return {
    title: product.title,
    description,
    alternates: { canonical },
    openGraph: {
      type: "website",
      title: product.title,
      description,
      url: canonical,
      images: image ? [{ url: image, alt: product.title }] : undefined,
    },
    twitter: {
      card: image ? "summary_large_image" : "summary",
      title: product.title,
      description,
      images: image ? [image] : undefined,
    },
  };
}

export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let product: ProductDetail;
  try {
    product = await serverApi.getProduct(slug);
  } catch {
    notFound();
  }

  const heroImage =
    product.primary_image_url ?? product.media_urls?.[0] ?? null;
  const galleryImages = (product.media_urls ?? []).filter(
    (u) => u !== heroImage,
  );

  return (
    <section className="max-w-[1280px] mx-auto px-5 py-10">
      <div className="mb-6">
        <Link className="btn-ghost underline underline-offset-4 text-sm" href="/catalog">
          ← Back to catalog
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 items-start">
        <div className="space-y-3">
          <div className="card-solid overflow-hidden">
            <div className="ratio-45 relative">
              {heroImage ? (
                <Image
                  alt={product.title}
                  className="object-cover"
                  fill
                  priority
                  sizes="(max-width: 1024px) 100vw, 50vw"
                  src={heroImage}
                />
              ) : (
                <span className="absolute inset-0 flex items-center justify-center text-[color:var(--muted)]">
                  {product.category}
                </span>
              )}
            </div>
          </div>

          <ProductGallery heroUrl={heroImage} urls={galleryImages} />
        </div>

        <div className="lg:sticky lg:top-24">
          <ProductBuyPanel product={product} />
        </div>
      </div>
    </section>
  );
}
