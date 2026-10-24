export function money(v: string | number | null | undefined) {
  if (v === null || v === undefined || v === "") return "–";
  return Number(v).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function dateTime(iso: string, timeZone?: string, opts?: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    ...opts,
  }).format(new Date(iso));
}

export function time(iso: string, timeZone?: string) {
  return new Intl.DateTimeFormat("en-US", { timeZone, hour: "numeric", minute: "2-digit" }).format(new Date(iso));
}

export function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export const CATEGORIES = ["groceries", "household", "lifestyle", "furniture", "other"] as const;
export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
