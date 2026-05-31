import Link from "next/link";
import type { Metadata } from "next";

import { ContentPage, ContentSection } from "@/components/content-page";

export const metadata: Metadata = {
  title: "Privacy",
  description:
    "How Ardezan handles your photos, body data, orders, and account information — and the controls you have over them.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <ContentPage
      eyebrow="Legal"
      title="Privacy"
      lastUpdated="May 2026"
      intro="Ardezan is an AI fitting room, so privacy matters more here than at an ordinary store — we handle photos of you. This page explains exactly what we collect, how the AI uses it, how long we keep it, and how you stay in control."
    >
      <ContentSection heading="What we collect">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>
            <strong>Account details</strong> — your name and email when you
            create an account.
          </li>
          <li>
            <strong>Order details</strong> — items, shipping address, and order
            history when you buy something.
          </li>
          <li>
            <strong>Try-on photos</strong> — the photo you upload to generate a
            look. You may optionally save one photo for reuse.
          </li>
          <li>
            <strong>Body profile (optional)</strong> — if you opt in, an
            estimated body shape and fit preference so future try-ons skip the
            analysis step.
          </li>
          <li>
            <strong>Usage data</strong> — basic, privacy-respecting analytics to
            keep the service reliable.
          </li>
        </ul>
      </ContentSection>

      <ContentSection heading="How the AI uses your photo">
        <p>
          When you start a try-on, your photo is sent to our AI provider to
          generate a preview of you in the recommended garments. Generated
          images are clearly labelled as AI previews — they are approximations,
          not photographs of the real product on your body.
        </p>
        <p>
          We never use your photos to train AI models, and we never sell them.
        </p>
      </ContentSection>

      <ContentSection heading="How long we keep photos">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>
            <strong>Anonymous try-ons</strong> — uploads are deleted within
            about 15 minutes; generated previews within about 24 hours.
          </li>
          <li>
            <strong>Saved photo</strong> — kept only if you opt in, and only
            until you remove it. Deleting it wipes the file from our storage.
          </li>
          <li>
            <strong>Ordered looks</strong> — if you buy a look you tried on, we
            keep that generated image so our team can pack the right items, then
            delete it within 30 days of the order being completed.
          </li>
        </ul>
      </ContentSection>

      <ContentSection heading="Payments">
        <p>
          Payments are processed by Stripe. We never see or store your full card
          number — Stripe handles card data directly under its own PCI-compliant
          systems.
        </p>
      </ContentSection>

      <ContentSection heading="Your controls">
        <p>
          You can remove your saved photo and body profile at any time from your{" "}
          <Link className="underline underline-offset-2" href="/account/me">
            account settings
          </Link>
          . You can also request deletion of your account and associated data by
          contacting us via the{" "}
          <Link className="underline underline-offset-2" href="/contact">
            contact page
          </Link>
          .
        </p>
      </ContentSection>

      <ContentSection heading="Changes to this policy">
        <p>
          We may update this policy as the product evolves. Material changes will
          be reflected by the “last updated” date above.
        </p>
      </ContentSection>
    </ContentPage>
  );
}
