import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, refreshAll, type Approval, type Clock, type RunResult } from "../api";
import { useResource, useSettings } from "../hooks";
import { dateTime, money } from "../format";
import { StatusBadge } from "../components/StatusBadge";

export function Approvals() {
  const { data } = useResource<Approval[]>("/approvals");
  const pending = data?.filter((a) => a.status === "pending") ?? [];
  const past = data?.filter((a) => a.status !== "pending") ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Approvals</h1>
        <p className="text-muted">
          The assistant asks before buying anything outside your preferences. If you don't answer, nothing is bought.
        </p>
      </header>
      {data && pending.length === 0 && <p className="card text-muted">Nothing needs your approval right now.</p>}
      <div className="space-y-4">
        {pending.map((a) => (
          <ApprovalCard key={a.id} a={a} />
        ))}
      </div>
      {past.length > 0 && (
        <section>
          <h2 className="mb-2 text-lg font-semibold">Earlier requests</h2>
          <ul className="divide-y divide-line rounded-xl border border-line bg-white">
            {past.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                <div>
                  <p className="font-medium">
                    #{a.id} · {a.lines.map((l) => l.item).join(", ")} at {a.store} · {money(a.quote.total)}
                  </p>
                  {a.status_reason && <p className="text-sm text-muted">{a.status_reason}</p>}
                </div>
                <StatusBadge status={a.status} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function useCountdown(iso: string, nowIso?: string) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => tick((n) => n + 1), 30000);
    return () => window.clearInterval(id);
  }, []);
  const ms = new Date(iso).getTime() - new Date(nowIso ?? Date.now()).getTime();
  if (ms <= 0) return "expired";
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return h ? `${h} hr ${m} min` : `${m} min`;
}

function ApprovalCard({ a }: { a: Approval }) {
  const settings = useSettings();
  const { data: clock } = useResource<Clock>("/clock", 10000);
  const left = useCountdown(a.expires_at, clock?.now);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function decide(action: "approve" | "reject") {
    setBusy(true);
    setMessage("");
    try {
      const res = await api<{ approval: Approval; run: RunResult } | Approval>(`/approvals/${a.id}/${action}`, { method: "POST" });
      if (action === "approve" && "run" in res && !res.run.placed.length) {
        setMessage(res.run.note || "Approved. The assistant will place this order in the next shopping window.");
      }
      refreshAll();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const platform = a.reasons.filter((r) => r.layer === "platform");
  const user = a.reasons.filter((r) => r.layer === "user");

  return (
    <article className="card border-violet-200" aria-labelledby={`appr-${a.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-violet-700">Approval request #{a.id}</p>
          <h2 id={`appr-${a.id}`} className="text-xl font-bold">
            Buy {a.lines.map((l) => l.item.toLowerCase()).join(", ")} for {money(a.quote.total)}?
          </h2>
          <p className="text-muted">
            {a.store}, {a.store_address} · {a.distance_mi} mi away
          </p>
        </div>
        <p className="rounded-lg bg-violet-50 px-3 py-1.5 text-sm text-violet-900">
          Expires in <strong>{left}</strong>
          <span className="block text-xs">{dateTime(a.expires_at, settings?.timezone)}</span>
        </p>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-1 font-semibold">What will be bought</h3>
          <ul className="space-y-1">
            {a.lines.map((l) => (
              <li key={l.item_id} className="flex justify-between gap-3">
                <span>
                  {l.quantity} × {l.product}
                  {l.color && <span className="text-muted"> ({l.color})</span>}
                  {l.is_substitution && <span className="ml-1 rounded bg-amber-100 px-1 text-xs">substitute</span>}
                </span>
                <span className="tabular-nums">{money(Number(l.unit_price) * l.quantity)}</span>
              </li>
            ))}
          </ul>
          <dl className="mt-2 space-y-0.5 border-t border-line pt-2 text-sm text-muted">
            <Row label="Tax" value={a.quote.tax} />
            <Row label="Delivery" value={a.quote.delivery_fee} />
            <Row label="Service fee" value={a.quote.service_fee} />
            <div className="flex justify-between pt-1 text-base font-semibold text-ink">
              <dt>Total</dt>
              <dd className="tabular-nums">{money(a.quote.total)}</dd>
            </div>
          </dl>
        </div>
        <div className="space-y-3">
          <div>
            <h3 className="mb-1 font-semibold">Why you're being asked</h3>
            <ul className="list-disc space-y-1 pl-5">
              {[...user, ...platform].map((r) => (
                <li key={r.code + r.message}>
                  {r.message}
                  {r.layer === "platform" && <span className="text-sm text-muted"> (always required)</span>}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-lg bg-canvas p-3 text-sm">
            <p className="font-medium">Effect on your weekly budget</p>
            <p>
              {money(a.budget.week_spent)} spent → <strong>{money(a.budget.after)}</strong> of{" "}
              {money(a.budget.weekly_budget)} ({money(a.budget.remaining_after)} left)
            </p>
          </div>
          {a.alternatives.length > 0 && (
            <div>
              <h3 className="mb-1 font-semibold">Other options nearby</h3>
              <ul className="text-sm">
                {a.alternatives.map((alt, i) => (
                  <li key={i}>
                    {alt.product}
                    {alt.color ? ` (${alt.color})` : ""} at {alt.store}, {alt.distance_mi} mi · {money(alt.price)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4">
        <button className="btn-primary" disabled={busy} onClick={() => decide("approve")}>
          {busy ? "Working…" : "Approve once"}
        </button>
        <button className="btn-secondary" disabled={busy} onClick={() => decide("reject")}>
          Reject
        </button>
        <Link to="/list" className="btn-secondary">Edit item</Link>
        <Link to="/settings" className="btn-secondary">Update preferences</Link>
        <p className="w-full text-sm text-muted">
          Approving applies only to this exact order. It doesn't change your settings, and every platform rule is
          checked again right before ordering.
        </p>
        {message && <p className="w-full font-medium" role="status">{message}</p>}
      </div>
    </article>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt>{label}</dt>
      <dd className="tabular-nums">{money(value)}</dd>
    </div>
  );
}
