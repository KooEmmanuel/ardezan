"use client";

import Link from "next/link";

// Full-bleed cinematic hero: the rendered Remotion reel (Act 1 Veo studio
// footage → Act 2 coded try-on→buy flow) plays muted-looped behind a thin
// scrim. The reel carries the story; the overlay keeps the *real* CTAs
// clickable no matter which scene is on screen. Built in /video (Remotion);
// re-render with `npm run render` there, then copy hero.{mp4,webm} + poster.png
// into public/site/.
//
// Source video already bakes in the "See clothes on you" headline, so the
// overlay stays minimal to avoid competing with it.
export function HeroCinematic() {
  return (
    <section className="relative w-full overflow-hidden bg-black">
      <div className="relative w-full aspect-video max-h-[86vh] mx-auto">
        {/* prefers-reduced-motion: the <video> is replaced by the poster via CSS. */}
        <video
          className="hero-reel absolute inset-0 w-full h-full object-cover"
          autoPlay
          muted
          loop
          playsInline
          poster="/site/poster.png"
          aria-label="Ardezan: upload one photo, see ten looks styled on you, and check out."
        >
          <source src="/site/hero.webm" type="video/webm" />
          <source src="/site/hero.mp4" type="video/mp4" />
        </video>
        {/* Poster fallback shown when motion is reduced. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/site/poster.png"
          alt=""
          aria-hidden
          className="hero-reel-fallback hidden absolute inset-0 w-full h-full object-cover"
        />

        {/* Bottom scrim + persistent CTAs */}
        <div className="absolute inset-x-0 bottom-0 pt-24 pb-7 px-5 bg-gradient-to-t from-black/70 via-black/25 to-transparent">
          <div className="max-w-[1280px] mx-auto flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
            <div className="text-white/85 text-[13px] sm:text-sm max-w-sm leading-relaxed">
              Upload one full-body photo — ten looks, styled on your shape, in about
              fifteen seconds.
            </div>
            <div className="flex flex-col sm:flex-row gap-3 sm:flex-shrink-0">
              <Link
                className="inline-flex items-center justify-center min-h-[2.75rem] px-6 rounded-[0.6rem] bg-white text-black font-medium text-sm hover:bg-white/90 transition"
                href="/try-on"
              >
                Try it on now
              </Link>
              <Link
                className="inline-flex items-center justify-center min-h-[2.75rem] px-6 rounded-[0.6rem] border border-white/40 text-white font-medium text-sm hover:bg-white/10 transition"
                href="/try-on/design"
              >
                Or design your own
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
