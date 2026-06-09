// Guard against open redirects: ?next= must be a same-origin path.
// Rejects absolute URLs ("https://…"), protocol-relative ("//evil.com"),
// and backslash tricks ("/\evil.com").
export function safeNextPath(raw: string | null, fallback: string): string {
  if (!raw) return fallback;
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) {
    return fallback;
  }
  return raw;
}
