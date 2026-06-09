"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useToast } from "@/components/toast";
import { api, formatMoney } from "@/lib/api";
import { readCart, removeCartLine, updateCartQuantity, writeCart } from "@/lib/cart";
import type { CartLineInput, CartLineState, RevalidateResponse, ResultCard } from "@/lib/types";

const ESTIMATED_SHIPPING_CENTS = 800;
const CATALOG_BUCKET = "__catalog";
const CHECKOUT_FILTER_KEY = "ardezan.checkout.line_ids";

type OutfitMeta = {
  outfit_name: string | null;
  image_url: string | null;
  try_on_session_id: string;
};

type Bucket = {
  key: string;                          // card_id or CATALOG_BUCKET
  outfit: OutfitMeta | null;            // null = catalog/standalone items
  lines: CartLineState[];
  subtotal_amount: number;
  item_count: number;
};

export default function CartPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [lines, setLines] = useState<CartLineInput[]>([]);
  const [validated, setValidated] = useState<RevalidateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [outfitsByCard, setOutfitsByCard] = useState<Record<string, OutfitMeta>>({});
  const [selectedBuckets, setSelectedBuckets] = useState<Set<string>>(new Set());

  async function revalidate(nextLines: CartLineInput[]) {
    setLines(nextLines);
    if (nextLines.length === 0) {
      setValidated(null);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const response = await api.revalidateCart(nextLines);
      setValidated(response);
    } catch (err) {
      toast({
        title: "Couldn't refresh your bag.",
        description: err instanceof Error ? err.message : "Try again in a moment.",
        kind: "error",
      });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void revalidate(readCart());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // We need to fetch each try-on session referenced by ANY cart line so
  // we can render the outfit's hero image + name on the group header.
  // The validated lines come back as ``CartLineState`` (now carrying
  // ``try_on_session_id`` thanks to the backend echo), so we read from
  // ``validated.lines`` rather than the raw input lines.
  //
  // Critically: depend on a *stable string key* (sorted unique session
  // IDs joined) so the effect doesn't re-fire every time the validated
  // array reference changes. That's what caused the ~12-call storm.
  const sessionKey = useMemo(() => {
    const ids = new Set<string>();
    for (const l of validated?.lines ?? []) {
      if (l.try_on_session_id) ids.add(l.try_on_session_id);
    }
    return Array.from(ids).sort().join(",");
  }, [validated]);

  useEffect(() => {
    if (!sessionKey) {
      setOutfitsByCard({});
      return;
    }
    const sessionIds = sessionKey.split(",");
    let cancelled = false;
    void Promise.all(
      sessionIds.map((sid) =>
        api.getTryOnSession(sid).catch(() => null),
      ),
    ).then((sessions) => {
      if (cancelled) return;
      const next: Record<string, OutfitMeta> = {};
      sessions.forEach((s, i) => {
        const sid = sessionIds[i];
        if (!s || !sid) return;
        for (const card of (s.result_cards as ResultCard[]) ?? []) {
          if (!card.card_id) continue;
          next[card.card_id] = {
            outfit_name: card.outfit_name ?? null,
            image_url: card.image_url ?? null,
            try_on_session_id: sid,
          };
        }
      });
      setOutfitsByCard(next);
    });
    return () => {
      cancelled = true;
    };
  }, [sessionKey]);

  // Group validated lines into buckets keyed by outfit (or catalog).
  const buckets = useMemo<Bucket[]>(() => {
    const map = new Map<string, Bucket>();
    for (const line of validated?.lines ?? []) {
      const cardId = line.try_on_card_id ?? null;
      const key = cardId ?? CATALOG_BUCKET;
      let bucket = map.get(key);
      if (!bucket) {
        bucket = {
          key,
          outfit: cardId ? (outfitsByCard[cardId] ?? null) : null,
          lines: [],
          subtotal_amount: 0,
          item_count: 0,
        };
        map.set(key, bucket);
      }
      bucket.lines.push(line);
      bucket.subtotal_amount += line.line_subtotal_amount;
      bucket.item_count += line.quantity;
    }
    // Outfits first (in their cart order), catalog last.
    return Array.from(map.values()).sort((a, b) => {
      if (a.key === CATALOG_BUCKET) return 1;
      if (b.key === CATALOG_BUCKET) return -1;
      return 0;
    });
  }, [validated, outfitsByCard]);

  // Default selection: every bucket selected once we have data.
  useEffect(() => {
    if (buckets.length === 0) {
      setSelectedBuckets(new Set());
      return;
    }
    setSelectedBuckets((prev) => {
      // Only initialize when we transition from 0 → N buckets. After
      // that, leave the user's choice alone but drop stale keys.
      const validKeys = new Set(buckets.map((b) => b.key));
      const next = new Set<string>();
      let any = false;
      for (const k of prev) {
        if (validKeys.has(k)) {
          next.add(k);
          any = true;
        }
      }
      if (!any) {
        return new Set(validKeys);
      }
      return next;
    });
  }, [buckets]);

  function toggleBucket(key: string) {
    setSelectedBuckets((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const selectedLines = useMemo(
    () =>
      buckets
        .filter((b) => selectedBuckets.has(b.key))
        .flatMap((b) => b.lines),
    [buckets, selectedBuckets],
  );

  const isEmpty = !loading && lines.length === 0;
  const subtotal = selectedLines.reduce((s, l) => s + l.line_subtotal_amount, 0);
  const itemCount = selectedLines.reduce((s, l) => s + l.quantity, 0);
  const currency = validated?.totals.currency ?? "USD";
  const tax = Math.round(subtotal * 0.08);
  const total = selectedLines.length > 0
    ? subtotal + ESTIMATED_SHIPPING_CENTS + tax
    : 0;

  const checkoutBlocked =
    loading ||
    !validated ||
    validated.blocks_checkout ||
    selectedLines.length === 0;

  async function startCheckout() {
    // Hand the checkout page the exact list of line IDs to charge.
    const lineIds = selectedLines.map((l) => l.line_id);
    try {
      window.sessionStorage.setItem(
        CHECKOUT_FILTER_KEY,
        JSON.stringify(lineIds),
      );
    } catch {
      // sessionStorage unavailable — checkout will fall back to full cart.
    }
    router.push("/checkout");
  }

  return (
    <section className="max-w-[1100px] mx-auto px-5 py-10">
      <h1 className="font-display text-4xl mb-2">Your bag</h1>
      <div className="text-sm text-[color:var(--muted)] mb-8">
        {loading ? "Refreshing…" : `${validated?.totals.item_count ?? 0} items in bag`}
        {!loading && buckets.length > 1 ? (
          <> · {itemCount} selected for checkout</>
        ) : null}
      </div>

      {isEmpty ? (
        <div className="card-solid p-10 text-center">
          <div className="font-display text-2xl mb-2">Your bag is empty.</div>
          <p className="text-[color:var(--muted)] mb-5">
            Try on a few looks — full bundles can be added with one click.
          </p>
          <Link className="btn-primary" href="/try-on">
            Style me
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-8">
          <div className="space-y-5">
            {buckets.map((bucket) => (
              <BucketCard
                bucket={bucket}
                key={bucket.key}
                onToggle={() => toggleBucket(bucket.key)}
                onUpdateQuantity={(lineId, q) =>
                  void revalidate(updateCartQuantity(lineId, q))
                }
                onRemove={(lineId) => void revalidate(removeCartLine(lineId))}
                selected={selectedBuckets.has(bucket.key)}
              />
            ))}
          </div>

          <aside className="card-solid p-5 h-fit lg:sticky lg:top-24 space-y-3">
            <div className="font-display text-xl">Order summary</div>
            <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--muted)]">
              {buckets.length === 1
                ? "1 group"
                : `${selectedBuckets.size}/${buckets.length} groups selected`}
            </div>
            <div className="text-sm space-y-1.5">
              <div className="flex justify-between">
                <span className="text-[color:var(--muted)]">
                  Subtotal ({itemCount} {itemCount === 1 ? "item" : "items"})
                </span>
                <span>{formatMoney(subtotal, currency)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[color:var(--muted)]">Estimated shipping</span>
                <span>{formatMoney(ESTIMATED_SHIPPING_CENTS, currency)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[color:var(--muted)]">Estimated tax</span>
                <span>{formatMoney(tax, currency)}</span>
              </div>
            </div>
            <div className="flex justify-between text-base font-medium pt-3 border-t border-[color:var(--line)]">
              <span>Total</span>
              <span>{formatMoney(total, currency)}</span>
            </div>
            <button
              className="btn-primary w-full"
              disabled={checkoutBlocked}
              onClick={() => void startCheckout()}
              type="button"
            >
              {validated?.blocks_checkout
                ? "Resolve issues to continue"
                : selectedLines.length === 0
                  ? "Select an outfit to continue"
                  : selectedBuckets.size < buckets.length
                    ? "Check out selected"
                    : "Checkout"}
            </button>
            <button
              className="btn-ghost w-full text-xs underline underline-offset-2"
              onClick={() => {
                writeCart([]);
                void revalidate([]);
              }}
              type="button"
            >
              Clear bag
            </button>
          </aside>
        </div>
      )}
    </section>
  );
}

function BucketCard({
  bucket,
  selected,
  onToggle,
  onUpdateQuantity,
  onRemove,
}: {
  bucket: Bucket;
  selected: boolean;
  onToggle: () => void;
  onUpdateQuantity: (lineId: string, quantity: number) => void;
  onRemove: (lineId: string) => void;
}) {
  // ANY line that carries a try_on_card_id belongs to an outfit, even
  // if we couldn't resolve the session detail (expired, 404, slow load).
  // Only the explicit catalog bucket is "Individual items".
  const isOutfit = bucket.key !== CATALOG_BUCKET;
  const title = isOutfit
    ? bucket.outfit?.outfit_name ?? "Styled look"
    : "Individual items";
  const subtitle = isOutfit
    ? `${bucket.item_count} ${bucket.item_count === 1 ? "piece" : "pieces"} · from your try-on`
    : `${bucket.item_count} ${bucket.item_count === 1 ? "item" : "items"} added directly`;

  return (
    <div
      className={
        "card-solid overflow-hidden transition-opacity " +
        (selected ? "" : "opacity-60")
      }
    >
      {/* Group header */}
      <header className="px-4 sm:px-5 py-3 flex items-center gap-3 sm:gap-4 border-b border-[color:var(--line)] bg-[color:var(--ivory)]">
        {isOutfit && bucket.outfit?.image_url ? (
          <div className="relative h-14 w-12 sm:h-16 sm:w-14 rounded-md overflow-hidden bg-[color:var(--paper)] border border-[color:var(--line)] shrink-0">
            <Image
              alt={title}
              className="object-cover"
              fill
              sizes="56px"
              src={bucket.outfit.image_url}
            />
          </div>
        ) : (
          <div className="h-14 w-12 sm:h-16 sm:w-14 rounded-md bg-[color:var(--paper)] border border-[color:var(--line)] shrink-0 flex items-center justify-center text-[color:var(--muted)]">
            {isOutfit ? (
              <SparkleIcon />
            ) : (
              <BagIcon />
            )}
          </div>
        )}
        <div className="flex-1 min-w-0">
          {isOutfit ? (
            <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)] mb-0.5 inline-flex items-center gap-1">
              <SparkleIcon />
              <span>Look</span>
            </div>
          ) : (
            <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)] mb-0.5">
              Catalog
            </div>
          )}
          <div className="font-display text-lg leading-tight truncate">{title}</div>
          <div className="text-[12px] text-[color:var(--muted)] mt-0.5">{subtitle}</div>
        </div>
        <label className="flex items-center gap-2 text-[12px] cursor-pointer shrink-0">
          <input
            checked={selected}
            className="h-4 w-4 accent-[color:var(--ink)]"
            onChange={onToggle}
            type="checkbox"
          />
          <span className="hidden sm:inline">{selected ? "In checkout" : "Skip"}</span>
        </label>
      </header>

      {/* Lines */}
      <ul className="divide-y divide-[color:var(--line)]">
        {bucket.lines.map((line) => (
          <li className="px-4 sm:px-5 py-3 flex gap-3 sm:gap-4 items-stretch" key={line.line_id}>
            <div className="w-16 h-20 sm:w-20 sm:h-24 rounded-md overflow-hidden bg-[color:var(--ivory)] relative shrink-0">
              {line.primary_image_url ? (
                <Image
                  alt={line.product_title ?? ""}
                  className="object-cover"
                  fill
                  sizes="80px"
                  src={line.primary_image_url}
                />
              ) : null}
            </div>

            <div className="flex-1 min-w-0">
              {line.kind === "custom_design" ? (
                <div className="font-display text-base leading-tight">
                  {line.product_title ?? "Custom design"}
                </div>
              ) : (
                <Link
                  className="font-display text-base leading-tight hover:underline"
                  href={`/product/${line.product_slug ?? line.product_id}`}
                >
                  {line.product_title ?? line.product_id}
                </Link>
              )}
              <div className="text-[11px] text-[color:var(--muted)] mt-0.5">
                {line.kind === "custom_design"
                  ? "Made-to-order"
                  : [line.size, line.color].filter(Boolean).join(" · ")}
              </div>
              {line.message ? (
                <div
                  className="text-[11px] mt-1.5"
                  style={{
                    color:
                      line.status === "out_of_stock" || line.status === "removed"
                        ? "#8d1717"
                        : "var(--ink-soft)",
                  }}
                >
                  {line.message}
                </div>
              ) : null}

              <div className="mt-2 flex items-center gap-3">
                <div className="inline-flex items-center border border-[color:var(--line)] rounded-md bg-white">
                  <button
                    aria-label="Decrease"
                    className="w-9 h-9 sm:w-7 sm:h-7 flex items-center justify-center hover:bg-black/5"
                    onClick={() => onUpdateQuantity(line.line_id, line.quantity - 1)}
                    type="button"
                  >
                    −
                  </button>
                  <span className="w-8 sm:w-7 text-center text-[12px] tabular-nums">
                    {line.quantity}
                  </span>
                  <button
                    aria-label="Increase"
                    className="w-9 h-9 sm:w-7 sm:h-7 flex items-center justify-center hover:bg-black/5"
                    onClick={() => onUpdateQuantity(line.line_id, line.quantity + 1)}
                    type="button"
                  >
                    +
                  </button>
                </div>
                <button
                  className="text-[11px] text-[color:var(--muted)] underline underline-offset-2 hover:text-[color:var(--ink)]"
                  onClick={() => onRemove(line.line_id)}
                  type="button"
                >
                  Remove
                </button>
              </div>
            </div>

            <div className="text-right font-display text-sm shrink-0 tabular-nums">
              {formatMoney(line.line_subtotal_amount, line.pricing?.currency)}
            </div>
          </li>
        ))}
      </ul>

      {/* Group footer */}
      <footer className="px-4 sm:px-5 py-2.5 bg-white flex items-center justify-between text-[12px]">
        <span className="text-[color:var(--muted)]">Group subtotal</span>
        <span className="font-medium tabular-nums">
          {formatMoney(bucket.subtotal_amount, bucket.lines[0]?.pricing?.currency)}
        </span>
      </footer>
    </div>
  );
}

function SparkleIcon() {
  return (
    <svg
      aria-hidden
      fill="currentColor"
      height="12"
      viewBox="0 0 24 24"
      width="12"
    >
      <path d="M12 3 L13.5 9 L20 10.5 L13.5 12 L12 18 L10.5 12 L4 10.5 L10.5 9 Z" />
    </svg>
  );
}

function BagIcon() {
  return (
    <svg aria-hidden fill="none" height="16" stroke="currentColor" strokeWidth="1.6" viewBox="0 0 24 24" width="16">
      <path d="M3 6h18l-2 12H5L3 6z" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}
