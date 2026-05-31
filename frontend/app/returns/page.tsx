import Link from "next/link";
import type { Metadata } from "next";

import { ContentPage, ContentSection } from "@/components/content-page";

export const metadata: Metadata = {
  title: "Returns & exchanges",
  description:
    "Ardezan’s returns and exchanges policy — the window, item condition, how to start a return, and refund timing.",
  alternates: { canonical: "/returns" },
};

export default function ReturnsPage() {
  return (
    <ContentPage
      eyebrow="Help"
      title="Returns & exchanges"
      intro="Because an AI preview isn’t the same as trying something on in person, returns are simple and expected. Here’s how it works."
    >
      <ContentSection heading="The window">
        <p>
          You can request a return within <strong>30 days</strong> of delivery.
          Items should be unworn, unwashed, and with original tags attached.
        </p>
      </ContentSection>

      <ContentSection heading="How to start a return">
        <p>If you have an account:</p>
        <ul className="list-disc pl-5 space-y-1.5">
          <li>
            Go to{" "}
            <Link className="underline underline-offset-2" href="/account/orders">
              your orders
            </Link>
            , open the order, and choose “Request a return.”
          </li>
          <li>Tell us which items and why, then send them back.</li>
        </ul>
        <p>
          If you checked out as a guest, use the manage-order link in your
          confirmation email to open the same return flow.
        </p>
      </ContentSection>

      <ContentSection heading="Refunds">
        <p>
          Once we receive and check the returned items, we issue your refund to
          the original payment method. Refunds usually appear within 5–10
          business days, depending on your bank.
        </p>
      </ContentSection>

      <ContentSection heading="Exchanges">
        <p>
          For a different size or colour, place a new order for the item you want
          and return the original. This is the fastest way to get the right
          piece without waiting on stock to be reserved.
        </p>
      </ContentSection>

      <ContentSection heading="Need help?">
        <p>
          Questions about a specific order? Reach us on the{" "}
          <Link className="underline underline-offset-2" href="/contact">
            contact page
          </Link>{" "}
          and include your order number.
        </p>
      </ContentSection>
    </ContentPage>
  );
}
