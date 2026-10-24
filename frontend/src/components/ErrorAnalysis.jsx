import { api } from "../api/client";
import usePolling from "../hooks/usePolling";
import { MARKET_LABELS } from "./ForecastMarkets";
const number = (v) => (v == null ? "—" : v.toFixed(2));
export default function ErrorAnalysis({ league = "ALL" }) {
  const { data, error } = usePolling(
    () => api.diagnostics(league),
    league,
    60000,
  );
  if (!data)
    return (
      <p className="text-xs text-mute">
        {error || "Revisando errores y resultados confirmados…"}
      </p>
    );
  return (
    <details className="panel rounded-xl p-5 space-y-4">
      <summary className="cursor-pointer font-semibold text-sm">
        Diagnóstico de fallos · {data.matches} partidos · {data.lost} fallos de{" "}
        {data.settled} selecciones
      </summary>
      <p className="text-xs text-mute leading-6">
        {data.prospective_matches} partidos prospectivos y{" "}
        {data.retrospective_matches} retrospectivos evaluados. Diferencias entre
        la liquidación guardada y la fuente actual:{" "}
        {data.settlement_discrepancies.length}. Un fallo de pronóstico no
        implica por sí mismo un error de código.
      </p>
      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {Object.entries(MARKET_LABELS).map(([key, title]) => {
          const m = data.markets[key];
          return (
            <div
              key={key}
              className="border border-ink-950/10 rounded-lg p-3 text-xs"
            >
              <h3 className="font-semibold">{title}</h3>
              <p className="text-mute mt-2">
                {m.won} aciertos / {m.lost} fallos
              </p>
              {key !== "result" && (
                <p className="text-mute mt-2">
                  Media esperada: {number(m.mean_expected)}
                  <br />
                  Media real: {number(m.mean_actual)}
                  <br />
                  Error medio (esperada − real): {number(m.mean_error)}
                </p>
              )}
              <p className="text-amber mt-2">
                {m.reconstructed} mercados reconstruidos; {m.retrospective}{" "}
                retrospectivos.
              </p>
            </div>
          );
        })}
      </div>
      <h3 className="text-sm font-semibold">Regla de doble oportunidad</h3>
      <p className="text-xs text-mute leading-6">
        Cuando equipo y empate son las dos probabilidades más altas y se separan
        hasta {data.policy.threshold_pp} puntos porcentuales, se recomienda
        local o empate (1X) o visitante o empate (X2). La probabilidad de cubrir
        cualquiera de ambos es la suma de sus probabilidades. Si no se cumple,
        se mantiene el resultado simple.
      </p>
      <p className="text-xs text-amber leading-6">
        Comparación retrospectiva: en {data.policy.sample} partidos, la
        selección simple habría acertado {data.policy.single_wins} y la nueva
        regla {data.policy.candidate_wins}; cambiaría {data.policy.changed}{" "}
        selecciones. {data.policy.note}
      </p>
      <p className="text-xs text-mute leading-6">
        {data.conclusion} Las selecciones de encuentros aún no iniciados se
        revisan ante un modelo o una política nuevos, conservando el historial.
        Los registros de partidos iniciados o finalizados permanecen cerrados.
      </p>
    </details>
  );
}
