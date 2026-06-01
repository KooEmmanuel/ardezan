// Pure type definitions shared between server-only admin helpers
// (``lib/admin-api.ts``) and client-side admin helpers
// (``lib/admin-browser.ts``). Has no runtime code and no
// ``server-only`` import, so it's safe in client components.

export type AdminFabric = {
  fabric_id: string;
  name: string;
  description: string;
  color_family: string;
  cost_per_yard_amount: number;
  currency: string;
  suitable_for: string[];
  swatch: { gradient: string | null; image_url: string | null };
  weight: "light" | "medium" | "heavy";
  finish: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminFabricUpdate = {
  name?: string;
  description?: string;
  color_family?: string;
  cost_per_yard_amount?: number;
  suitable_for?: string[];
  weight?: "light" | "medium" | "heavy";
  finish?: string | null;
  gradient?: string | null;
  active?: boolean;
};

export type AdminInspiration = {
  inspiration_id: string;
  fabric_id: string;
  piece_type: string;
  complexity: "simple" | "standard" | "intricate";
  title: string;
  tagline: string;
  brief: string;
  fit_note: string | null;
  image_url: string | null;
  gradient: string | null;
  active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type AdminInspirationUpdate = {
  fabric_id?: string;
  piece_type?: string;
  complexity?: "simple" | "standard" | "intricate";
  title?: string;
  tagline?: string;
  brief?: string;
  fit_note?: string | null;
  gradient?: string | null;
  active?: boolean;
  sort_order?: number;
};

export type AdminCommerceConfig = {
  yardage_by_piece: Record<string, number>;
  base_tailoring_by_piece: Record<string, number>;
  complexity_multiplier: Record<string, number>;
  shipping: {
    standard_cents: number;
    express_cents: number;
    international_cents: number;
  };
};
