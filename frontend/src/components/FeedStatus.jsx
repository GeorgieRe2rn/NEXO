import { RefreshCw, WifiOff } from "lucide-react";
import { localTime } from "../api/client";
import { useFeed } from "./FeedContext";

export default function FeedStatus({ compact = false, league = "ALL" }) {
  const { meta, error, loading, reload } = useFeed();
  const sources=(meta?.leagues||[]).filter(l=>league==="ALL"||l.code===league);
  const healthy =
    sources.filter((l) => !l.stale && l.status === "ok").length || 0;
  const times =
    sources
      .map((l) => l.last_success)
      .filter(Boolean)
      .sort() || [];
  return (
    <div
      className={`flex items-center gap-2 text-[11px] ${error || !healthy ? "text-amber" : "text-mute"}`}
    >
      {error ? (
        <WifiOff size={12} />
      ) : healthy ? (
        <span className="live-dot" />
      ) : (
        <span className="h-1.5 w-1.5 bg-amber rounded-full" />
      )}
      <span>
        {error
          ? "Sin conexión · reconectando"
          : loading
            ? "Conectando con resultados…"
            : healthy
              ? `${healthy}/${sources.length} ligas sincronizadas`
              : "Esperando datos del proveedor"}
        {!compact && times.length > 0
          ? ` · Último éxito ${localTime(times.at(-1))}`
          : ""}
      </span>
      <button
        onClick={reload}
        aria-label="Volver a consultar resultados"
        className="p-1 hover:text-paper"
      >
        <RefreshCw size={12} />
      </button>
    </div>
  );
}
