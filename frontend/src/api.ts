export type ItemStatus =
  | "ready"
  | "needs_clarification"
  | "awaiting_approval"
  | "purchased"
  | "unavailable"
  | "blocked"
  | "removed";

export interface Item {
  id: number;
  name: string;
  category: string;
  quantity: number;
  brand: string | null;
  color: string | null;
  size: string | null;
  max_price: string | null;
  substitution: "allow" | "prohibit" | "approval";
  priority: "high" | "normal" | "low";
  needed_by: string | null;
  recurrence: "once" | "weekly";
  notes: string;
  status: ItemStatus;
  status_reason: string;
  clarification_question: string;
  deferred_until: string | null;
  version: number;
  updated_at: string;
}

export interface Reason {
  code: string;
  layer: "platform" | "user";
  effect: string;
  message: string;
}

export interface Quote {
  subtotal: string;
  tax: string;
  delivery_fee: string;
  service_fee: string;
  total: string;
}

export interface Approval {
  id: number;
  status: string;
  status_reason: string;
  store: string;
  store_address: string;
  distance_mi: number;
  lines: {
    item_id: number;
    item: string;
    product: string;
    brand: string;
    color: string | null;
    size: string | null;
    quantity: number;
    unit_price: string;
    is_substitution: boolean;
    mismatches: string[];
  }[];
  quote: Quote;
  reasons: Reason[];
  alternatives: { item: string; product: string; color: string | null; store: string; price: string; distance_mi: number }[];
  budget: { week_spent: string; weekly_budget: string; after: string; remaining_after: string };
  created_at: string;
  expires_at: string;
  decided_at: string | null;
}

export interface Order extends Quote {
  id: number;
  store: string;
  store_address: string;
  distance_mi: number;
  status: "placed" | "canceled";
  delivery_status: "preparing" | "out_for_delivery" | "delivered" | "canceled";
  card: string;
  approval_id: number | null;
  committed_at: string;
  lines: { item_id: number; item: string; product: string; brand: string; color: string | null; size: string | null; quantity: number; unit_price: string }[];
}

export interface Activity {
  id: number;
  kind: string;
  message: string;
  details: { reasons?: Reason[]; quote?: Quote; mismatches?: string[] };
  source: "ai" | "rules";
  item_id: number | null;
  at: string;
}

export interface Notification {
  id: number;
  kind: "daily_summary" | "purchase" | "approval" | "low_balance";
  channel: "email" | "sms";
  to: string;
  subject: string;
  body: Record<string, any>;
  at: string;
}

export interface Settings {
  location_label: string;
  lat: number;
  lng: number;
  timezone: string;
  weekly_budget: string;
  order_limit: string;
  max_delivery_fee: string;
  substitution_default: "allow" | "prohibit" | "approval";
  always_approve_categories: string[];
  permitted_days: number[];
  notify_channel: "email" | "sms";
  notify_contact: string;
  purchase_notifications: boolean;
  paused: boolean;
  payment_method: "card" | "wallet";
  wallet_balance: string;
  bank: { bank_name: string; last4: string } | null;
  card: { brand: string; last4: string; exp_month: number; exp_year: number; name: string } | null;
  setup_complete: boolean;
  platform_rules: string[];
  agent_mode: "ai" | "rules";
}

export interface WalletEntry {
  id: number;
  kind: "deposit" | "purchase" | "refund";
  amount: string;
  order_id: number | null;
  memo: string;
  at: string;
}

export interface Wallet {
  balance: string;
  bank: { bank_name: string; last4: string; holder_name: string } | null;
  entries: WalletEntry[];
}

export interface Clock {
  now: string;
  frozen: boolean;
  in_window: boolean;
  timezone: string;
}

export interface RunResult {
  placed: number[];
  approvals: number[];
  blocked: number;
  deferred: number;
  unavailable: number;
  note: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: any,
  ) {
    super(typeof detail === "string" ? detail : (detail?.message ?? `Request failed (${status})`));
  }
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: init?.method ?? "GET",
    headers: init?.body !== undefined ? { "content-type": "application/json" } : undefined,
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    // FastAPI validation errors arrive as a list.
    if (Array.isArray(detail)) throw new ApiError(res.status, detail.map((d) => d.msg).join(" "));
    throw new ApiError(res.status, detail ?? res.statusText);
  }
  return data as T;
}

export const REFRESH_EVENT = "shopper:refresh";

/** Tell every mounted view to refetch now (after a mutation). */
export function refreshAll() {
  window.dispatchEvent(new Event(REFRESH_EVENT));
}
