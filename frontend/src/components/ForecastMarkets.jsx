import { kickoffLabel, pct } from "../api/client";
export const MARKET_LABELS = {
  result: "Resultado 1X2",
  goals: "Goles totales",
  corners: "Córners totales",
  yellows: "Amarillas totales",
};
export function pickLabel(pick, line) {
  return (
    {
      "1X": "Local o empate (1X)",
      X2: "Visitante o empate (X2)",
      LOCAL: "Local",
      EMPATE: "Empate",
      VISITANTE: "Visitante",
      OVER: `Más de ${line}`,
      UNDER: `Menos de ${line}`,
    }[pick] || pick
  );
}
export default function ForecastMarkets({ snapshot, compact = false, technical = true }) {
  if (!snapshot)
    return (
      <div className="empty-state text-xs">
        Sin pronóstico disponible con datos suficientes.
      </div>
    );
  return (
    <div className="space-y-3">
      {technical && snapshot.history_notice && <details className="text-xs text-mute leading-6"><summary className="cursor-pointer py-2">Sobre este pronóstico</summary><p>{snapshot.history_notice}</p></details>}
      <div
        className={`grid gap-3 ${compact ? "sm:grid-cols-2" : "sm:grid-cols-2 xl:grid-cols-4"}`}
      >
        {Object.entries(MARKET_LABELS).map(([key, title]) => {
          const m = snapshot.markets[key];
          return (
            <article key={key} className="panel rounded-xl p-4">
              <h3 className="text-xs font-semibold mb-3">{title}</h3>
              {technical && snapshot.specialists?.[key] && <p className="text-[10px] text-led mb-3">{snapshot.specialists[key].family} · {snapshot.phase === "LIVE" ? "En vivo" : "Previo"}</p>}
              {!m?.available ? (
                <p className="text-xs text-mute">
                  {technical ? (m?.reason || "Sin datos disponibles") : "No disponible"}
                </p>
              ) : (
                <>
                  <p className="text-[10px] text-mute mb-3 min-h-[30px]">
                    {key === "result"
                      ? "Probabilidad al final del partido"
                      : `Total esperado: ${m.expected_total.toFixed(1)}${snapshot.phase === "LIVE" ? ` · Actual: ${m.current}` : ""}`}
                  </p>
                  <div className={key === "result" ? "grid grid-cols-3 gap-2 sm:block sm:space-y-2" : "grid grid-cols-2 gap-2 sm:block sm:space-y-2"}>
                    {Object.entries(m.choices).map(([pick, p]) => (
                      <div
                        key={pick}
                        className="flex flex-col sm:flex-row justify-between items-center gap-2 text-[11px] px-3 py-2.5 border border-ink-950/10 rounded-md"
                      >
                        <span>{pickLabel(pick, m.line)}</span>
                        <strong className="text-led stat-num text-sm">
                          {pct(p)}
                        </strong>
                      </div>
                    ))}
                  </div>
                  {key === "result" && m.suggestion && (
                    <div className="mt-4 text-xs text-led">
                      <p>
                        Sugerencia: {pickLabel(m.suggestion.pick)} ·{" "}
                        {pct(m.suggestion.probability)}
                      </p>
                      {technical && <details className="text-[10px] text-mute mt-2"><summary className="cursor-pointer py-2">Por qué se sugiere</summary><p>{m.suggestion.reason}</p></details>}
                    </div>
                  )}
                  {technical && key !== "result" && (
                    <details className="text-[10px] text-mute mt-3 leading-5"><summary className="cursor-pointer py-2">Base del cálculo</summary><p>
                      {m.basis}
                      {key !== "goals"
                        ? ` · ${m.prior_samples} partidos observados`
                        : ""}
                    </p></details>
                  )}
                  {technical && m.history?.length > 0 && <details className="mt-3 text-[10px] leading-5">
                    <summary className="text-led cursor-pointer">Ver historial real · local {m.history_coverage.home}/5 · visitante {m.history_coverage.away}/5</summary>
                    {m.history.map(row => <a key={row.match_id} href={row.source_url} target="_blank" rel="noreferrer" className="block text-mute border-b border-ink-950/5 py-2">{kickoffLabel(row.kickoff)} · {row.home} vs {row.away} · {row.home_value}–{row.away_value} (total {row.total}) ↗</a>)}
                  </details>}
                </>
              )}
            </article>
          );
        })}
      </div>
      {technical && <p className="text-[10px] text-mute">
        {snapshot.model_version} · Guardado {kickoffLabel(snapshot.created_at)}
      </p>}
    </div>
  );
}
