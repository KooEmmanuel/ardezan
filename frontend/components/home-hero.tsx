"use client";

import Link from "next/link";

// Hero is now a full-bleed cinematic: the rendered reel (studio → try-on →
// buy, built in /video with Remotion) plays muted-looped as the BACKGROUND,
// with the headline + CTAs overlaid on the left over a legibility scrim.
// The old right-column animated storyboard (HeroDemo) has been removed —
// the background video now carries that story.
//
// Re-render the reel in /video (`npm run render`), then copy
// hero.{mp4,webm} + poster.png into public/site/.
export function HomeHero() {
  return (
    <section className="relative w-full overflow-hidden bg-black">
      {/* ─── Background reel ─── */}
      <video
        className="hero-reel absolute inset-0 w-full h-full object-cover"
        autoPlay
        muted
        loop
        playsInline
        poster="/site/poster.png"
        aria-hidden
      >
        {/* mp4 only — the crisp 3.36 Mbps h264 render. (The webm export came
            out heavily compressed; h264 mp4 is supported by every modern
            browser, so we serve the good file directly.) */}
        <source src="/site/hero.mp4" type="video/mp4" />
      </video>
      {/* Reduced-motion fallback (see globals.css) */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/site/poster.png"
        alt=""
        aria-hidden
        className="hero-reel-fallback hidden absolute inset-0 w-full h-full object-cover"
      />

      {/* Legibility scrim — darkest on the left where the copy sits, so the
          text stays readable whether the reel is in its dark studio act or
          its bright UI act. */}
      <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/45 to-black/10" />

      {/* ─── Overlaid copy + CTA ─── */}
      <div className="relative z-10 max-w-[1280px] mx-auto px-4 sm:px-5 min-h-[80vh] sm:min-h-[88vh] flex items-center">
        <div className="max-w-xl text-white">
          <div className="text-[11px] uppercase tracking-[0.18em] text-white/65 mb-3">
            An AI-native fitting room
          </div>
          <h1 className="font-display text-[3.1rem] sm:text-6xl leading-[0.98] sm:leading-[1.02] mb-4">
            See clothes on <i>you</i>,<br />not on a model.
          </h1>
          <p className="text-white/80 text-base sm:text-lg leading-relaxed mb-6 max-w-md">
            Upload one full-body photo. Our stylist drapes ten looks onto your shape —
            fit, fabric, and proportion — in about fifteen seconds.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 max-w-md">
            <Link
              className="inline-flex flex-1 items-center justify-center min-h-[2.75rem] px-6 rounded-[0.6rem] bg-white text-black font-medium text-sm hover:bg-white/90 transition"
              href="/try-on"
            >
              Try it now
            </Link>
            <Link
              className="inline-flex flex-1 items-center justify-center min-h-[2.75rem] px-6 rounded-[0.6rem] border border-white/40 text-white font-medium text-sm hover:bg-white/10 transition"
              href="/try-on/design"
            >
              Or design your own
            </Link>
          </div>
          <div className="text-[11px] text-white/60 mt-3 max-w-md">
            Free preview · no signup to try · your photo stays on your device.
          </div>
        </div>
      </div>
    </section>
  );
}
