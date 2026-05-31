import type { Metadata } from "next";
import { Cormorant_Garamond, Inter } from "next/font/google";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

import { CartBadge } from "@/components/cart-badge";
import { ChromeGate } from "@/components/chrome-gate";
import { NavViewToggle } from "@/components/nav-view-toggle";
import { ToastProvider } from "@/components/toast";
import { SITE_NAME, SITE_URL } from "@/lib/site";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  display: "swap",
  variable: "--font-inter",
});

const display = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-display",
});

const SITE_DESCRIPTION =
  "See clothes on you, not on a model. Upload one full-body photo; get ten styled looks.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} — an AI-native fitting room`,
    template: `%s · ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: [
    "AI try-on",
    "virtual fitting room",
    "see clothes on you",
    "AI fashion",
    "online clothing",
  ],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: `${SITE_NAME} — an AI-native fitting room`,
    description: SITE_DESCRIPTION,
    url: SITE_URL,
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE_NAME} — an AI-native fitting room`,
    description: SITE_DESCRIPTION,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large" },
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${display.variable}`}>
      <body className="min-h-screen">
        <ToastProvider>
        <ChromeGate>
        <header className="border-b border-[color:var(--line)] bg-[color:var(--paper)]/85 backdrop-blur-md sticky top-0 z-40">
          <div className="max-w-[1280px] mx-auto px-4 sm:px-5 py-3 sm:py-4 flex items-center gap-2 sm:gap-4">
            <Link className="shrink-0 inline-flex items-center" href="/" aria-label="Ardezan home">
              <Image
                alt="Ardezan"
                className="h-7 sm:h-9 w-auto"
                height={36}
                priority
                src="/logo-v2.png"
                width={40}
              />
            </Link>

            <nav className="hidden md:flex items-center gap-5 ml-6 text-sm" aria-label="Primary">
              <Link className="nav-link" href="/catalog?cat=women">Women</Link>
              <Link className="nav-link" href="/catalog?cat=men">Men</Link>
              <Link className="nav-link" href="/catalog?cat=bespoke">Bespoke</Link>
              <Link className="nav-link" href="/try-on/design">Design Me</Link>
              <Link className="nav-link" href="/catalog?cat=new">New</Link>
            </nav>

            <div className="ml-auto flex items-center gap-1.5 sm:gap-3">
              <NavViewToggle />
              <button aria-label="Search" className="hidden sm:inline-flex p-2 rounded-md hover:bg-black/5" title="Search" type="button">
                <SearchIcon />
              </button>
              <Link aria-label="Account" className="hidden sm:inline-flex p-2 rounded-md hover:bg-black/5" href="/account/me" title="Account">
                <UserIcon />
              </Link>
              <Link aria-label="Cart" className="p-2 rounded-md hover:bg-black/5 relative" href="/cart" title="Cart">
                <CartIcon />
                <CartBadge />
              </Link>
            </div>
          </div>
        </header>
        </ChromeGate>

        <main id="main" className="min-h-[calc(100vh-64px)]">{children}</main>

        <ChromeGate>
        <footer className="border-t border-[color:var(--line)] mt-12">
          <div className="max-w-[1280px] mx-auto px-5 py-8 grid grid-cols-2 sm:grid-cols-4 gap-6 text-sm">
            <div>
              <div className="font-display text-lg mb-2">Ardezan</div>
              <div className="text-[color:var(--muted)] text-xs leading-relaxed">
                An AI-native fitting room.<br />Made for one body — yours.
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--muted)] mb-2">Shop</div>
              <div className="space-y-1 text-[color:var(--ink-soft)]">
                <Link className="block" href="/try-on">Try-On</Link>
                <Link className="block" href="/try-on/design">Design Me</Link>
                <Link className="block" href="/catalog?cat=bespoke">Bespoke</Link>
                <Link className="block" href="/catalog">Catalog</Link>
                <Link className="block" href="/account/fitting-room">Fitting Room</Link>
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--muted)] mb-2">Help</div>
              <div className="space-y-1 text-[color:var(--ink-soft)]">
                <Link className="block" href="/sizing">Sizing</Link>
                <Link className="block" href="/returns">Returns</Link>
                <Link className="block" href="/contact">Contact</Link>
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--muted)] mb-2">Studio</div>
              <div className="space-y-1 text-[color:var(--ink-soft)]">
                <Link className="block" href="/privacy">Privacy</Link>
                <Link className="block" href="/terms">Terms</Link>
              </div>
            </div>
          </div>
          <div className="border-t border-[color:var(--line)]">
            <div className="max-w-[1280px] mx-auto px-5 py-3 text-[11px] text-[color:var(--muted)] flex flex-wrap items-center gap-3">
              <span>© Ardezan — photos generated for demonstration.</span>
            </div>
          </div>
        </footer>
        </ChromeGate>
        </ToastProvider>
      </body>
    </html>
  );
}

function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 4-7 8-7s8 3 8 7" />
    </svg>
  );
}

function CartIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M3 3h2l3 14h13" />
      <circle cx="10" cy="20" r="1.5" />
      <circle cx="18" cy="20" r="1.5" />
    </svg>
  );
}
