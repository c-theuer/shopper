import { useState } from "react";
import { Link } from "react-router";
import { api, ApiError, refreshAll, type Item } from "../api";
import { useResource } from "../hooks";
import { CATEGORIES, money } from "../format";
import { StatusBadge } from "../components/StatusBadge";

const ORDER: Item["status"][] = ["needs_clarification", "awaiting_approval", "ready", "purchased", "unavailable", "blocked"];

type Draft = Partial<Omit<Item, "id" | "status">>;

const EMPTY: Draft = { name: "", category: "groceries", quantity: 1, priority: "normal", recurrence: "once", notes: "" };

export function ShoppingList() {
  const { data: items } = useResource<Item[]>("/items");
  const counts = Object.fromEntries(ORDER.map((s) => [s, items?.filter((i) => i.status === s).length ?? 0]));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Shopping list</h1>
        <p className="text-muted">
          Add, change, or remove items any time. The assistant always shops from the latest version of this list.
        </p>
      </header>

      <AddItem />

      {items && items.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="List readiness">
          {ORDER.filter((s) => counts[s]).map((s) => (
            <li key={s} className="flex items-center gap-1.5 rounded-full bg-white px-2 py-1 ring-1 ring-line">
              <StatusBadge status={s} /> <span className="pr-1 font-semibold">{counts[s]}</span>
            </li>
          ))}
        </ul>
      )}

      {items?.length === 0 && <p className="card text-muted">Your list is empty. Add your first item above.</p>}

      <ul className="space-y-3">
        {items
          ?.slice()
          .sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || a.id - b.id)
          .map((item) => <ItemCard key={item.id} item={item} />)}
      </ul>
    </div>
  );
}

function AddItem() {
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.name?.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api("/items", { method: "POST", body: clean(draft) });
      setDraft(EMPTY);
      setMore(false);
      refreshAll();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-4" aria-label="Add an item">
      <div className="grid gap-3 sm:grid-cols-[1fr_11rem_6rem_auto] sm:items-end">
        <div>
          <label className="label" htmlFor="new-name">Item</label>
          <input
            id="new-name"
            className="input"
            placeholder="e.g. Whole milk, a lamp, dining chair"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="new-cat">Category</label>
          <select
            id="new-cat"
            className="input capitalize"
            value={draft.category}
            onChange={(e) => setDraft({ ...draft, category: e.target.value })}
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="new-qty">Quantity</label>
          <input
            id="new-qty"
            type="number"
            min={1}
            max={99}
            className="input"
            value={draft.quantity}
            onChange={(e) => setDraft({ ...draft, quantity: Number(e.target.value) })}
          />
        </div>
        <button className="btn-primary" disabled={busy}>
          {busy ? "Checking…" : "Add to list"}
        </button>
      </div>
      <button type="button" className="text-sm font-medium text-brand underline" onClick={() => setMore(!more)} aria-expanded={more}>
        {more ? "Fewer details" : "More details (brand, color, price limit…)"}
      </button>
      {more && <DetailFields draft={draft} setDraft={setDraft} idPrefix="new" />}
      {error && <p className="text-red-700">{error}</p>}
    </form>
  );
}

function DetailFields({ draft, setDraft, idPrefix }: { draft: Draft; setDraft: (d: Draft) => void; idPrefix: string }) {
  const text = (key: keyof Draft, label: string, placeholder = "") => (
    <div>
      <label className="label" htmlFor={`${idPrefix}-${key}`}>{label}</label>
      <input
        id={`${idPrefix}-${key}`}
        className="input"
        placeholder={placeholder}
        value={(draft[key] as string) ?? ""}
        onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
      />
    </div>
  );
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {text("brand", "Brand", "Any")}
      {text("color", "Color", "Any")}
      {text("size", "Size", "Any")}
      <div>
        <label className="label" htmlFor={`${idPrefix}-max`}>Max price each ($)</label>
        <input
          id={`${idPrefix}-max`}
          type="number"
          min={0}
          step="0.01"
          className="input"
          value={draft.max_price ?? ""}
          onChange={(e) => setDraft({ ...draft, max_price: e.target.value || null })}
        />
      </div>
      <div>
        <label className="label" htmlFor={`${idPrefix}-sub`}>Substitutes</label>
        <select
          id={`${idPrefix}-sub`}
          className="input"
          value={draft.substitution ?? ""}
          onChange={(e) => setDraft({ ...draft, substitution: (e.target.value || undefined) as Draft["substitution"] })}
        >
          <option value="">Use my default</option>
          <option value="allow">Allow</option>
          <option value="approval">Ask me first</option>
          <option value="prohibit">Never</option>
        </select>
      </div>
      <div>
        <label className="label" htmlFor={`${idPrefix}-pri`}>Priority</label>
        <select
          id={`${idPrefix}-pri`}
          className="input"
          value={draft.priority}
          onChange={(e) => setDraft({ ...draft, priority: e.target.value as Draft["priority"] })}
        >
          <option value="high">High</option>
          <option value="normal">Normal</option>
          <option value="low">Low</option>
        </select>
      </div>
      <div>
        <label className="label" htmlFor={`${idPrefix}-by`}>Needed by</label>
        <input
          id={`${idPrefix}-by`}
          type="date"
          className="input"
          value={draft.needed_by ?? ""}
          onChange={(e) => setDraft({ ...draft, needed_by: e.target.value || null })}
        />
      </div>
      <div>
        <label className="label" htmlFor={`${idPrefix}-rec`}>Repeats</label>
        <select
          id={`${idPrefix}-rec`}
          className="input"
          value={draft.recurrence}
          onChange={(e) => setDraft({ ...draft, recurrence: e.target.value as Draft["recurrence"] })}
        >
          <option value="once">One time</option>
          <option value="weekly">Every week</option>
        </select>
      </div>
      <div className="sm:col-span-3">
        <label className="label" htmlFor={`${idPrefix}-notes`}>Notes</label>
        <textarea
          id={`${idPrefix}-notes`}
          className="input"
          rows={2}
          value={draft.notes ?? ""}
          onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
        />
      </div>
    </div>
  );
}

