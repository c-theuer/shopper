import { useState } from "react";
import { api, refreshAll, type Order } from "../api";
import { useResource, useSettings } from "../hooks";
import { dateTime, money } from "../format";
import { StatusBadge } from "../components/StatusBadge";

export function Orders() {
  const { data } = useResource<Order[]>("/orders");
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Orders</h1>
        <p className="text-muted">Everything the assistant has bought, with receipts and delivery status.</p>
      </header>
      {data?.length === 0 && <p className="card text-muted">No orders yet. Run shopping from the demo bar.</p>}
      <ul className="space-y-4">
        {data?.map((o) => <OrderCard key={o.id} o={o} />)}
      </ul>
    </div>
  );
}

function OrderCard({ o }: { o: Order }) {
  const settings = useSettings();
  const [error, setError] = useState("");
  const canCancel = o.status === "placed" && o.delivery_status !== "delivered";

  return (
    <li className="card">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">
            Order #{o.id} · {o.store}
          </h2>
          <p className="text-sm text-muted">
            {dateTime(o.committed_at, settings?.timezone)} · {o.store_address} · {o.distance_mi} mi
            {o.approval_id && ` · approved by you (request #${o.approval_id})`}
          </p>
        </div>
        <StatusBadge status={o.delivery_status} />
      </div>
      <table className="mt-3 w-full text-left">
        <caption className="sr-only">Receipt for order {o.id}</caption>
        <thead className="text-sm text-muted">
          <tr>
            <th className="py-1 font-medium">Item</th>
            <th className="py-1 font-medium">For list item</th>
            <th className="py-1 text-right font-medium">Price</th>
          </tr>
        </thead>
        <tbody>
          {o.lines.map((l) => (
            <tr key={l.item_id} className="border-t border-line">
              <td className="py-1.5">
                {l.quantity} × {l.product}
                <span className="text-sm text-muted">
                  {" "}
                  {[l.brand, l.color, l.size].filter(Boolean).join(", ")}
                </span>
              </td>
              <td className="py-1.5 text-muted">{l.item}</td>
              <td className="py-1.5 text-right tabular-nums">{money(Number(l.unit_price) * l.quantity)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="ml-auto mt-2 max-w-xs space-y-0.5 border-t border-line pt-2 text-sm">
        {(["subtotal", "tax", "delivery_fee", "service_fee"] as const).map((k) => (
          <div key={k} className="flex justify-between text-muted">
            <dt className="capitalize">{k.replace("_", " ")}</dt>
            <dd className="tabular-nums">{money(o[k])}</dd>
          </div>
        ))}
        <div className="flex justify-between pt-1 text-base font-semibold">
          <dt>Charged to {o.card}</dt>
          <dd className="tabular-nums">{money(o.total)}</dd>
        </div>
      </dl>
      {canCancel && (
        <div className="mt-3">
          <button
            className="btn-danger"
            onClick={async () => {
              try {
                await api(`/orders/${o.id}/cancel`, { method: "POST" });
                refreshAll();
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Cancel order
          </button>
          {error && <p className="mt-2 text-red-700">{error}</p>}
        </div>
      )}
    </li>
  );
}
