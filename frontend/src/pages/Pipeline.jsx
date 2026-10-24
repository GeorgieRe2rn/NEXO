import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function Pipeline() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.pipeline().then(setData).catch(() => {});

  useEffect(() => {
    load();
  }, []);

  const run = async () => {
    setBusy(true);
    try {
      await api.csrf();
      await api.runEtl();
      await load();
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <p className="text-slate-400">Leyendo tablas de conocimiento…</p>;

  const k = data.knowledge_tables || {};

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <p className="text-[12px] text-mute">ETL</p>
        <h2 className="font-display text-3xl md:text-4xl mt-1">Pipeline de extracción</h2>
        <p className="text-slate-400 mt-2">{data.constraint}</p>
      </div>

      <div className="grid md:grid-cols-4 gap-4">
        {[
          ["Forma equipos", k.team_form_snapshots, "team_form_snapshots"],
          ["Forma jugadores", k.player_form_snapshots, "player_form_snapshots"],
          ["Predicciones", k.predictions, "predictions"],
          ["Caché API", data.cache?.entries ?? 0, "api_cache"],
        ].map(([label, n, table]) => (
          <div key={table} className="glass rounded-3xl p-5">
            <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">{table}</p>
            <p className="font-display text-4xl mt-2">{n}</p>
            <p className="text-sm text-slate-400 mt-1">{label}</p>
          </div>
        ))}
      </div>

      <div className="glass rounded-3xl p-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h3 className="font-display text-xl">Flujo</h3>
            <p className="text-sm text-slate-400 mt-1">Extract (API-Football / football-data.org) → Transform (stats last-5 oficiales) → Load → Knowledge</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={run}
              disabled={busy}
              className="rounded-md bg-paper text-ink-950 px-4 py-2 text-sm disabled:opacity-50"
            >
              {busy ? "Ejecutando…" : "Reejecutar ETL"}
            </button>
            <button
              onClick={async () => {
                setBusy(true);
                try {
                  await api.csrf();
                  await api.runRosters();
                  await load();
                } finally {
                  setBusy(false);
                }
              }}
              disabled={busy}
              className="rounded-md border border-ink-950/15 px-4 py-2 text-sm disabled:opacity-50"
            >
              Plantillas
            </button>
            <button
              onClick={async () => {
                setBusy(true);
                try {
                  await api.csrf();
                  await api.runEnrich();
                  await load();
                } finally {
                  setBusy(false);
                }
              }}
              disabled={busy}
              className="rounded-md border border-ink-950/15 px-4 py-2 text-sm disabled:opacity-50"
            >
              Stats y lesiones
            </button>
          </div>
        </div>
        <ol className="mt-6 grid md:grid-cols-4 gap-3 text-sm">
          {["Extract", "Transform", "Load", "Knowledge"].map((s, i) => (
            <li key={s} className="rounded-2xl border border-ink-950/10 p-4">
              <span className="stat-num text-mute">0{i + 1}</span>
              <p className="font-display text-lg mt-1">{s}</p>
            </li>
          ))}
        </ol>
        <ul className="mt-6 space-y-2 text-sm text-slate-300">
          {(data.features || []).map((f) => (
            <li key={f} className="flex gap-2">
              <span className="text-mute">–</span> {f}
            </li>
          ))}
        </ul>
      </div>

      <div className="glass rounded-3xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-[10px] uppercase tracking-[0.2em] text-slate-500 bg-ink-950/5">
            <tr>
              {["ID", "Fuente", "Estado", "Req", "Caché", "Filas", "Notas"].map((h) => (
                <th key={h} className="text-left px-4 py-3 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data.runs || []).map((r) => (
              <tr key={r.id} className="border-t border-ink-950/5">
                <td className="px-4 py-3 font-mono">{r.id}</td>
                <td className="px-4 py-3">{r.source}</td>
                <td className="px-4 py-3">{r.status}</td>
                <td className="px-4 py-3 font-mono">{r.requests_made}</td>
                <td className="px-4 py-3 font-mono">{r.cache_hits}</td>
                <td className="px-4 py-3 font-mono">{r.rows_upserted}</td>
                <td className="px-4 py-3 text-slate-400 max-w-xs truncate">{r.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
