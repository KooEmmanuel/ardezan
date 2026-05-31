"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

// Lightweight toast notification system.
//
// Usage:
//   const { toast } = useToast();
//   toast({ title: "Saved.", kind: "success" });
//   toast({ title: "Couldn't save.", description: err.message, kind: "error" });
//
// Toasts live in a portal-friendly fixed container, stack vertically,
// auto-dismiss after their duration, and clear themselves when the user
// clicks the × button.

export type ToastKind = "info" | "success" | "error" | "warning";

export type ToastInput = {
  title: string;
  description?: string;
  kind?: ToastKind;
  durationMs?: number;
};

type Toast = ToastInput & { id: string; kind: ToastKind; durationMs: number };

type ToastContextValue = {
  toast: (input: ToastInput) => void;
  dismiss: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_DURATION_MS = 5000;
const MAX_VISIBLE = 4;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timeoutsRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    const t = timeoutsRef.current.get(id);
    if (t) {
      clearTimeout(t);
      timeoutsRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((x) => x.id !== id));
  }, []);

  const toast = useCallback(
    (input: ToastInput) => {
      const id =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `t_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      const next: Toast = {
        id,
        title: input.title,
        description: input.description,
        kind: input.kind ?? "info",
        durationMs: input.durationMs ?? DEFAULT_DURATION_MS,
      };
      setToasts((prev) => {
        const overflow = Math.max(0, prev.length + 1 - MAX_VISIBLE);
        return [...prev.slice(overflow), next];
      });
      const timer = setTimeout(() => dismiss(id), next.durationMs);
      timeoutsRef.current.set(id, timer);
    },
    [dismiss],
  );

  useEffect(() => {
    const map = timeoutsRef.current;
    return () => {
      for (const t of map.values()) clearTimeout(t);
      map.clear();
    };
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ toast, dismiss }), [toast, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-label="Notifications"
        aria-live="polite"
        className="fixed z-[60] bottom-4 right-4 flex flex-col gap-2 max-w-[min(360px,calc(100vw-32px))]"
        role="region"
      >
        {toasts.map((t) => (
          <ToastCard key={t.id} onDismiss={() => dismiss(t.id)} toast={t} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const accent =
    toast.kind === "success"
      ? "#166534"
      : toast.kind === "error"
        ? "#8d1717"
        : toast.kind === "warning"
          ? "#a16207"
          : "#0a0a0b";

  return (
    <div
      className="card-solid p-3 sm:p-4 flex items-start gap-3"
      role={toast.kind === "error" ? "alert" : "status"}
      style={{ borderLeft: `3px solid ${accent}` }}
    >
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium" style={{ color: accent }}>
          {toast.title}
        </div>
        {toast.description ? (
          <div className="text-[12px] text-[color:var(--ink-soft)] mt-0.5 leading-snug">
            {toast.description}
          </div>
        ) : null}
      </div>
      <button
        aria-label="Dismiss notification"
        className="text-[color:var(--muted)] hover:text-[color:var(--ink)] text-lg leading-none"
        onClick={onDismiss}
        type="button"
      >
        ×
      </button>
    </div>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Soft fallback so calling toast() in tests or outside the provider
    // doesn't crash — logs to console instead.
    return {
      toast: ({ title, description, kind }) =>
        // eslint-disable-next-line no-console
        console.log(`[toast:${kind ?? "info"}]`, title, description ?? ""),
      dismiss: () => undefined,
    };
  }
  return ctx;
}
