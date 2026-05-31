"use client";

import { useEffect, useState } from "react";

// HEIC files (typical iPhone uploads) can't be decoded by Chrome or Firefox.
// Safari renders them fine. The backend processes them either way via
// pillow-heif, but the browser preview is blank on non-Safari.
//
// This component:
//   - Tries to render the photo natively
//   - Falls back to a styled "Photo ready" card if the browser can't decode
//     the bytes (onError) or if the file MIME is in the known-unrenderable list

const UNRENDERABLE_MIME = new Set(["image/heic", "image/heif"]);

function isUnrenderable(file: File): boolean {
  if (UNRENDERABLE_MIME.has(file.type.toLowerCase())) return true;
  // Some browsers report an empty type for .heic files coming via drag-drop
  if (!file.type && /\.heic$|\.heif$/i.test(file.name)) return true;
  return false;
}

export function PhotoPreview({
  file,
  badge,
}: {
  file: File;
  badge?: React.ReactNode;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    if (isUnrenderable(file)) {
      setErrored(true);
      setSrc(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setSrc(url);
    setErrored(false);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  if (errored || !src) {
    return (
      <div className="relative w-full max-h-[520px] rounded-xl border border-white/40 bg-white/40 p-10 text-center">
        <div className="mx-auto mb-3 w-14 h-14 rounded-full bg-black/10 flex items-center justify-center">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <circle cx="9" cy="9" r="2" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
        </div>
        <div className="font-display text-lg">Photo ready</div>
        <div className="text-xs text-[color:var(--muted)] mt-1 truncate max-w-full">
          {file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB
        </div>
        <div className="text-[10px] text-[color:var(--muted)] mt-3 leading-relaxed">
          HEIC preview isn&apos;t supported by this browser. Your photo uploads fine.
        </div>
        {badge ? <div className="absolute top-3 left-3">{badge}</div> : null}
      </div>
    );
  }

  return (
    <div className="relative">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        alt="Your photo"
        className="w-full max-h-[520px] object-cover rounded-xl border border-white/40"
        onError={() => setErrored(true)}
        src={src}
      />
      {badge ? <div className="absolute top-3 left-3">{badge}</div> : null}
    </div>
  );
}
