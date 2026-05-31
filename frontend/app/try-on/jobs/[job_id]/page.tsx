"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ErrorCard } from "@/components/error-card";
import { StylistChatDock } from "@/components/stylist-chat-dock";
import { TryOnResultGrid } from "@/components/try-on-result-grid";
import { TryOnStageRail } from "@/components/try-on-stage-rail";
import { API_BASE_URL, api } from "@/lib/api";
import type { ResultCard, TryOnEvent } from "@/lib/types";

type StageId =
  | "validating_upload"
  | "analyzing_photo"
  | "building_catalog_context"
  | "recommending_outfits"
  | "generating_images"
  | "completed"
  | "failed";

const TERMINAL_TYPES = new Set([
  "job.completed",
  "job.completed_partial",
  "job.failed",
  "job.cancelled",
  "job.expired",
]);

export default function TryOnJobPage() {
  return (
    <Suspense fallback={null}>
      <TryOnJobInner />
    </Suspense>
  );
}

function TryOnJobInner() {
  const params = useParams<{ job_id: string }>();
  const search = useSearchParams();
  const sessionIdFromQuery = search.get("session");

  const [stage, setStage] = useState<StageId>("validating_upload");
  const [agentNote, setAgentNote] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("Try-on starting…");
  const [terminal, setTerminal] = useState<null | "completed" | "completed_partial" | "failed">(null);
  const [error, setError] = useState<string | null>(null);
  const [cards, setCards] = useState<ResultCard[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(sessionIdFromQuery);
  const [imageByCardId, setImageByCardId] = useState<Record<string, string>>({});
  const [unavailable, setUnavailable] = useState(false);
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const anyEventReceivedRef = useRef(false);

  const fetchSession = useCallback(async (sid: string) => {
    try {
      const detail = await api.getTryOnSession(sid);
      setCards(detail.result_cards);
    } catch (err) {
      console.warn("session-fetch", err);
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    void fetchSession(sessionId);
  }, [sessionId, fetchSession]);

  useEffect(() => {
    const url = `${API_BASE_URL}/api/v1/try-on/jobs/${params.job_id}/events`;
    const source = new EventSource(url, { withCredentials: true });
    const seen = seenEventIdsRef.current;

    function applyEvent(event: TryOnEvent) {
      if (event.stage) {
        const known: StageId[] = [
          "validating_upload",
          "analyzing_photo",
          "building_catalog_context",
          "recommending_outfits",
          "generating_images",
          "completed",
          "failed",
        ];
        if (known.includes(event.stage as StageId)) setStage(event.stage as StageId);
      }
      if (typeof event.progress_percent === "number") setProgress(event.progress_percent);
      if (event.message) setStatusMessage(event.message);

      switch (event.type) {
        case "agent.summary": {
          // The ADK Stylist agent's narrative — show it in the floating dock.
          const summary = String(
            (event.payload as Record<string, unknown> | undefined)?.summary ??
              event.message ??
              "",
          );
          if (summary) setAgentNote(summary);
          break;
        }
        case "recommender.completed":
          if (sessionId) void fetchSession(sessionId);
          break;
        case "designer.image_completed": {
          const cardId = String(event.payload?.card_id ?? "");
          const url = String(event.payload?.image_url ?? "");
          if (cardId && url) setImageByCardId((prev) => ({ ...prev, [cardId]: url }));
          break;
        }
        case "job.completed":
          setTerminal("completed");
          if (sessionId) void fetchSession(sessionId);
          source.close();
          break;
        case "job.completed_partial":
          setTerminal("completed_partial");
          if (sessionId) void fetchSession(sessionId);
          source.close();
          break;
        case "job.failed":
        case "job.cancelled":
        case "job.expired":
          setTerminal("failed");
          setError(event.message || "Try-on failed.");
          source.close();
          break;
      }
      if (TERMINAL_TYPES.has(event.type)) {
        seenEventIdsRef.current = new Set();
      }
    }

    function handle(ev: MessageEvent, fallbackType: string) {
      if (ev.lastEventId && seen.has(ev.lastEventId)) return;
      if (ev.lastEventId) seen.add(ev.lastEventId);
      anyEventReceivedRef.current = true;
      try {
        const data = { ...(JSON.parse(ev.data) as Omit<TryOnEvent, "type">), type: fallbackType };
        applyEvent(data);
      } catch {
        // ignore unparseable
      }
    }

    // If the EventSource fails to connect at all (404 / 401 on the SSE
    // endpoint), no events ever arrive. Treat that as "unavailable" rather
    // than letting the UI sit on the loading shimmer forever.
    source.onerror = () => {
      if (anyEventReceivedRef.current) return;
      if (source.readyState === EventSource.CLOSED) {
        setUnavailable(true);
      }
    };

    const named = [
      "job.created", "validator.completed", "analyzer.started", "analyzer.completed",
      "context.building", "context.completed", "recommender.started", "recommender.completed",
      "agent.started", "agent.summary", "agent.failed", "agent.empty",
      "designer.image_started", "designer.image_completed", "designer.image_failed",
      "designer.skipped", "job.completed", "job.completed_partial", "job.failed",
      "job.cancelled", "job.expired", "error",
    ];
    const listeners: { name: string; fn: (ev: MessageEvent) => void }[] = [];
    for (const name of named) {
      const fn = (ev: MessageEvent) => handle(ev, name);
      source.addEventListener(name, fn as EventListener);
      listeners.push({ name, fn });
    }
    source.addEventListener("message", (ev) => handle(ev, "message"));

    return () => {
      for (const { name, fn } of listeners) {
        source.removeEventListener(name, fn as EventListener);
      }
      source.close();
    };
  }, [params.job_id, sessionId, fetchSession]);

  useEffect(() => {
    if (sessionId) return;
    api.getTryOnJob(params.job_id)
      .then((job) => {
        if (job.try_on_session_id) setSessionId(job.try_on_session_id);
      })
      .catch((err) => {
        // 404 (expired or never existed) or 401 (someone else's job) —
        // surface a friendly "unavailable" card instead of leaving the
        // shimmer hanging or letting the rejection bubble up.
        const message = err instanceof Error ? err.message : String(err);
        if (
          /404|not[\s_-]?found|expired|forbidden|401|403/i.test(message)
        ) {
          setUnavailable(true);
        }
      });
  }, [params.job_id, sessionId]);

  const mergedCards = useMemo<ResultCard[]>(() => {
    if (cards.length === 0) return [];
    return cards.map((card) => ({
      ...card,
      // Prefer the freshly-signed URL from the session fetch over the
      // SSE live-push URL. They were equal at generation time, but the
      // SSE one expires (signed URLs are valid for ~1h) and stale
      // payloads replay on reconnect, breaking the image on revisits.
      // Only fall back to the live-push URL while the card has no
      // persisted image yet (mid-generation).
      image_url: card.image_url ?? imageByCardId[card.card_id] ?? null,
    }));
  }, [cards, imageByCardId]);

  const headlineEyebrow =
    unavailable
      ? "Session unavailable"
      : terminal === "completed"
        ? "Styled for you"
        : terminal === "completed_partial"
          ? "Looks ready"
          : terminal === "failed"
            ? "Try-on failed"
            : "Styling in progress";

  return (
    <section className="ai-canvas">
      <div className="max-w-[1280px] mx-auto px-5 py-10">
        <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-4 mb-6">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ink-soft)] mb-1">
              {headlineEyebrow}
            </div>
            <h1 className="font-display text-4xl sm:text-5xl leading-[1.02]">
              {unavailable
                ? "This try-on isn't available anymore."
                : terminal === "completed" || terminal === "completed_partial"
                  ? "Pick the look that lands."
                  : terminal === "failed"
                    ? "Let's try that again."
                    : statusMessage}
            </h1>
          </div>
          <Link className="sm:ml-auto btn-ghost underline underline-offset-4 text-sm" href="/try-on">
            Start over
          </Link>
        </div>

        {!unavailable ? (
          <TryOnStageRail current={stage} progress={progress} terminal={terminal} />
        ) : null}

        {unavailable ? (
          <ErrorCard
            cta={{ label: "Start a new try-on", href: "/try-on" }}
            message="This try-on session may have expired (we keep generated images for 24 hours) or the link may have been opened in a different browser session. Start a new one — your photo stays on your device."
            title="We couldn't find this try-on."
          />
        ) : null}

        {unavailable ? null : terminal === "failed" ? (
          <ErrorCard
            cta={{ label: "Try another photo", href: "/try-on" }}
            message={error ?? "Something went wrong on our side."}
            title="We couldn't finish your try-on."
          />
        ) : (
          <TryOnResultGrid
            cards={mergedCards}
            loading={!terminal && cards.length === 0}
            sessionId={sessionId}
          />
        )}

        <div className="text-xs text-[color:var(--ink-soft)] mt-6 text-center max-w-xl mx-auto pb-28">
          AI preview — generated images approximate fit, drape, and color. Actual garment may vary.
        </div>
      </div>

      {/* Floating Stylist chat dock — appears once results are ready. */}
      {!unavailable && (terminal === "completed" || terminal === "completed_partial") ? (
        <StylistChatDock
          agentNote={agentNote}
          sessionId={sessionId}
          thinking={false}
        />
      ) : null}
    </section>
  );
}
