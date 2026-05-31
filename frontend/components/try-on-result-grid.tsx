"use client";

import { useState } from "react";

import { formatMoney } from "@/lib/api";
import { addFullLookToCart, addSingleItemToCart } from "@/lib/cart";
import type { ResultCard } from "@/lib/types";

export function TryOnResultGrid({
  cards,
  loading,
  sessionId,
}: {
  cards: ResultCard[];
  loading: boolean;
  sessionId: string | null;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <article className="glass overflow-hidden" key={i}>
            <div className="ratio-45 shimmer" />
            <div className="p-3 bg-white/85 backdrop-blur-md">
              <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
                Styling outfit {i + 1}
              </div>
              <div className="h-3 w-2/3 bg-[color:var(--ivory)] rounded mt-2" />
            </div>
          </article>
        ))}
      </div>
    );
  }

  if (cards.length === 0) {
    return (
      <div className="glass-strong p-6 text-center text-[color:var(--ink-soft)]">
        No outfits yet — hang on.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {cards.map((card) => (
        <TryOnCard card={card} key={card.card_id} sessionId={sessionId} />
      ))}
    </div>
  );
}

function TryOnCard({
  card,
  sessionId,
}: {
  card: ResultCard;
  sessionId: string | null;
}) {
  const [feedback, setFeedback] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const isRendering = !card.image_url;
  const isUnavailable = card.status === "unavailable";

  function onAddFullLook() {
    if (!sessionId) return;
    addFullLookToCart({ try_on_session_id: sessionId, card });
    setFeedback("Look added to cart.");
  }

  function onAddItem(item: ResultCard["items"][number]) {
    if (!sessionId) return;
    addSingleItemToCart({
      try_on_session_id: sessionId,
      card_id: card.card_id,
      item,
    });
    setFeedback(`${item.product_title ?? "Item"} added to cart.`);
  }

  return (
    <article className="glass-strong overflow-hidden flex flex-col">
      <div className="ratio-45 relative overflow-hidden bg-[color:var(--ivory)]">
        {card.image_url ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            alt={card.outfit_name ?? "Outfit"}
            className="absolute inset-0 w-full h-full object-cover"
            src={card.image_url}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-center shimmer">
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
                Rendering
              </div>
              <div className="font-display text-base mt-1">
                {card.outfit_name ?? "Outfit"}
              </div>
            </div>
          </div>
        )}
        <span className="absolute top-3 left-3 pill pill-ai">AI preview</span>
        {card.status === "partially_unavailable" ? (
          <span className="absolute top-3 right-3 pill pill-outline">
            Limited stock
          </span>
        ) : null}
      </div>

      <div className="p-3 bg-white/85 backdrop-blur-md flex-1 flex flex-col">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-display text-base leading-tight">
              {card.outfit_name ?? "Outfit"}
            </div>
            <div className="text-[11px] text-[color:var(--muted)] mt-0.5">
              {card.items.length}-piece
            </div>
          </div>
          <div className="text-sm font-medium shrink-0">
            {formatMoney(card.total_amount, card.currency)}
          </div>
        </div>

        {card.rationale ? (
          <p className="text-[11px] text-[color:var(--muted)] mt-2 leading-snug">
            {card.rationale}
          </p>
        ) : null}

        <button
          className="text-[11px] underline underline-offset-2 text-[color:var(--ink-soft)] text-left mt-3"
          onClick={() => setExpanded((s) => !s)}
          type="button"
        >
          {expanded ? "Hide items" : `View ${card.items.length} items`}
        </button>

        {expanded ? (
          <ul className="text-[12px] mt-2 space-y-1.5">
            {card.items.map((item) => (
              <li className="flex items-center justify-between gap-3" key={item.variant_id}>
                <div className="min-w-0 flex-1">
                  <div className="truncate">{item.product_title ?? item.product_id}</div>
                  <div className="text-[10px] text-[color:var(--muted)]">
                    {[item.recommended_size, item.color].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <button
                  className="text-[10px] underline underline-offset-2 shrink-0"
                  disabled={!sessionId}
                  onClick={() => onAddItem(item)}
                  type="button"
                >
                  Add
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="mt-auto pt-3">
          <button
            className="btn-primary w-full text-sm"
            disabled={!sessionId || isUnavailable || isRendering}
            onClick={onAddFullLook}
            type="button"
          >
            {isRendering ? "Rendering…" : "Add full look"}
          </button>
          {feedback ? (
            <p className="text-[11px] mt-2" style={{ color: "#166534" }}>
              {feedback}
            </p>
          ) : null}
        </div>
      </div>
    </article>
  );
}
