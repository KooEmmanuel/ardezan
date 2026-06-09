import Link from "next/link";

export default function NotFound() {
  return (
    <section className="max-w-[640px] mx-auto px-5 py-20">
      <div className="card-solid p-8 sm:p-10 text-center">
        <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
          404
        </div>
        <h1 className="font-display text-3xl sm:text-4xl mb-3">
          This page seems to have walked off the runway.
        </h1>
        <p className="text-sm text-[color:var(--muted)] mb-6 leading-relaxed">
          The link may be old, or the piece may no longer be available.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-2">
          <Link className="btn-primary inline-flex" href="/catalog">
            Browse the catalog
          </Link>
          <Link
            className="btn-ghost text-sm underline underline-offset-4"
            href="/"
          >
            Back to home
          </Link>
        </div>
      </div>
    </section>
  );
}
