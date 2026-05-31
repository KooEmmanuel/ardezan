"use client";

import { useState } from "react";

import { api } from "@/lib/api";

// Shown when a logged-in customer hits an action gated behind email
// verification (checkout, saving a photo / body profile). Offers a one-click
// resend of the verification email, plus an optional "I've verified — retry"
// action so the customer can continue without a full page reload.
export function VerifyEmailBanner({
  email,
  onRetry,
  retryLabel = "I've verified — try again",
}: {
  email?: string | null;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

  async function resend() {
    setState("sending");
    setError(null);
    try {
      await api.requestEmailVerification();
      setState("sent");
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "Couldn't send the email.");
    }
  }

  return (
    <div
      className="rounded-lg border p-4"
      role="alert"
      style={{
        background: "#fff7e6",
        borderColor: "#f0d8a0",
        color: "#7a4e00",
      }}
    >
      <div className="font-display text-[15px] mb-1">
        Verify your email to continue
      </div>
      <p className="text-[13px] leading-relaxed">
        For your security, confirm your email before you place an order or save
        a photo.
        {email ? (
          <>
            {" "}
            We sent a link to <span className="font-medium">{email}</span>.
          </>
        ) : (
          " Check your inbox for the verification link."
        )}
      </p>

      {state === "sent" ? (
        <p className="text-[13px] mt-2 font-medium" style={{ color: "#166534" }}>
          Sent. Open the link in your inbox, then continue.
        </p>
      ) : null}
      {state === "error" && error ? (
        <p className="text-[13px] mt-2" style={{ color: "#8d1717" }}>
          {error}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          className="btn-secondary text-xs"
          disabled={state === "sending"}
          onClick={resend}
          type="button"
        >
          {state === "sending"
            ? "Sending…"
            : state === "sent"
              ? "Resend link"
              : "Resend verification email"}
        </button>
        {onRetry ? (
          <button
            className="btn-primary text-xs"
            onClick={onRetry}
            type="button"
          >
            {retryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
