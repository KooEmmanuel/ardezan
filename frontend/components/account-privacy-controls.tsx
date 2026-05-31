"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import { useToast } from "@/components/toast";
import { VerifyEmailBanner } from "@/components/verify-email-banner";
import { api, isEmailNotVerified } from "@/lib/api";
import type { BodyProfileStatus, SavedPhotoStatus } from "@/lib/types";

// Toggles for the two persistent-data opt-ins:
//   - Saved photo: keeps the most recent try-on upload so future try-ons
//     skip the upload step entirely.
//   - Body profile: snapshots the BodyProfile from a session onto the
//     customer doc so the recommender can use it next time without
//     re-analyzing the photo.
//
// Both opt-ins are sourced from a past Fitting Room session — we pick the
// most recent one. If the customer has no sessions yet, the controls
// gently say "do a try-on first".

export function AccountPrivacyControls() {
  const { toast } = useToast();
  const [photo, setPhoto] = useState<SavedPhotoStatus | null>(null);
  const [body, setBody] = useState<BodyProfileStatus | null>(null);
  const [latestSession, setLatestSession] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Set when saving a photo / body profile is blocked on email verification.
  const [needsVerify, setNeedsVerify] = useState(false);

  async function refresh() {
    try {
      const [p, b, fr] = await Promise.all([
        api.getSavedPhotoStatus(),
        api.getBodyProfileStatus(),
        api.listFittingRoom(),
      ]);
      setPhoto(p);
      setBody(b);
      setLatestSession(fr.items[0]?.try_on_session_id ?? null);
    } catch {
      // Toast-once on load failure
      toast({
        title: "Couldn't load privacy settings.",
        kind: "error",
      });
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function withBusy<T>(fn: () => Promise<T>, successTitle: string) {
    setBusy(true);
    try {
      await fn();
      setNeedsVerify(false);
      toast({ title: successTitle, kind: "success" });
      await refresh();
    } catch (err) {
      if (isEmailNotVerified(err)) {
        // Saving persistent data is gated behind email verification — surface
        // the inline banner instead of a generic error toast.
        setNeedsVerify(true);
      } else {
        toast({
          title: "Something went wrong.",
          description: err instanceof Error ? err.message : undefined,
          kind: "error",
        });
      }
    } finally {
      setBusy(false);
    }
  }

  async function onOptInPhoto() {
    if (!latestSession) {
      toast({
        title: "Do a try-on first.",
        description: "We use your most recent session's photo as the saved one.",
        kind: "info",
      });
      return;
    }
    await withBusy(
      () => api.optInSavedPhoto({ try_on_session_id: latestSession }),
      "Photo saved.",
    );
  }

  async function onDeletePhoto() {
    if (!confirm("Remove your saved photo? Future try-ons will need a fresh upload.")) return;
    await withBusy(() => api.deleteSavedPhoto(), "Saved photo removed.");
  }

  async function onOptInBody() {
    if (!latestSession) {
      toast({
        title: "Do a try-on first.",
        description: "We snapshot the body profile your latest analyzer produced.",
        kind: "info",
      });
      return;
    }
    await withBusy(
      () => api.optInBodyProfile({ try_on_session_id: latestSession }),
      "Body profile saved.",
    );
  }

  async function onDeleteBody() {
    if (!confirm("Forget your saved body profile?")) return;
    await withBusy(() => api.deleteBodyProfile(), "Body profile cleared.");
  }

  if (!photo || !body) {
    return (
      <div className="card-solid p-5 mb-3 text-sm text-[color:var(--muted)]">
        Loading privacy settings…
      </div>
    );
  }

  return (
    <>
      {needsVerify ? (
        <div className="mb-3">
          <VerifyEmailBanner />
        </div>
      ) : null}

      {/* Saved photo card */}
      <div className="card-solid p-5 mb-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
          Saved photo
        </div>
        <div className="flex items-start gap-4">
          {photo.has_photo && photo.photo_url ? (
            <div className="w-20 h-24 rounded-md overflow-hidden bg-[color:var(--ivory)] relative shrink-0">
              <Image
                alt="Saved photo"
                className="object-cover"
                fill
                sizes="80px"
                src={photo.photo_url}
              />
            </div>
          ) : null}
          <div className="flex-1 min-w-0">
            {photo.has_photo ? (
              <>
                <div className="text-sm" style={{ color: "#166534" }}>
                  Saved — used for future try-ons
                </div>
                {photo.photo_uploaded_at ? (
                  <div className="text-[12px] text-[color:var(--muted)]">
                    Uploaded {new Date(photo.photo_uploaded_at).toLocaleDateString()}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="text-sm text-[color:var(--muted)]">
                Not saved. Every try-on will ask you to upload.
              </div>
            )}
            <p className="text-[11px] text-[color:var(--muted)] mt-2 leading-snug">
              We only keep the photo from your latest session, and only if you opt in.
              You can remove it anytime — the file is wiped from our storage immediately.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {photo.has_photo ? (
                <button
                  className="btn-secondary text-xs"
                  disabled={busy}
                  onClick={onDeletePhoto}
                  type="button"
                >
                  Remove saved photo
                </button>
              ) : (
                <button
                  className="btn-primary text-xs"
                  disabled={busy || !latestSession}
                  onClick={onOptInPhoto}
                  type="button"
                >
                  Save my latest photo
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Body profile card */}
      <div className="card-solid p-5 mb-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] mb-2">
          Body profile
        </div>
        {body.opted_in ? (
          <>
            <div className="text-sm" style={{ color: "#166534" }}>
              On file
            </div>
            {body.updated_at ? (
              <div className="text-[12px] text-[color:var(--muted)]">
                Updated {new Date(body.updated_at).toLocaleDateString()}
              </div>
            ) : null}
            <p className="text-[11px] text-[color:var(--muted)] mt-2 leading-snug">
              Future try-ons can skip the analyzer step. Stored body shape,
              estimated measurements, and fit preference only.
            </p>
            <button
              className="btn-secondary text-xs mt-3"
              disabled={busy}
              onClick={onDeleteBody}
              type="button"
            >
              Forget my body profile
            </button>
          </>
        ) : (
          <>
            <div className="text-sm text-[color:var(--muted)]">
              Not saved. Every try-on re-analyzes your photo from scratch.
            </div>
            <p className="text-[11px] text-[color:var(--muted)] mt-2 leading-snug">
              Optional. Saves time + cost on future try-ons. You can clear it later.
            </p>
            <button
              className="btn-primary text-xs mt-3"
              disabled={busy || !latestSession}
              onClick={onOptInBody}
              type="button"
            >
              Save from my latest try-on
            </button>
          </>
        )}
      </div>
    </>
  );
}
