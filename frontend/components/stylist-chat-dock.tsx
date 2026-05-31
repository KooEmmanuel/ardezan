"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useToast } from "@/components/toast";
import { api } from "@/lib/api";

/**
 * Floating chat dock that lives fixed at the bottom of the try-on results
 * page. Talks to the Stylist ADK agent via the existing refine endpoint.
 *
 * Three things make this nicer than the previous inline form:
 *   - It's pinned to the viewport, not the layout, so it stays reachable
 *     while the user scrolls outfits.
 *   - It surfaces the stylist agent's narrative summary (passed in via
 *     ``agentNote``) as a small chat bubble above the input, so the user
 *     sees the AI's reasoning, not just the result cards.
 *   - It collapses to a minimized pill when not in use so it doesn't
 *     occlude the bottom rows of the outfit grid.
 */
export function StylistChatDock({
  sessionId,
  agentNote,
  thinking = false,
}: {
  sessionId: string | null;
  agentNote?: string | null;
  thinking?: boolean;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [showNote, setShowNote] = useState(false);
  const seenNoteRef = useRef<string | null>(null);

  // When a fresh agent note arrives, briefly auto-reveal so the user
  // sees the stylist's reasoning even if they had collapsed the dock.
  useEffect(() => {
    if (!agentNote) return;
    if (seenNoteRef.current === agentNote) return;
    seenNoteRef.current = agentNote;
    setShowNote(true);
    setCollapsed(false);
  }, [agentNote]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!sessionId) return;
    const text = prompt.trim();
    if (text.length < 2) return;
    setSubmitting(true);
    try {
      const created = await api.refineTryOnSession(sessionId, text);
      router.push(`/try-on/jobs/${created.job_id}?session=${created.try_on_session_id}`);
    } catch (err) {
      toast({
        title: "Couldn't refine.",
        description:
          err instanceof Error ? err.message : "Try again in a moment.",
        kind: "error",
      });
      setSubmitting(false);
    }
  }

  if (!sessionId) return null;

  // Collapsed pill — small launcher near bottom-right.
  if (collapsed) {
    return (
      <button
        aria-label="Open stylist chat"
        className="fixed bottom-5 left-1/2 -translate-x-1/2 z-30 inline-flex items-center gap-2 h-10 px-4 rounded-full bg-[color:var(--ink)] text-[color:var(--paper)] shadow-lg hover:opacity-90 transition-opacity"
        onClick={() => setCollapsed(false)}
        type="button"
      >
        <SparkleIcon />
        <span className="text-[13px] font-medium">Refine with stylist</span>
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-30 w-[min(720px,calc(100vw-1.5rem))] pointer-events-none">
      <div className="relative pointer-events-auto">
        {/* Agent note — slides up above the dock */}
        {showNote && agentNote ? (
          <div className="mb-2 mx-2 sm:mx-0 reveal">
            <div className="relative rounded-2xl bg-white/95 backdrop-blur-md border border-[color:var(--line)] shadow-lg px-4 py-3 pr-9">
              <div className="flex items-start gap-2.5">
                <div className="shrink-0 h-7 w-7 rounded-full bg-[color:var(--ink)] text-[color:var(--paper)] flex items-center justify-center">
                  <SparkleIcon />
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--muted)] mb-0.5">
                    Stylist
                  </div>
                  <p className="text-[13px] leading-relaxed text-[color:var(--ink-soft)]">
                    {agentNote}
                  </p>
                </div>
              </div>
              <button
                aria-label="Dismiss note"
                className="absolute top-2.5 right-2.5 h-6 w-6 rounded-md text-[color:var(--muted)] hover:bg-[color:var(--ivory)] inline-flex items-center justify-center"
                onClick={() => setShowNote(false)}
                type="button"
              >
                <svg fill="none" height="12" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="12">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            </div>
          </div>
        ) : null}

        {/* Composer */}
        <form
          className="rounded-2xl bg-white/95 backdrop-blur-md border border-[color:var(--line)] shadow-xl px-2.5 py-2 flex items-center gap-2"
          onSubmit={onSubmit}
        >
          <div className="shrink-0 h-8 w-8 rounded-full bg-[color:var(--ivory)] text-[color:var(--ink-soft)] flex items-center justify-center">
            <SparkleIcon />
          </div>
          <input
            aria-label="Refine your try-on"
            className="flex-1 min-w-0 bg-transparent text-[14px] placeholder:text-[color:var(--muted)] focus:outline-none px-1 py-2"
            disabled={submitting || thinking}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={
              thinking
                ? "Stylist is thinking…"
                : "Refine — e.g. 'warmer pieces' or 'swap the trousers'"
            }
            value={prompt}
          />
          {showNote && agentNote ? (
            <button
              aria-label="Hide stylist note"
              className="hidden sm:inline-flex h-8 w-8 rounded-md text-[color:var(--muted)] hover:bg-[color:var(--ivory)] items-center justify-center"
              onClick={() => setShowNote(false)}
              type="button"
            >
              <svg fill="none" height="14" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="14">
                <path d="m18 15-6-6-6 6" />
              </svg>
            </button>
          ) : null}
          <button
            aria-label="Minimize"
            className="h-8 w-8 rounded-md text-[color:var(--muted)] hover:bg-[color:var(--ivory)] inline-flex items-center justify-center"
            onClick={() => setCollapsed(true)}
            type="button"
          >
            <svg fill="none" height="14" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="14">
              <path d="M5 12h14" />
            </svg>
          </button>
          <button
            className="shrink-0 inline-flex items-center justify-center h-9 w-9 rounded-full bg-[color:var(--ink)] text-[color:var(--paper)] disabled:opacity-30 disabled:cursor-not-allowed"
            disabled={submitting || thinking || prompt.trim().length < 2}
            type="submit"
          >
            {submitting ? <Spinner /> : <ArrowUpIcon />}
          </button>
        </form>

        {/* Tiny attribution */}
        <div className="text-center mt-1.5 text-[10px] text-[color:var(--ink-soft)]/70">
          Powered by the Ardezan Stylist agent · Gemini + Google ADK
        </div>
      </div>
    </div>
  );
}

function SparkleIcon() {
  return (
    <svg
      aria-hidden
      fill="currentColor"
      height="14"
      viewBox="0 0 24 24"
      width="14"
    >
      <path d="M12 3 L13.5 9 L20 10.5 L13.5 12 L12 18 L10.5 12 L4 10.5 L10.5 9 Z" />
    </svg>
  );
}

function ArrowUpIcon() {
  return (
    <svg
      aria-hidden
      fill="none"
      height="14"
      stroke="currentColor"
      strokeWidth="2.5"
      viewBox="0 0 24 24"
      width="14"
    >
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg
      aria-hidden
      className="animate-spin"
      fill="none"
      height="14"
      stroke="currentColor"
      strokeWidth="2.5"
      viewBox="0 0 24 24"
      width="14"
    >
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  );
}
