import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api, kickoffLabel, pct } from "../api/client";
import usePolling from "../hooks/usePolling";
import { MARKET_LABELS, pickLabel } from "./ForecastMarkets";
import ErrorAnalysis from "./ErrorAnalysis";
const STATUS = {
  PENDING: "Pendiente",
  WON: "Acierto",
  LOST: "Fallo",
  VOID: "Anulada",
};
export default function SelectionsHistory({ league = "ALL", technical = true }) {
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("ALL");
  useEffect(() => setPage(1), [league, filter]);
  const { data, error, loading, reload } = usePolling(
    () => api.selections(league, page, filter),
    `${league}:${page}:${filter}`,
    15000,
  );
  const grouped = {};
  for (const s of data?.items || []) {
    if (filter !== "ALL" && s.status !== filter) continue;
    (grouped[s.match_id] ||= { match: s, items: [] }).items.push(s);
  }
  const groups = Object.values(grouped).sort(
    (a, b) =>
      Number(b.items.some((s) => s.status === "PENDING")) -
        Number(a.items.some((s) => s.status === "PENDING")) ||
      new Date(a.match.kickoff) - new Date(b.match.kickoff),
  );
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap justify-between gap-3">
        <h2 className="text-2xl font-display">
          Registro de apuestas automáticas
        </h2>
        <button className="text-xs text-led" onClick={reload}>
          Actualizar
        </button>
      </div>
      <p className="text-xs text-mute">Simulación sin dinero · selecciones y resultados.</p>
      {error && (
        <p role="alert" className="text-xs text-amber">
          {error}
        </p>
      )}
      {technical && <ErrorAnalysis league={league} />}
      {loading && <div className="skeleton h-32" />}
      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              ["Aciertos", data.counts.WON],
              ["Fallos", data.counts.LOST],
              ["Pendientes", data.counts.PENDING],
              ["Anuladas", data.counts.VOID],
              ["Acierto prospectivo", pct(data.accuracy)],
            ].map(([k, v]) => (
              <div key={k} className="panel rounded-xl p-4">
                <p className="text-[10px] text-mute">{k}</p>
                <p className="stat-num text-led text-2xl mt-2">{v}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-amber">
            Registros retrospectivos: {data.retro_total || 0} · Acierto
            retrospectivo: {pct(data.retro_accuracy)}. Se evalúan aparte del
            acierto prospectivo y se excluyen del aprendizaje.
          </p>
          <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
            {Object.entries(MARKET_LABELS).map(([key, title]) => {
              const m = data.by_market?.[key];
              const n = (m?.won || 0) + (m?.lost || 0);
              return (
                <div key={key} className="panel rounded-lg p-4 text-xs">
                  <h3 className="font-semibold">{title}</h3>
                  <p className="text-mute mt-2">
                    {m?.won || 0} aciertos · {m?.lost || 0} fallos ·{" "}
                    {m?.pending || 0} pendientes
                  </p>
                  <p className="text-led mt-2">
                    Acierto combinado: {pct(n ? m.won / n : null)}
                  </p>
                </div>
              );
            })}
          </div>
          <label className="flex gap-3 items-center text-xs text-mute">
            Estado
            <select
              aria-label="Filtrar apuestas por estado"
              className="field"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="ALL">Todos</option>
              {Object.entries(STATUS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          {groups.map(({ match: m, items }) => (
            <article
              key={m.match_id}
              className="panel rounded-xl p-5 space-y-4"
            >
              <header className="flex flex-wrap justify-between gap-2">
                <Link
                  to={`/match/${m.match_id}`}
                  className="font-semibold text-sm hover:text-led"
                >
                  {m.home} vs {m.away} →
                </Link>
                <span className="text-[10px] text-mute">
                  {m.league} · {kickoffLabel(m.kickoff)} · Hermosillo
                </span>
              </header>
              {technical && m.history_notice && <p className="text-[10px] text-amber leading-5">{m.prediction_family} · {m.history_notice}</p>}
              {m.retrospective && (
                <p className="text-xs text-amber">
                  Registro retrospectivo: incorporado durante el partido usando
                  el previo de {kickoffLabel(m.prior_at)}. No usa el marcador ni
                  contadores actuales.
                </p>
              )}
              <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
                {Object.entries(MARKET_LABELS).map(([key, title]) => {
                  const s = items.find((i) => i.market === key);
                  return (
                    <div
                      key={key}
                      className="rounded-lg border border-ink-950/10 p-4 text-xs"
                    >
                      <h3 className="text-mute mb-3">{title}</h3>
                      {s ? (
                        <>
                          <p className="font-semibold text-led">
                            {s.withdrawal_reason ? "Retirada: sin respaldo de datos reales" : pickLabel(s.pick, s.line)}
                          </p>
                          <p className="text-mute mt-2">
                            {s.withdrawal_reason || <>Probabilidad previa: {pct(s.probability)}</>}
                          </p>
                          {technical && s.basis && <p className="text-[10px] text-amber mt-2 leading-5">{s.basis}{s.prior_samples != null && s.market !== "goals" ? ` · ${s.prior_samples} partidos observados` : ""}</p>}
                          {technical && s.history?.length > 0 && <details className="mt-3 text-[10px] leading-5">
                            <summary className="text-led cursor-pointer">Historial verificado · {s.history_coverage.home}/5 local · {s.history_coverage.away}/5 visitante</summary>
                            {s.history.map(row => <a key={row.match_id} href={row.source_url} target="_blank" rel="noreferrer" className="block text-mute border-b border-ink-950/5 py-2">{kickoffLabel(row.kickoff)} · {row.home} vs {row.away} · {row.home_value}–{row.away_value} ↗</a>)}
                          </details>}
                          <p
                            className={`mt-3 font-semibold ${s.status === "WON" ? "text-led" : s.status === "LOST" ? "text-amber" : "text-mute"}`}
                          >
                            {STATUS[s.status]}
                          </p>
                          <p className="mt-2">
                            Resultado real:{" "}
                            {s.result_value == null
                              ? "Esperando dato final"
                              : s.market === "result"
                                ? pickLabel(
                                    ["LOCAL", "EMPATE", "VISITANTE"][
                                      s.result_value
                                    ],
                                  )
                                : s.result_value}
                          </p>
                          <p className="mt-3 text-[9px] text-mute">
                            Registrada {kickoffLabel(s.created_at)}
                            <br />
                            {technical && s.model_version}
                          </p>
                          {technical && s.policy_version && (
                            <p className="text-[9px] text-mute mt-2">
                              Regla registrada: {s.policy_version}
                              <br />
                              {s.selection_reason}
                            </p>
                          )}
                          {technical && s.market === "result" &&
                            !s.policy_version &&
                            s.current_suggestion?.pick !== s.pick && (
                              <p className="text-[10px] text-amber mt-2">
                                La regla actual recomendaría{" "}
                                {pickLabel(s.current_suggestion.pick)} (
                                {pct(s.current_suggestion.probability)}). Esta
                                sugerencia no cambia la apuesta original ni su
                                resultado.
                              </p>
                            )}
                          {technical && s.revisions?.length > 0 && (
                            <details className="mt-3 text-[10px] text-mute">
                              <summary className="cursor-pointer text-led">
                                {s.revisions.length} revisiones automáticas
                              </summary>
                              {s.revisions.map((r, i) => (
                                <div
                                  key={i}
                                  className="mt-2 border-t border-ink-950/10 pt-2"
                                >
                                  <p>{kickoffLabel(r.at)}</p>
                                  <p>
                                    Antes:{" "}
                                    {pickLabel(
                                      r.previous.pick,
                                      r.previous.line,
                                    )}{" "}
                                    · {pct(r.previous.probability)} ·{" "}
                                    {r.previous.model}
                                  </p>
                                  <p>
                                    Después:{" "}
                                    {pickLabel(r.current.pick, r.current.line)}{" "}
                                    · {pct(r.current.probability)} ·{" "}
                                    {r.current.model}
                                  </p>
                                  <p>{r.reason}</p>
                                </div>
                              ))}
                            </details>
                          )}
                          {s.reconstructed && (
                            <p className="text-[10px] text-amber mt-2">
                              {s.basis ||
                                "Reconstruido desde datos previos; no era un mercado archivado."}
                            </p>
                          )}
                          {s.audit?.length > 1 && (
                            <p className="text-[9px] text-amber mt-2">
                              Historial de correcciones;{" "}
                              {s.audit.length} revisiones registradas.
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="text-mute">
                          {filter === "ALL"
                            ? "Sin registro previo disponible; no se inventan datos."
                            : "Sin selecciones con este estado."}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </article>
          ))}
          {!groups.length && (
            <div className="empty-state">
              Sin apuestas automáticas con este filtro. Se registran cuando
              exista un pronóstico previo válido para un partido futuro.
            </div>
          )}
          <div className="flex flex-wrap justify-between items-center gap-3 text-xs">
            <span className="text-mute">
              {data.match_total} partidos · Página {data.page} de {data.pages}
            </span>
            <div className="flex gap-4">
              <button
                className="text-led disabled:text-mute"
                disabled={data.page <= 1}
                onClick={() => setPage(data.page - 1)}
              >
                Anterior
              </button>
              <button
                className="text-led disabled:text-mute"
                disabled={data.page >= data.pages}
                onClick={() => setPage(data.page + 1)}
              >
                Siguiente
              </button>
            </div>
          </div>
          <p className="text-[10px] text-mute leading-5">
            Se muestran hasta 20 partidos por página; los totales incluyen todo
            el historial automático. La tasa prospectiva excluye retrospectivos,
            pendientes y anuladas. Los contadores finales ausentes permanecen
            pendientes. El análisis en vivo no modifica estas selecciones.
            Ningún pronóstico garantiza acertar.
          </p>
        </>
      )}
    </div>
  );
}
