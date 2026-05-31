import Link from "next/link";
import type { Metadata } from "next";

import { ContentPage, ContentSection } from "@/components/content-page";

export const metadata: Metadata = {
  title: "Contact",
  description:
    "Get in touch with the Ardezan team about orders, sizing, returns, or your account.",
  alternates: { canonical: "/contact" },
};

const SUPPORT_EMAIL = "support@ardezan.com";

export default function ContactPage() {
  return (
    <ContentPage
      eyebrow="Help"
      title="Contact us"
      intro="We’re a small team and we read every message. Here’s the fastest way to reach us."
    >
      <ContentSection heading="Email">
        <p>
          For anything — orders, sizing, returns, or your account — email{" "}
          <a
            className="underline underline-offset-2"
            href={`mailto:${SUPPORT_EMAIL}`}
          >
            {SUPPORT_EMAIL}
          </a>
          . We typically reply within one business day.
        </p>
        <p>
          If your question is about a specific order, include your order number
          so we can help faster.
        </p>
      </ContentSection>

      <ContentSection heading="Before you write">
        <p>A few things you can often sort out yourself:</p>
        <ul className="list-disc pl-5 space-y-1.5">
          <li>
            Track or manage an order from{" "}
            <Link className="underline underline-offset-2" href="/account/orders">
              your orders
            </Link>
            .
          </li>
          <li>
            Start a return or exchange on the{" "}
            <Link className="underline underline-offset-2" href="/returns">
              returns page
            </Link>
            .
          </li>
          <li>
            Fit questions are covered under{" "}
            <Link className="underline underline-offset-2" href="/sizing">
              sizing &amp; fit
            </Link>
            .
          </li>
        </ul>
      </ContentSection>
    </ContentPage>
  );
}
