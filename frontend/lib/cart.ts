import type { CartLineInput, ResultCard, VariantPublic } from "@/lib/types";

const CART_KEY = "atelier.cart.v1";
export const CART_EVENT = "atelier-cart-changed";

export function readCart(): CartLineInput[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(CART_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as CartLineInput[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function writeCart(lines: CartLineInput[]): void {
  window.localStorage.setItem(CART_KEY, JSON.stringify(lines));
  window.dispatchEvent(new Event(CART_EVENT));
}

export function addVariantToCart(input: {
  product_id: string;
  variant: VariantPublic;
  quantity?: number;
}): CartLineInput[] {
  const cart = readCart();
  const existing = cart.find((line) => line.variant_id === input.variant.variant_id);
  if (existing) {
    existing.quantity = Math.min(99, existing.quantity + (input.quantity ?? 1));
    existing.expected_unit_price_amount = input.variant.pricing.price_amount ?? null;
  } else {
    cart.push({
      line_id: `line_${crypto.randomUUID()}`,
      product_id: input.product_id,
      variant_id: input.variant.variant_id,
      quantity: input.quantity ?? 1,
      source: "catalog",
      expected_unit_price_amount: input.variant.pricing.price_amount ?? null,
    });
  }
  writeCart(cart);
  return cart;
}

export function removeCartLine(lineId: string): CartLineInput[] {
  const next = readCart().filter((line) => line.line_id !== lineId);
  writeCart(next);
  return next;
}

export function updateCartQuantity(lineId: string, quantity: number): CartLineInput[] {
  const next = readCart()
    .map((line) => (line.line_id === lineId ? { ...line, quantity } : line))
    .filter((line) => line.quantity > 0);
  writeCart(next);
  return next;
}

// ── Try-on additions ───────────────────────────────────────────────
// Full-look adds every item in the card as separate lines so the cart
// shows the user what they're committing to. Lines stay distinct from
// catalog lines via ``source`` + ``try_on_card_id`` so revalidate keeps
// them grouped if they need a swap.
export function addFullLookToCart(input: {
  try_on_session_id: string;
  card: ResultCard;
}): CartLineInput[] {
  const cart = readCart();
  for (const item of input.card.items) {
    cart.push({
      line_id: `line_${crypto.randomUUID()}`,
      product_id: item.product_id,
      variant_id: item.variant_id,
      quantity: 1,
      source: "try_on_full_look",
      try_on_session_id: input.try_on_session_id,
      try_on_card_id: input.card.card_id,
      expected_unit_price_amount: item.price_amount ?? null,
    });
  }
  writeCart(cart);
  return cart;
}

export function addSingleItemToCart(input: {
  try_on_session_id: string;
  card_id: string;
  item: ResultCard["items"][number];
}): CartLineInput[] {
  const cart = readCart();
  cart.push({
    line_id: `line_${crypto.randomUUID()}`,
    product_id: input.item.product_id,
    variant_id: input.item.variant_id,
    quantity: 1,
    source: "try_on_single_item",
    try_on_session_id: input.try_on_session_id,
    try_on_card_id: input.card_id,
    expected_unit_price_amount: input.item.price_amount ?? null,
  });
  writeCart(cart);
  return cart;
}

// ── Design Me additions ────────────────────────────────────────────
// A custom design is a one-off line — no variant, no merging. The
// design_session_id is the only key the backend needs to look up the
// brief, the fabric, and the locked-in estimate.
export function addCustomDesignToCart(input: {
  design_session_id: string;
  expected_unit_price_amount: number;
}): CartLineInput[] {
  const cart = readCart();
  cart.push({
    line_id: `line_${crypto.randomUUID()}`,
    kind: "custom_design",
    design_session_id: input.design_session_id,
    quantity: 1,
    source: "design_me",
    expected_unit_price_amount: input.expected_unit_price_amount,
  });
  writeCart(cart);
  return cart;
}
