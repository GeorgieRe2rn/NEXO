import { useCallback, useEffect, useRef, useState } from "react";

export default function usePolling(loader, key, interval = 15000) {
  const latest = useRef(loader);
  latest.current = loader;
  const [state, setState] = useState({ data: null, loading: true, error: "" });
  const reload = useRef(() => {});
  useEffect(() => {
    let active = true,
      running = false;
    setState({ data: null, loading: true, error: "" });
    const load = async () => {
      if (!active || running || document.hidden) return;
      running = true;
      try {
        const data = await latest.current();
        if (active) setState({ data, loading: false, error: "" });
      } catch {
        if (active)
          setState((s) => ({
            ...s,
            loading: false,
            error: "No se pudo conectar. Reintentaremos automáticamente.",
          }));
      } finally {
        running = false;
      }
    };
    reload.current = load;
    load();
    const timer = setInterval(load, interval);
    const resume = () => {
      if (!document.hidden) load();
    };
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("online", resume);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("online", resume);
    };
  }, [key, interval]);
  return { ...state, reload: useCallback(() => reload.current(), []) };
}
