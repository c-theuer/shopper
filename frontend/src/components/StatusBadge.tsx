import type { ItemStatus } from "../api";

const STYLES: Record<string, { label: string; cls: string }> = {
  ready: { label: "Ready", cls: "bg-sky-50 text-sky-800 ring-sky-200" },
  needs_clarification: { label: "Needs your answer", cls: "bg-amber-50 text-amber-900 ring-amber-300" },
  awaiting_approval: { label: "Awaiting approval", cls: "bg-violet-50 text-violet-800 ring-violet-200" },
  purchased: { label: "Purchased", cls: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  unavailable: { label: "Unavailable", cls: "bg-stone-100 text-stone-700 ring-stone-300" },
  blocked: { label: "Blocked", cls: "bg-red-50 text-red-800 ring-red-200" },
  removed: { label: "Removed", cls: "bg-stone-100 text-stone-600 ring-stone-200" },
  // approvals
  pending: { label: "Pending", cls: "bg-violet-50 text-violet-800 ring-violet-200" },
  approved: { label: "Approved", cls: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  used: { label: "Approved and ordered", cls: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  rejected: { label: "Rejected", cls: "bg-stone-100 text-stone-700 ring-stone-300" },
  expired: { label: "Expired", cls: "bg-stone-100 text-stone-700 ring-stone-300" },
  invalidated: { label: "No longer valid", cls: "bg-stone-100 text-stone-700 ring-stone-300" },
  // orders
  preparing: { label: "Preparing", cls: "bg-sky-50 text-sky-800 ring-sky-200" },
  out_for_delivery: { label: "Out for delivery", cls: "bg-amber-50 text-amber-900 ring-amber-300" },
  delivered: { label: "Delivered", cls: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  canceled: { label: "Canceled", cls: "bg-stone-100 text-stone-700 ring-stone-300" },
};

export function StatusBadge({ status }: { status: ItemStatus | string }) {
  const s = STYLES[status] ?? { label: status, cls: "bg-stone-100 text-stone-700 ring-stone-300" };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-medium ring-1 ring-inset ${s.cls}`}>
      {s.label}
    </span>
  );
}

export function SourceTag({ source }: { source: "ai" | "rules" }) {
  return source === "ai" ? (
    <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-xs font-semibold text-indigo-700" title="Decided with Claude">
      AI
    </span>
  ) : (
    <span className="rounded bg-stone-100 px-1.5 py-0.5 text-xs font-semibold text-stone-600" title="Decided by fixed rules">
      Rules
    </span>
  );
}
