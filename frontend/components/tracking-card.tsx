// Renders the carrier + tracking number on the customer-facing order
// pages. If the order hasn't shipped yet, falls back to a calm "We'll
// email when it ships" copy so the section never looks empty.

import type { OrderPublic } from "@/lib/types";

const CARRIER_TRACKING_URLS: Record<string, (n: string) => string> = {
  USPS: (n) =>
    `https://tools.usps.com/go/TrackConfirmAction?qtc_tLabels1=${encodeURIComponent(n)}`,
  FedEx: (n) =>
    `https://www.fedex.com/fedextrack/?tracknumbers=${encodeURIComponent(n)}`,
  UPS: (n) =>
    `https://www.ups.com/track?tracknum=${encodeURIComponent(n)}`,
  DHL: (n) =>
    `https://www.dhl.com/global-en/home/tracking/tracking-express.html?submit=1&tracking-id=${encodeURIComponent(n)}`,
  "Royal Mail": (n) =>
    `https://www.royalmail.com/track-your-item#/tracking-results/${encodeURIComponent(n)}`,
};

function carrierTrackingUrl(carrier: string | null, number: string | null): string | null {
  if (!number) return null;
  if (!carrier) return null;
  const builder = CARRIER_TRACKING_URLS[carrier];
  return builder ? builder(number) : null;
}

export function TrackingCard({ order }: { order: OrderPublic }) {
  const { fulfillment } = order;
  const number = fulfillment.tracking_number;
  const carrier = fulfillment.carrier;
  const shippedAt = fulfillment.shipped_at;
  const deliveredAt = fulfillment.delivered_at;

  // The whole card is only meaningful once the order ships. Before that
  // we show a small "we'll email you" placeholder so the customer knows
  // where to look later.
  if (!number) {
    return (
      <div className="rounded-lg bg-[color:var(--ivory)] p-4 text-sm">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
          Shipment
        </div>
        <div className="text-[color:var(--ink-soft)]">
          We&apos;ll email a tracking link as soon as this order ships.
        </div>
      </div>
    );
  }

  const trackingUrl =
    fulfillment.tracking_url ?? carrierTrackingUrl(carrier, number);

  return (
    <div className="rounded-lg bg-[color:var(--ivory)] p-4 text-sm">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-1">
        Shipment
      </div>
      <div className="space-y-0.5">
        {carrier ? <div>{carrier}</div> : null}
        <div className="font-mono text-[12px] break-all">{number}</div>
        {shippedAt ? (
          <div className="text-[12px] text-[color:var(--muted)]">
            Shipped {new Date(shippedAt).toLocaleDateString()}
          </div>
        ) : null}
        {deliveredAt ? (
          <div className="text-[12px]" style={{ color: "#166534" }}>
            Delivered {new Date(deliveredAt).toLocaleDateString()}
          </div>
        ) : null}
      </div>
      {trackingUrl ? (
        <a
          className="btn-secondary inline-flex mt-3 text-xs"
          href={trackingUrl}
          rel="noopener noreferrer"
          target="_blank"
        >
          Track shipment →
        </a>
      ) : null}
    </div>
  );
}
