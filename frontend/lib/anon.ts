// Stable per-browser anonymous id so the backend can apply per-fingerprint
// quotas + retention TTLs without an account. Stored in localStorage; minted
// once on first try-on.

const KEY = "atelier.anon.v1";

export function readAnonId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY);
}

export function ensureAnonId(): string {
  if (typeof window === "undefined") {
    throw new Error("ensureAnonId called on the server");
  }
  let id = window.localStorage.getItem(KEY);
  if (!id) {
    id = `anon_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
    window.localStorage.setItem(KEY, id);
  }
  return id;
}
