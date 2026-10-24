import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, refreshAll, type Settings } from "../api";
import { useSettings } from "../hooks";
import { CATEGORIES, DAYS, money } from "../format";

const TIMEZONES = ["America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York", "Pacific/Honolulu"];

export function SettingsPage() {
  const settings = useSettings();
  if (!settings) return null;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted">Your limits and preferences. The assistant asks for approval when a purchase falls outside them.</p>
      </header>
      <PreferencesForm settings={settings} />
      <PaymentMethod settings={settings} />
      {settings.payment_method === "card" && <CardForm settings={settings} />}
      <section className="card">
        <h2 className="text-lg font-semibold">Rules that always apply</h2>
        <p className="text-muted">These platform limits can't be changed or approved away.</p>
        <ul className="mt-3 list-disc space-y-1 pl-5">
          {settings.platform_rules.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function PreferencesForm({ settings }: { settings: Settings }) {
  const [form, setForm] = useState(settings);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  useEffect(() => setForm(settings), [settings.timezone, settings.location_label]); // eslint-disable-line

  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setForm({ ...form, [k]: v });
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const { card, setup_complete, platform_rules, agent_mode, paused, payment_method, wallet_balance, bank, ...body } = form;
      await api("/settings", { method: "PATCH", body });
      setSaved("Saved.");
      window.setTimeout(() => setSaved(""), 3000);
      refreshAll();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form onSubmit={save} className="space-y-6">
      <section className="card space-y-4">
        <h2 className="text-lg font-semibold">Location and time</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Delivery address" id="loc">
            <input id="loc" className="input" value={form.location_label} onChange={(e) => set("location_label", e.target.value)} />
          </Field>
          <Field label="Time zone" id="tz">
            <select id="tz" className="input" value={form.timezone} onChange={(e) => set("timezone", e.target.value)}>
              {TIMEZONES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Latitude" id="lat">
            <input id="lat" type="number" step="0.0001" className="input" value={form.lat} onChange={(e) => set("lat", Number(e.target.value))} />
          </Field>
          <Field label="Longitude" id="lng">
            <input id="lng" type="number" step="0.0001" className="input" value={form.lng} onChange={(e) => set("lng", Number(e.target.value))} />
          </Field>
        </div>
        <p className="text-sm text-muted">Stores are only used if they're within 10 miles of this point (straight-line distance).</p>
      </section>

      <section className="card space-y-4">
        <h2 className="text-lg font-semibold">Budget and limits</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Money label="Weekly budget" id="wb" max={15000} value={form.weekly_budget} onChange={(v) => set("weekly_budget", v)} />
          <Money label="Limit per order" id="ol" max={1000} value={form.order_limit} onChange={(v) => set("order_limit", v)} />
          <Money label="Max delivery fee" id="df" value={form.max_delivery_fee} onChange={(v) => set("max_delivery_fee", v)} />
        </div>
      </section>

      <section className="card space-y-4">
        <h2 className="text-lg font-semibold">Preferences</h2>
        <Field label="If my preferred product isn't available" id="sub">
          <select id="sub" className="input sm:w-80" value={form.substitution_default} onChange={(e) => set("substitution_default", e.target.value as Settings["substitution_default"])}>
            <option value="approval">Ask me before substituting</option>
            <option value="allow">Pick a close substitute</option>
            <option value="prohibit">Don't substitute</option>
          </select>
        </Field>
        <fieldset>
          <legend className="label">Always ask me before buying</legend>
          <div className="flex flex-wrap gap-3">
            {CATEGORIES.map((c) => (
              <label key={c} className="flex items-center gap-2 capitalize">
                <input type="checkbox" checked={form.always_approve_categories.includes(c)} onChange={() => set("always_approve_categories", toggle(form.always_approve_categories, c))} />
                {c}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend className="label">Days the assistant may shop (10 a.m. to 5 p.m.)</legend>
          <div className="flex flex-wrap gap-3">
            {DAYS.map((d, i) => (
              <label key={d} className="flex items-center gap-2">
                <input type="checkbox" checked={form.permitted_days.includes(i)} onChange={() => set("permitted_days", toggle(form.permitted_days, i).sort())} />
                {d}
              </label>
            ))}
          </div>
        </fieldset>
      </section>

      <section className="card space-y-4">
        <h2 className="text-lg font-semibold">Notifications</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Send my daily summary by" id="ch">
            <select id="ch" className="input" value={form.notify_channel} onChange={(e) => set("notify_channel", e.target.value as Settings["notify_channel"])}>
              <option value="email">Email</option>
              <option value="sms">Text message</option>
            </select>
          </Field>
          <Field label={form.notify_channel === "sms" ? "Phone number" : "Email address"} id="contact">
            <input id="contact" className="input" value={form.notify_contact} onChange={(e) => set("notify_contact", e.target.value)} />
          </Field>
        </div>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={form.purchase_notifications} onChange={(e) => set("purchase_notifications", e.target.checked)} />
          Also message me after every purchase
        </label>
        <p className="text-sm text-muted">Approval requests are always sent, even if purchase messages are off.</p>
      </section>

      <div className="flex items-center gap-3">
        <button className="btn-primary">Save settings</button>
        {saved && <span role="status" className="text-emerald-700">{saved}</span>}
        {error && <span role="alert" className="text-red-700">{error}</span>}
      </div>
    </form>
  );
}

function PaymentMethod({ settings }: { settings: Settings }) {
  const [error, setError] = useState("");

  async function choose(method: Settings["payment_method"]) {
    setError("");
    try {
      await api("/settings", { method: "PATCH", body: { payment_method: method } });
      refreshAll();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const options = [
    {
      value: "wallet" as const,
      label: "Wallet",
      detail: settings.bank
        ? `${money(settings.wallet_balance)} available, funded from ${settings.bank.bank_name} •••• ${settings.bank.last4}`
        : "Link a bank account first",
    },
    {
      value: "card" as const,
      label: "Test card",
      detail: settings.card ? `${settings.card.brand} •••• ${settings.card.last4}` : "No card saved yet",
    },
  ];

  return (
    <section className="card space-y-4">
      <h2 className="text-lg font-semibold">Payment method</h2>
      <fieldset>
        <legend className="label">The assistant pays with</legend>
        <div className="space-y-2">
          {options.map((o) => (
            <label key={o.value} className="flex items-start gap-2">
              <input type="radio" name="payment_method" className="mt-1" checked={settings.payment_method === o.value} onChange={() => choose(o.value)} />
              <span>
                <span className="font-medium">{o.label}</span>
                <span className="block text-sm text-muted">{o.detail}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {settings.payment_method === "wallet" && (
        <p className="text-sm text-muted">
          Orders wait until your balance covers them. <Link to="/wallet" className="font-medium text-brand underline">Manage your wallet</Link>
        </p>
      )}
      {error && <p className="text-red-700" role="alert">{error}</p>}
    </section>
  );
}

function CardForm({ settings }: { settings: Settings }) {
  const [form, setForm] = useState({ number: "", exp: "", cvc: "", name: "", zip: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const [mm, yy] = form.exp.split("/").map((s) => Number(s.trim()));
    setBusy(true);
    setError("");
    try {
      await api("/card", {
        method: "PUT",
        body: { number: form.number, exp_month: mm || 0, exp_year: yy < 100 ? 2000 + yy : yy, cvc: form.cvc, name: form.name, zip: form.zip },
      });
      setForm({ number: "", exp: "", cvc: "", name: "", zip: "" });
      refreshAll();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card space-y-4">
      <h2 className="text-lg font-semibold">Payment card</h2>
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-950" role="note">
        <strong>Demo only: use a test card.</strong> This demo stores card details without PCI-compliant protection, so
        it only accepts published test numbers such as <span className="font-mono">4242 4242 4242 4242</span>. Never
        enter a real card.
      </div>
      {settings.card && (
        <p>
          Saved card: <strong>{settings.card.brand} •••• {settings.card.last4}</strong>, expires {String(settings.card.exp_month).padStart(2, "0")}/
          {settings.card.exp_year}, {settings.card.name}
        </p>
      )}
      <form onSubmit={save} className="grid gap-3 sm:grid-cols-6">
        <Field label="Card number" id="cc" className="sm:col-span-3">
          <input id="cc" className="input font-mono" inputMode="numeric" autoComplete="off" placeholder="4242 4242 4242 4242" value={form.number} onChange={(e) => setForm({ ...form, number: e.target.value })} required />
        </Field>
        <Field label="Expiry (MM/YY)" id="exp" className="sm:col-span-2">
          <input id="exp" className="input" placeholder="12/29" autoComplete="off" value={form.exp} onChange={(e) => setForm({ ...form, exp: e.target.value })} required />
        </Field>
        <Field label="CVC" id="cvc">
          <input id="cvc" className="input" placeholder="123" autoComplete="off" value={form.cvc} onChange={(e) => setForm({ ...form, cvc: e.target.value })} />
        </Field>
        <Field label="Name on card" id="ccname" className="sm:col-span-4">
          <input id="ccname" className="input" autoComplete="off" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </Field>
        <Field label="ZIP" id="zip" className="sm:col-span-2">
          <input id="zip" className="input" autoComplete="off" value={form.zip} onChange={(e) => setForm({ ...form, zip: e.target.value })} />
        </Field>
        <div className="sm:col-span-6">
          <button className="btn-primary" disabled={busy}>{settings.card ? "Replace card" : "Save card"}</button>
          {error && <p className="mt-2 text-red-700" role="alert">{error}</p>}
          <p className="mt-2 text-sm text-muted">The CVC is checked but never saved.</p>
        </div>
      </form>
    </section>
  );
}

export function Field({ label, id, className = "", children }: { label: string; id: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={className}>
      <label className="label" htmlFor={id}>{label}</label>
      {children}
    </div>
  );
}

export function Money({ label, id, value, max, onChange }: { label: string; id: string; value: string; max?: number; onChange: (v: string) => void }) {
  return (
    <Field label={label} id={id}>
      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">$</span>
        <input id={id} type="number" min={0} max={max} step="0.01" className="input pl-7" value={value} onChange={(e) => onChange(e.target.value)} />
      </div>
    </Field>
  );
}
