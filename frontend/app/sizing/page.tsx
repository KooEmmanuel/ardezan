import Link from "next/link";
import type { Metadata } from "next";

import { ContentPage, ContentSection } from "@/components/content-page";

export const metadata: Metadata = {
  title: "Sizing & fit",
  description:
    "How Ardezan’s AI estimates your fit, how to get the most accurate try-on, and how to measure yourself.",
  alternates: { canonical: "/sizing" },
};

export default function SizingPage() {
  return (
    <ContentPage
      eyebrow="Help"
      title="Sizing & fit"
      intro="Ardezan recommends a size for each garment based on the photo you upload and the details you share. Here’s how to get the most accurate result."
    >
      <ContentSection heading="How the fit estimate works">
        <p>
          When you try on a look, our AI estimates your proportions from your
          photo and any details you add, then suggests the size most likely to
          fit for each item. You can always change the size before adding to your
          bag.
        </p>
      </ContentSection>

      <ContentSection heading="Getting the best result">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>Use a clear, well-lit, full-body photo.</li>
          <li>Stand straight, facing the camera, with arms slightly away from your body.</li>
          <li>Wear fitted clothing so your shape is visible.</li>
          <li>Add your height when prompted — it noticeably improves accuracy.</li>
        </ul>
      </ContentSection>

      <ContentSection heading="Measuring yourself">
        <p>
          If you’d like to double-check a size, measure with a soft tape:
        </p>
        <ul className="list-disc pl-5 space-y-1.5">
          <li><strong>Chest/bust</strong> — around the fullest part, tape level.</li>
          <li><strong>Waist</strong> — around your natural waistline.</li>
          <li><strong>Hips</strong> — around the fullest part.</li>
        </ul>
        <p>
          Each product page lists its specific measurements where available.
        </p>
      </ContentSection>

      <ContentSection heading="Still unsure?">
        <p>
          If a size feels off, it’s easy to exchange — see{" "}
          <Link className="underline underline-offset-2" href="/returns">
            returns &amp; exchanges
          </Link>
          , or reach us on the{" "}
          <Link className="underline underline-offset-2" href="/contact">
            contact page
          </Link>
          .
        </p>
      </ContentSection>
    </ContentPage>
  );
}
