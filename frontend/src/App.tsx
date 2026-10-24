import { NavLink, Navigate, Route, Routes } from "react-router";
import { api, refreshAll, type Approval, type Item, type Notification, type Settings } from "./api";
import { SettingsContext, useResource } from "./hooks";
import { DemoBar } from "./components/DemoBar";
import { VoiceAssistant } from "./components/VoiceAssistant";
import { ShoppingList } from "./pages/ShoppingList";
import { Approvals } from "./pages/Approvals";
import { Orders } from "./pages/Orders";
import { ActivityPage } from "./pages/Activity";
import { Inbox } from "./pages/Inbox";
import { SettingsPage } from "./pages/Settings";
import { WalletPage } from "./pages/Wallet";
import { money } from "./format";

export function App() {
  const { data: settings } = useResource<Settings>("/settings", 5000);
  const { data: approvals } = useResource<Approval[]>("/approvals");
  const { data: items } = useResource<Item[]>("/items");
  const { data: inbox } = useResource<Notification[]>("/notifications");
  const pending = approvals?.filter((a) => a.status === "pending").length ?? 0;
  const questions = items?.filter((i) => i.status === "needs_clarification").length ?? 0;

  const nav = [
    { to: "/list", label: "Shopping list", badge: questions, badgeLabel: "need answers" },
    { to: "/approvals", label: "Approvals", badge: pending, badgeLabel: "pending" },
    { to: "/orders", label: "Orders" },
    { to: "/activity", label: "Agent activity" },
    {
      to: "/wallet",
      label: "Wallet",
      badge: settings?.payment_method === "wallet" ? money(settings.wallet_balance) : undefined,
      badgeLabel: "balance",
      quiet: true,
    },
    { to: "/inbox", label: "Inbox", badge: inbox?.length ?? 0, badgeLabel: "messages", quiet: true },
    { to: "/settings", label: "Settings" },
  ];

  async function togglePause() {
    if (!settings) return;
    await api("/settings", { method: "PATCH", body: { paused: !settings.paused } });
    refreshAll();
  }

  return (
    <SettingsContext.Provider value={settings}>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-2">
        Skip to content
      </a>
      <DemoBar />
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 md:flex-row">
        <aside className="md:w-60 md:shrink-0">
          <div className="mb-5">
            <p className="text-xl font-bold text-brand">Shopper</p>
            <p className="text-sm text-muted">Your shopping assistant</p>
          </div>
          <nav aria-label="Main">
            <ul className="flex flex-wrap gap-1 md:flex-col">
              {nav.map((n) => (
                <li key={n.to}>
                  <NavLink
                    to={n.to}
                    className={({ isActive }) =>
                      `flex items-center justify-between gap-3 rounded-lg px-3 py-2 font-medium ${
                        isActive ? "bg-brand-soft text-brand-dark" : "text-ink hover:bg-white"
                      }`
                    }
                  >
                    {n.label}
                    {!!n.badge && (
                      <span
                        className={`rounded-full px-2 text-sm ${n.quiet ? "bg-stone-200 text-stone-700" : "bg-amber-400 text-stone-900"}`}
                        aria-label={`${n.badge} ${n.badgeLabel}`}
                      >
                        {n.badge}
                      </span>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          {settings && (
            <div className="card mt-5 p-4">
              <p className="text-sm font-medium text-muted">Assistant</p>
              <p className="mt-1 font-semibold">{settings.paused ? "Paused" : "Shopping for you"}</p>
              <button
                onClick={togglePause}
                className={`mt-3 w-full ${settings.paused ? "btn-primary" : "btn-secondary"}`}
                aria-pressed={settings.paused}
              >
                {settings.paused ? "Resume shopping" : "Pause shopping"}
              </button>
            </div>
          )}
          <VoiceAssistant />
        </aside>
        <main id="main" className="min-w-0 flex-1">
          {settings && !settings.setup_complete && (
            <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-900">
              Finish setup in <NavLink to="/settings" className="font-semibold underline">Settings</NavLink> (add a
              payment method and a contact) before the assistant can shop.
            </div>
          )}
          <Routes>
            <Route path="/" element={<Navigate to="/list" replace />} />
            <Route path="/list" element={<ShoppingList />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/activity" element={<ActivityPage />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/wallet" element={<WalletPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/list" replace />} />
          </Routes>
        </main>
      </div>
    </SettingsContext.Provider>
  );
}
