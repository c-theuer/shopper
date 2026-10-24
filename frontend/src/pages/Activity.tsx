import { type Activity } from "../api";
import { useResource, useSettings } from "../hooks";
import { dateTime, money } from "../format";
import { SourceTag } from "../components/StatusBadge";

const DOT: Record<string, string> = {
  purchase: "bg-emerald-500",
  approval: "bg-violet-500",
  blocked: "bg-red-500",
  skip: "bg-stone-400",
  unavailable: "bg-stone-400",
  decision: "bg-sky-500",
  question: "bg-amber-400",
  choose: "bg-indigo-400",
};

const OUTCOME: Record<string, string> = {
  allow: "Allowed",
  needs_approval: "Needs approval",
  defer: "Waiting",
  block: "Blocked",
};

export function ActivityPage() {
  const { data } = useResource<Activity[]>("/activity");
  const settings = useSettings();
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Agent activity</h1>
        <p className="text-muted">
          Every step the assistant takes, and every rule check with its reasons. Claude suggests products; fixed rules
          decide what can be bought.
        </p>
      </header>
      <ol className="relative space-y-3 border-l-2 border-line pl-5">
        {data?.map((a) => (
          <li key={a.id} className="relative">
            <span className={`absolute -left-[1.72rem] top-2 h-3 w-3 rounded-full ring-4 ring-canvas ${DOT[a.kind] ?? "bg-stone-300"}`} />
            <div className="rounded-lg border border-line bg-white px-4 py-2.5">
              <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
                <time dateTime={a.at}>{dateTime(a.at, settings?.timezone)}</time>
                {(a.kind === "choose" || a.kind === "question" || a.source === "ai") && <SourceTag source={a.source} />}
              </div>
              <p className="mt-0.5">{a.message.replace(/: (allow|needs_approval|defer|block)\.$/, (_, o) => `: ${OUTCOME[o]}.`)}</p>
              {!!a.details.reasons?.length && (
                <ul className="mt-1.5 space-y-0.5 text-sm">
                  {a.details.reasons.map((r, i) => (
                    <li key={i} className="flex gap-2">
                      <span
                        className={`shrink-0 rounded px-1.5 text-xs font-semibold leading-5 ${
                          r.effect === "block"
                            ? "bg-red-100 text-red-800"
                            : r.effect === "needs_approval"
                              ? "bg-violet-100 text-violet-800"
                              : "bg-amber-100 text-amber-900"
                        }`}
                      >
                        {OUTCOME[r.effect]}
                      </span>
                      <span>
                        {r.message} <span className="text-muted">({r.layer === "platform" ? "platform rule" : "your setting"})</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {a.details.quote && a.kind === "decision" && (
                <p className="mt-1 text-sm text-muted">
                  Items {money(a.details.quote.subtotal)} + tax {money(a.details.quote.tax)} + delivery{" "}
                  {money(a.details.quote.delivery_fee)} + service {money(a.details.quote.service_fee)} ={" "}
                  <strong className="text-ink">{money(a.details.quote.total)}</strong>
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
