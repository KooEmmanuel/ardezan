// Demo / hackathon helpers.
//
// Ardezan runs in Stripe TEST mode for judging, so we (a) make it obvious the
// store is safe to click through and (b) prefill the checkout so anyone can
// run the whole flow in seconds — they only need to paste the test card
// (Stripe forbids prefilling the card number itself, for PCI reasons).
//
// On by default. For a real launch, set NEXT_PUBLIC_DEMO_MODE=false to drop
// the banner and all prefilling.
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE !== "false";

// Stripe's universal test card: any future expiry, any CVC, any postal code.
export const STRIPE_TEST_CARD = "4242 4242 4242 4242";

// Prefilled contact + shipping so a judge's only job is to paste the card.
export const DEMO_CHECKOUT = {
  email: "demo@ardezan.store",
  address: {
    name: "Demo Shopper",
    line1: "123 Atelier Way",
    line2: "",
    city: "New York",
    region: "NY",
    postal_code: "10012",
    country: "US",
  },
} as const;
