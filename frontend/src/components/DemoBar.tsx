import { useEffect, useRef, useState } from "react";
import { api, refreshAll, type Clock, type RunResult } from "../api";
import { useResource, useSettings } from "../hooks";
import { dateTime, plural } from "../format";

function describe(r: RunResult) {
  if (r.note) return r.note;
  const parts = [];
  if (r.placed.length) parts.push(`placed ${plural(r.placed.length, "order")}`);
  if (r.approvals.length) parts.push(`${plural(r.approvals.length, "approval")} needed`);
  if (r.blocked) parts.push(`${r.blocked} blocked`);
  if (r.deferred) parts.push(`${r.deferred} waiting`);
  if (r.unavailable) parts.push(`${r.unavailable} unavailable`);
  return parts.length ? `Shopping run: ${parts.join(", ")}.` : "Shopping run: nothing new to buy.";
}

export function DemoBar() {
  const settings = useSettings();
  const { data: clock } = useResource<Clock>("/clock", 5000);
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string>("");
  const [autopilot, setAutopilot] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [timeInput, setTimeInput] = useState("10:15");
  const running = useRef(false);

  async function act(label: string, fn: () => Promise<string | void>) {
    setBusy(label);
    try {
      const msg = await fn();
      if (msg) setToast(msg);
    } catch (e) {
      setToast((e as Error).message);
    } finally {
      setBusy(null);
      refreshAll();
    }
  }

  const setClock = (body: object) =>
    act("clock", async () => {
      await api<Clock>("/demo/clock", { method: "POST", body });
    });
  const runShopping = () =>
    act("run", async () => describe(await api<RunResult>("/demo/run", { method: "POST" })));

  useEffect(() => {
    if (!autopilot) return;
    const id = window.setInterval(async () => {
      if (running.current) return;
      running.current = true;
      try {
        const r = await api<RunResult>("/demo/run", { method: "POST" });
        if (r.placed.length || r.approvals.length) setToast(`Autopilot: ${describe(r)}`);
        refreshAll();
      } catch {
        /* keep autopilot alive through transient errors */
      } finally {
        running.current = false;
      }
    }, 15000);
    return () => window.clearInterval(id);
  }, [autopilot]);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(""), 6000);
    return () => window.clearTimeout(id);
  }, [toast]);

  const tz = settings?.timezone;
  return (
    <div className="sticky top-0 z-20 border-b border-stone-700 bg-stone-900 text-stone-100">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 text-sm">
        <span className="rounded bg-amber-400 px-2 py-0.5 text-xs font-bold tracking-wide text-stone-900">DEMO</span>
        <div className="flex items-center gap-2" aria-live="polite">
          <span className="font-semibold tabular-nums">{clock ? dateTime(clock.now, tz) : "…"}</span>
          {clock && (
            <span className={`rounded-full px-2 py-0.5 text-xs ${clock.in_window ? "bg-emerald-600" : "bg-stone-600"}`}>
              {clock.in_window ? "Shopping hours" : "Closed (10 a.m. to 5 p.m.)"}
            </span>
          )}
          {clock && !clock.frozen && <span className="text-xs text-stone-400">live</span>}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <label className="sr-only" htmlFor="demo-time">Set demo time</label>
          <input
            id="demo-time"
            type="time"
            value={timeInput}
            onChange={(e) => setTimeInput(e.target.value)}
            className="rounded border border-stone-600 bg-stone-800 px-2 py-1 text-stone-100"
          />
          <DemoButton onClick={() => setClock({ at: timeInput })} disabled={!!busy}>Set</DemoButton>
          <DemoButton onClick={() => setClock({ advance_minutes: 60 })} disabled={!!busy}>+1 hr</DemoButton>
          <DemoButton onClick={() => setClock({ at: "10:00" })} disabled={!!busy}>10:00 AM</DemoButton>
          <DemoButton onClick={() => setClock({ at: "17:05" })} disabled={!!busy}>5:05 PM</DemoButton>
          <DemoButton
            onClick={() => {
              const next = new Date(new Date(clock?.now ?? Date.now()).getTime() + 86400000);
              const on = new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(next);
              setClock({ at: "10:00", on });
            }}
            disabled={!!busy}
          >
            Next day 10 AM
          </DemoButton>
          {clock?.frozen && (
            <DemoButton onClick={() => setClock({ live: true })} disabled={!!busy}>Live time</DemoButton>
          )}
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          <button
            onClick={runShopping}
            disabled={!!busy}
            className="rounded bg-emerald-500 px-3 py-1 font-semibold text-stone-950 hover:bg-emerald-400 disabled:opacity-50"
          >
            {busy === "run" ? "Shopping…" : "Run shopping"}
          </button>
          <DemoButton
            onClick={() =>
              act("summary", async () => {
                await api("/demo/summary", { method: "POST" });
                return "Daily summary sent. Check the Inbox.";
              })
            }
            disabled={!!busy}
          >
            Send summary
          </DemoButton>
          <label className="flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 hover:bg-stone-800">
            <input type="checkbox" checked={autopilot} onChange={(e) => setAutopilot(e.target.checked)} />
            Autopilot
          </label>
          <DemoButton
            onClick={() => {
              if (!confirmReset) {
                setConfirmReset(true);
                window.setTimeout(() => setConfirmReset(false), 4000);
                return;
              }
              setConfirmReset(false);
              act("reset", async () => {
                await api("/demo/reset", { method: "POST", body: { preload: true } });
                return "Demo reset with Mike's list.";
              });
            }}
            disabled={!!busy}
          >
            {busy === "reset" ? "Resetting…" : confirmReset ? "Click again to reset" : "Reset demo"}
          </DemoButton>
          <span
            className={`ml-1 rounded px-1.5 py-0.5 text-xs ${settings?.agent_mode === "ai" ? "bg-indigo-500/30 text-indigo-200" : "bg-stone-700 text-stone-300"}`}
            title={settings?.agent_mode === "ai" ? "Claude is choosing products" : "No API key: using keyword rules"}
          >
            Agent: {settings?.agent_mode === "ai" ? "Claude" : "rules"}
          </span>
        </div>
      </div>
      {toast && (
        <div role="status" className="border-t border-stone-700 bg-stone-800">
          <p className="mx-auto max-w-7xl px-4 py-1.5 text-sm text-amber-200">{toast}</p>
        </div>
      )}
    </div>
  );
}

function DemoButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="rounded border border-stone-600 px-2.5 py-1 hover:bg-stone-800 disabled:opacity-50"
    />
  );
}
