import { useState } from "react";
import { Link } from "react-router";
import { type Notification } from "../api";
import { useResource, useSettings } from "../hooks";
import { dateTime, money } from "../format";

const KIND_LABELS: Record<Notification["kind"], string> = {
  daily_summary: "Daily summary",
  approval: "Approval request",
  purchase: "Purchase",
  low_balance: "Add funds",
};

export function Inbox() {
  const { data } = useResource<Notification[]>("/notifications");
  const settings = useSettings();
  const [openId, setOpenId] = useState<number | null>(null);
  const open = data?.find((n) => n.id === openId) ?? data?.[0];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Inbox</h1>
        <p className="text-muted">
          Messages the assistant would send by {settings?.notify_channel === "sms" ? "text message" : "email"} to{" "}
          {settings?.notify_contact || "you"}. In this demo nothing is actually sent.
        </p>
      </header>
      {data?.length === 0 && <p className="card text-muted">No messages yet.</p>}
      {open && (
        <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
          <ul className="space-y-1" aria-label="Messages">
            {data!.map((n) => (
              <li key={n.id}>
                <button
                  onClick={() => setOpenId(n.id)}
                  aria-current={open.id === n.id}
                  className={`w-full rounded-lg px-3 py-2 text-left ${open.id === n.id ? "bg-white ring-2 ring-brand" : "hover:bg-white"}`}
                >
                  <span className="block text-xs uppercase tracking-wide text-muted">
                    {KIND_LABELS[n.kind]} ·{" "}
                    {n.channel}
                  </span>
                  <span className="block font-medium">{n.subject}</span>
                  <span className="block text-xs text-muted">{dateTime(n.at, settings?.timezone)}</span>
                </button>
              </li>
            ))}
          </ul>
          <Message n={open} tz={settings?.timezone} />
        </div>
      )}
    </div>
  );
}

function Message({ n, tz }: { n: Notification; tz?: string }) {
  const b = n.body;
  return (
    <article className={`card ${n.channel === "sms" ? "max-w-md rounded-3xl" : ""}`}>
      <p className="text-sm text-muted">
        To: {n.to} · {dateTime(n.at, tz)}
      </p>
      <h2 className="mt-1 text-xl font-bold">{n.subject}</h2>
      <div className="mt-4 space-y-4">
        {n.kind === "daily_summary" && <Summary b={b} />}
        {n.kind === "purchase" && (
          <div>
            <p>Your assistant placed order #{b.order_id} at {b.store}:</p>
            <Lines lines={b.lines} />
            <p className="mt-2 font-semibold">
              Total {money(b.total)} charged to {b.card}
            </p>
          </div>
        )}
        {n.kind === "low_balance" && (
          <div>
            <p>
              The assistant is ready to buy {b.items.join(", ")} for {money(b.needed)}, but your wallet only has{" "}
              {money(b.balance)}.
            </p>
            <Link to="/wallet" className="btn-primary mt-3">Add funds</Link>
            <p className="mt-2 text-sm text-muted">The order will go through on the next run after you add funds.</p>
          </div>
        )}
        {n.kind === "approval" && (
          <div>
            <p>
              The assistant wants to buy {b.items.join(", ")} at {b.store} for {money(b.quote.total)}, and needs your
              OK first:
            </p>
            <ul className="mt-2 list-disc pl-5">
              {b.reasons.map((r: string, i: number) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
            <Link to="/approvals" className="btn-primary mt-3">Review in the app</Link>
            <p className="mt-2 text-sm text-muted">If you don't respond, nothing is bought.</p>
          </div>
        )}
      </div>
    </article>
  );
}

function Lines({ lines }: { lines: { name: string; item: string; quantity: number; unit_price: string }[] }) {
  return (
    <ul className="mt-1 list-disc pl-5">
      {lines.map((l, i) => (
        <li key={i}>
          {l.quantity} × {l.name} <span className="text-muted">({money(Number(l.unit_price) * l.quantity)})</span>
        </li>
      ))}
    </ul>
  );
}

function Summary({ b }: { b: Record<string, any> }) {
  const section = (title: string, rows: { name: string; reason: string }[]) =>
    rows.length > 0 && (
      <section>
        <h3 className="font-semibold">{title}</h3>
        <ul className="list-disc pl-5">
          {rows.map((r, i) => (
            <li key={i}>
              {r.name}
              {r.reason && <span className="text-muted">: {r.reason}</span>}
            </li>
          ))}
        </ul>
      </section>
    );
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Spent today" value={money(b.day_total)} />
        <Stat label="Spent this week" value={money(b.week_spent)} />
        <Stat label="Left in weekly budget" value={money(b.remaining_budget)} sub={`of ${money(b.weekly_budget)}`} />
        {b.wallet_balance !== undefined && <Stat label="Wallet balance" value={money(b.wallet_balance)} />}
      </div>
      <section>
        <h3 className="font-semibold">Bought today</h3>
        {b.orders.length === 0 && <p className="text-muted">Nothing was bought today.</p>}
        {b.orders.map((o: any) => (
          <div key={o.order_id} className="mt-2">
            <p>
              <Link to="/orders" className="font-medium text-brand underline">Order #{o.order_id}</Link> at {o.store},{" "}
              {money(o.total)} {o.status === "canceled" && "(canceled)"}
            </p>
            <Lines lines={o.lines} />
          </div>
        ))}
      </section>
      {b.pending_approvals.length > 0 && (
        <section>
          <h3 className="font-semibold">Waiting for your approval</h3>
          <ul className="list-disc pl-5">
            {b.pending_approvals.map((a: any) => (
              <li key={a.approval_id}>
                <Link to="/approvals" className="text-brand underline">Request #{a.approval_id}</Link> at {a.store},{" "}
                {money(a.total)}
              </li>
            ))}
          </ul>
        </section>
      )}
      {section("Still on the list", b.remaining_items)}
      {section("Unavailable within 10 miles", b.unavailable)}
      {section("Blocked", b.blocked)}
    </>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-canvas p-3">
      <p className="text-sm text-muted">{label}</p>
      <p className="text-xl font-bold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-muted">{sub}</p>}
    </div>
  );
}
