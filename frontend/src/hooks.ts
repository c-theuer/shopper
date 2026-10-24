import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, REFRESH_EVENT, type Settings } from "./api";

/** Fetch a resource, refetch every few seconds and whenever refreshAll() fires. */
export function useResource<T>(path: string, intervalMs = 3000) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<Error | undefined>();
  const alive = useRef(true);

  const load = useCallback(() => {
    api<T>(path)
      .then((d) => alive.current && (setData(d), setError(undefined)))
      .catch((e) => alive.current && setError(e));
  }, [path]);

  useEffect(() => {
    alive.current = true;
    load();
    const id = window.setInterval(load, intervalMs);
    window.addEventListener(REFRESH_EVENT, load);
    return () => {
      alive.current = false;
      window.clearInterval(id);
      window.removeEventListener(REFRESH_EVENT, load);
    };
  }, [load, intervalMs]);

  return { data, error, reload: load };
}

export const SettingsContext = createContext<Settings | undefined>(undefined);

export function useSettings() {
  return useContext(SettingsContext);
}
