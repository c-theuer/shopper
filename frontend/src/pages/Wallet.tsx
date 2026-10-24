import { useState } from "react";
import { Link } from "react-router";
import { api, refreshAll, type Wallet, type WalletEntry } from "../api";
import { useResource, useSettings } from "../hooks";
import { dateTime, money } from "../format";
import { Field, Money } from "./Settings";

const QUICK_AMOUNTS = ["50", "100", "250"];

export function WalletPage() {
  const { data } = useResource<Wallet>("/wallet");
  const settings = useSettings();
  if (!data || !settings) return null;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Wallet</h1>
        <p className="text-muted">Move money in from your bank so the assistant can shop with it.</p>
      </header>
      <section className="card flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">Available balance</p>
          <p className="text-3xl font-bold tabular-nums">{money(data.balance)}</p>
        </div>
        <p className="text-sm text-muted">
          {settings.payment_method === "wallet" ? (
            "The assistant pays from this balance."
          ) : (
            <>
              The assistant is paying with your card.{" "}
              <Link to="/settings" className="font-medium text-brand underline">Switch to the wallet</Link>
            </>
          )}
        </p>
      </section>
      {data.bank && <AddFunds />}
      <BankForm wallet={data} />
      <History entries={data.entries} tz={settings.timezone} />
    </div>
  );
}

function AddFunds() {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);

  async function add(value: string) {
    setBusy(true);
    setError("");
    try {
      await api("/wallet/deposits", { method: "POST", body: { amount: value } });
      setAmount("");
      setSaved(`Added ${money(value)}.`);
      window.setTimeout(() => setSaved(""), 3000);
      refreshAll();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card space-y-4">
      <h2 className="text-lg font-semibold">Add funds</h2>
      <div className="flex flex-wrap gap-2">
        {QUICK_AMOUNTS.map((a) => (
          <button key={a} type="button" className="btn-secondary" disabled={busy} onClick={() => add(a)}>
            + {money(a)}
          </button>
        ))}
      </div>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          add(amount);
        }}
      >
        <Money label="Other amount" id="amount" max={5000} value={amount} onChange={setAmount} />
        <button className="btn-primary" disabled={busy || !amount}>Add</button>
      </form>
      {saved && <p role="status" className="text-emerald-700">{saved}</p>}
      {error && <p role="alert" className="text-red-700">{error}</p>}
      <p className="text-sm text-muted">Demo deposits are available instantly. Up to $5,000 per deposit.</p>
    </section>
  );
}

function BankForm({ wallet }: { wallet: Wallet }) {
  const [form, setForm] = useState({ routing_number: "", account_number: "", holder_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/wallet/bank", { method: "PUT", body: form });
      setForm({ routing_number: "", account_number: "", holder_name: "" });
      refreshAll();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card space-y-4">
      <h2 className="text-lg font-semibold">Bank account</h2>
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-950" role="note">
        <strong>Demo only: use a test bank account.</strong> No real bank is connected and no money moves. Only
        routing number <span className="font-mono">110000000</span> with account{" "}
        <span className="font-mono">000123456789</span> is accepted. Never enter a real account.
      </div>
      {wallet.bank && (
        <p>
          Linked: <strong>{wallet.bank.bank_name} •••• {wallet.bank.last4}</strong>, {wallet.bank.holder_name}
        </p>
      )}
      <form onSubmit={save} className="grid gap-3 sm:grid-cols-6">
        <Field label="Routing number" id="routing" className="sm:col-span-2">
          <input id="routing" className="input font-mono" inputMode="numeric" autoComplete="off" placeholder="110000000" value={form.routing_number} onChange={(e) => setForm({ ...form, routing_number: e.target.value })} required />
        </Field>
        <Field label="Account number" id="account" className="sm:col-span-2">
          <input id="account" className="input font-mono" inputMode="numeric" autoComplete="off" placeholder="000123456789" value={form.account_number} onChange={(e) => setForm({ ...form, account_number: e.target.value })} required />
        </Field>
        <Field label="Account holder" id="holder" className="sm:col-span-2">
          <input id="holder" className="input" autoComplete="off" value={form.holder_name} onChange={(e) => setForm({ ...form, holder_name: e.target.value })} required />
        </Field>
        <div className="sm:col-span-6">
          <button className="btn-primary" disabled={busy}>{wallet.bank ? "Replace bank account" : "Link bank account"}</button>
          {error && <p className="mt-2 text-red-700" role="alert">{error}</p>}
          <p className="mt-2 text-sm text-muted">Only the last 4 digits of the account number are saved.</p>
        </div>
      </form>
    </section>
  );
}

const KIND_LABELS: Record<WalletEntry["kind"], string> = { deposit: "Deposit", purchase: "Purchase", refund: "Refund" };

function History({ entries, tz }: { entries: WalletEntry[]; tz: string }) {
  return (
    <section className="card space-y-3">
      <h2 className="text-lg font-semibold">History</h2>
      {entries.length === 0 && <p className="text-muted">No activity yet.</p>}
      <ul className="divide-y divide-stone-200">
        {entries.map((e) => (
          <li key={e.id} className="flex items-center justify-between gap-3 py-2">
            <div>
              <p className="font-medium">
                {KIND_LABELS[e.kind]}
                {e.order_id && (
                  <>
                    {" · "}
                    <Link to="/orders" className="text-brand underline">Order #{e.order_id}</Link>
                  </>
                )}
              </p>
              <p className="text-sm text-muted">{e.memo} · {dateTime(e.at, tz)}</p>
            </div>
            <p className={`font-semibold tabular-nums ${Number(e.amount) < 0 ? "" : "text-emerald-700"}`}>
              {Number(e.amount) < 0 ? "−" : "+"}
              {money(Math.abs(Number(e.amount)))}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