function clean(d: Draft) {
  const out: Record<string, unknown> = { ...d };
  for (const k of ["brand", "color", "size", "max_price", "needed_by", "substitution"]) {
    if (out[k] === "" || out[k] === undefined) delete out[k];
  }
  return out;
}

function ItemCard({ item }: { item: Item }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>(item);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [orderId, setOrderId] = useState<number | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setOrderId(null);
    try {
      await fn();
      refreshAll();
      return true;
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError && e.status === 409) setOrderId(e.detail?.order_id ?? null);
      return false;
    } finally {
      setBusy(false);
    }
  }

  const specs = [item.brand, item.color, item.size].filter(Boolean);
  const done = item.status === "purchased";

  return (
    <li className={`card ${item.status === "needs_clarification" ? "border-amber-300" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">
              {item.name}
              {item.quantity > 1 && <span className="font-normal text-muted"> × {item.quantity}</span>}
            </h2>
            <StatusBadge status={item.status} />
          </div>
          <p className="mt-0.5 text-sm capitalize text-muted">
            {[item.category, ...specs].join(" · ")}
            {item.max_price && <span className="normal-case"> · up to {money(item.max_price)} each</span>}
            {item.recurrence === "weekly" && <span className="normal-case"> · every week</span>}
            {item.priority === "high" && <span className="normal-case font-medium text-ink"> · high priority</span>}
          </p>
          {item.status_reason && <p className="mt-2 text-[0.95rem]">{item.status_reason}</p>}
          {item.status === "awaiting_approval" && (
            <Link to="/approvals" className="mt-2 inline-block font-medium text-brand underline">
              Review the approval request
            </Link>
          )}
        </div>
        {!editing && (
          <div className="flex shrink-0 flex-wrap gap-2">
            <button className="btn-secondary" onClick={() => (setDraft(item), setEditing(true))} disabled={busy}>
              Edit
            </button>
            {!done && item.status !== "blocked" && (
              <button
                className="btn-secondary"
                disabled={busy}
                onClick={() => run(() => api(`/items/${item.id}/defer`, { method: "POST", body: {} }))}
              >
                Tomorrow
              </button>
            )}
            <button className="btn-danger" disabled={busy} onClick={() => run(() => api(`/items/${item.id}`, { method: "DELETE" }))}>
              Remove
            </button>
          </div>
        )}
      </div>

      {item.status === "needs_clarification" && (
        <form
          className="mt-4 rounded-lg bg-amber-50 p-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (answer.trim() && (await run(() => api(`/items/${item.id}/answer`, { method: "POST", body: { answer } })))) {
              setAnswer("");
            }
          }}
        >
          <p className="font-medium text-amber-950">{item.clarification_question}</p>
          <div className="mt-2 flex gap-2">
            <label className="sr-only" htmlFor={`answer-${item.id}`}>Your answer</label>
            <input
              id={`answer-${item.id}`}
              className="input"
              placeholder="Type your answer"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
            />
            <button className="btn-primary shrink-0" disabled={busy}>
              {busy ? "Saving…" : "Answer"}
            </button>
          </div>
        </form>
      )}

      {editing && (
        <form
          className="mt-4 space-y-3 border-t border-line pt-4"
          onSubmit={async (e) => {
            e.preventDefault();
            const body = clean({
              name: draft.name, category: draft.category, quantity: draft.quantity, brand: draft.brand ?? "",
              color: draft.color ?? "", size: draft.size ?? "", max_price: draft.max_price, substitution: draft.substitution,
              priority: draft.priority, needed_by: draft.needed_by, recurrence: draft.recurrence, notes: draft.notes,
            });
            // Blank spec fields mean "any"; send them so they're cleared.
            for (const k of ["brand", "color", "size"] as const) body[k] = draft[k] ?? "";
            if (await run(() => api(`/items/${item.id}`, { method: "PATCH", body }))) setEditing(false);
          }}
        >
          <div className="grid gap-3 sm:grid-cols-[1fr_11rem_6rem]">
            <div>
              <label className="label" htmlFor={`e${item.id}-name`}>Item</label>
              <input id={`e${item.id}-name`} className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor={`e${item.id}-cat`}>Category</label>
              <select id={`e${item.id}-cat`} className="input capitalize" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor={`e${item.id}-qty`}>Quantity</label>
              <input id={`e${item.id}-qty`} type="number" min={1} max={99} className="input" value={draft.quantity} onChange={(e) => setDraft({ ...draft, quantity: Number(e.target.value) })} />
            </div>
          </div>
          <DetailFields draft={draft} setDraft={setDraft} idPrefix={`e${item.id}`} />
          <div className="flex gap-2">
            <button className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
            <button type="button" className="btn-secondary" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </form>
      )}

      {error && (
        <div className="mt-3 rounded-lg bg-red-50 p-3 text-red-800" role="alert">
          <p>{error}</p>
          {orderId && (
            <div className="mt-2 flex gap-2">
              <Link to="/orders" className="btn-secondary">View order #{orderId}</Link>
              <button
                className="btn-danger"
                onClick={() => run(() => api(`/orders/${orderId}/cancel`, { method: "POST" }))}
              >
                Cancel order #{orderId}
              </button>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
