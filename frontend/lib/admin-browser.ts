// Browser-side admin API helpers — for use from ``"use client"``
// pages. Mirrors a subset of ``lib/admin-api.ts`` but uses plain
// ``fetch`` with ``credentials: "include"`` instead of forwarding
// cookies via ``next/headers``.
//
// Why split: ``lib/admin-api.ts`` is ``import "server-only"`` because
// it reads cookies from the request context. Importing it from a
// client component fails the Vercel build.

import { API_BASE_URL } from "@/lib/api";
import type {
  AdminCommerceConfig,
  AdminFabric,
  AdminFabricUpdate,
  AdminInspiration,
  AdminInspirationUpdate,
} from "@/lib/admin-types";

type Result<T> =
  | { kind: "ok"; data: T }
  | { kind: "unauth" }
  | { kind: "error"; status: number; message: string };

async function call<T>(path: string, init: RequestInit = {}): Promise<Result<T>> {
  try {
    const r = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        // Default to JSON unless the caller is sending FormData.
        ...(init.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...(init.headers ?? {}),
      },
      credentials: "include",
    });
    if (r.status === 401 || r.status === 403) return { kind: "unauth" };
    if (r.status === 204) return { kind: "ok", data: null as T };
    const text = await r.text();
    const body = text ? JSON.parse(text) : null;
    if (!r.ok) {
      const message: string =
        body?.error?.message ??
        body?.message ??
        `Request failed (${r.status})`;
      return { kind: "error", status: r.status, message };
    }
    return { kind: "ok", data: body as T };
  } catch (err) {
    return {
      kind: "error",
      status: 0,
      message: err instanceof Error ? err.message : "Network error",
    };
  }
}

export const adminBrowser = {
  // ── Fabrics ───────────────────────────────────────────────
  listFabrics: () => call<{ items: AdminFabric[] }>("/api/v1/admin/fabrics"),

  getFabric: (id: string) =>
    call<AdminFabric>(`/api/v1/admin/fabrics/${encodeURIComponent(id)}`),

  patchFabric: (id: string, body: AdminFabricUpdate) =>
    call<AdminFabric>(`/api/v1/admin/fabrics/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteFabric: (id: string) =>
    call<null>(`/api/v1/admin/fabrics/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  // ── Inspirations ──────────────────────────────────────────
  listInspirations: () =>
    call<{ items: AdminInspiration[] }>("/api/v1/admin/inspirations"),

  getInspiration: (id: string) =>
    call<AdminInspiration>(
      `/api/v1/admin/inspirations/${encodeURIComponent(id)}`,
    ),

  patchInspiration: (id: string, body: AdminInspirationUpdate) =>
    call<AdminInspiration>(
      `/api/v1/admin/inspirations/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  deleteInspiration: (id: string) =>
    call<null>(`/api/v1/admin/inspirations/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  // ── Commerce ──────────────────────────────────────────────
  getCommerceConfig: () =>
    call<AdminCommerceConfig>("/api/v1/admin/commerce"),

  patchCommerceConfig: (body: Partial<AdminCommerceConfig>) =>
    call<AdminCommerceConfig>("/api/v1/admin/commerce", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};
