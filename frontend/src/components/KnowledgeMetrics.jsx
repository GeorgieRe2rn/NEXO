import { useEffect, useState } from "react";
import { api } from "../api/client";

const percent = (v) =>
  v == null ? "Sin evidencia" : `${(v * 100).toFixed(1)}%`;
const decimal = (v) => (v == null ? "Sin evidencia" : v.toFixed(4));

export default function KnowledgeMetrics({ league = "ALL" }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api.metrics(league));
    } catch {
      setError(
        "No se pudieron cargar las métricas. Revisa la conexión y tu sesión.",
      );
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    setData(null);
    load();
  }, [league]);
  const e = data?.evaluation;
  const q = data?.quality;
  return (
    <div className="space-y-5">
      <div className="flex justify-between gap-3 items-center">
        <h2 className="font-display text-3xl">MÉTRICAS KDD</h2>
        <button
          onClick={load}
          disabled={loading}
          className="text-led text-sm disabled:opacity-50"
        >
          {loading ? "Cargando…" : "Actualizar"}
        </button>
      </div>
      <p className="text-mute">
        Evaluación del conocimiento extraído: calidad de datos y comparación de
        pronósticos previos al partido con resultados oficiales.
      </p>
      {error && (
        <p role="alert" className="text-red-300">
          {error}
        </p>
      )}
      {e && (
        <>
          {e.scope && <p className="text-xs text-led">{e.scope}</p>}
          {data.legacy_evaluation && <p className="text-xs text-mute">Historial anterior conservado: {data.legacy_evaluation.samples} casos. Sus aciertos no se suman a la evaluación ni al aprendizaje de v2.</p>}
          <p className="text-mute">
            Casos evaluados: <strong className="text-paper">{e.samples}</strong>{" "}
            · Estado: {e.status.replaceAll("_", " ")} · Cobertura sobre
            finalizados: {percent(e.coverage)}
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            {[
              [
                "Accuracy",
                percent(e.accuracy),
                "Proporción de resultados 1X2 acertados. Mayor es mejor.",
              ],
              [
                "F1 macro",
                decimal(e.macro_f1),
                "Promedio de F1 de local, empate y visitante. Mayor es mejor; clases sin soporte valen 0.",
              ],
              [
                "Log loss",
                decimal(e.log_loss),
                `Penaliza probabilidades equivocadas. Menor es mejor. Referencia uniforme: ${decimal(e.uniform_log_loss)}.`,
              ],
              [
                "Brier multiclase",
                decimal(e.brier),
                `Error cuadrático de probabilidades, rango 0–2. Menor es mejor. Referencia uniforme: ${decimal(e.uniform_brier)}.`,
              ],
            ].map(([label, value, note]) => (
              <div key={label} className="glass rounded-lg p-4">
                <p className="text-mute">{label}</p>
                <p className="stat-num text-3xl text-led my-2">{value}</p>
                <p className="text-sm text-mute">{note}</p>
              </div>
            ))}
          </div>
          <div className="glass rounded-lg p-4 overflow-x-auto">
            <h3 className="font-display text-xl mb-2">Matriz de confusión</h3>
            <p className="text-sm text-mute mb-3">
              Filas: resultado real. Columnas: resultado predicho. Los aciertos
              están en la diagonal.
            </p>
            <table className="w-full text-sm text-left">
              <thead>
                <tr>
                  <th>Real / Predicho</th>
                  {e.per_class.map((c) => (
                    <th key={c.label}>{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {e.confusion_matrix.map((row, i) => (
                  <tr key={i} className="border-t border-ink-950/10">
                    <th className="py-2">{e.per_class[i].label}</th>
                    {row.map((v, j) => (
                      <td key={j} className={i === j ? "text-led" : ""}>
                        {v}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="glass rounded-lg p-4 overflow-x-auto">
            <h3 className="font-display text-xl mb-3">Evaluación por clase</h3>
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  {["Clase", "Casos reales", "Precisión", "Recall", "F1"].map(
                    (h) => (
                      <th key={h}>{h}</th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {e.per_class.map((c) => (
                  <tr key={c.label} className="border-t border-ink-950/10">
                    <th className="py-2">{c.label}</th>
                    <td>{c.support}</td>
                    {[c.precision, c.recall, c.f1].map((v, i) => (
                      <td key={i}>{e.samples ? decimal(v) : "—"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="glass rounded-lg p-4 space-y-2 text-sm">
            <h3 className="font-display text-xl">Calidad de datos</h3>
            {e.architecture && <p className="text-xs text-mute">La cobertura de ventanas corresponde al inventario histórico. Los ejemplos utilizables de v2 se cuentan por separado en Aprendizaje.</p>}
            <p>Partidos oficiales finalizados: {q.finished_matches}</p>
            <p>
              Marcadores completos y no negativos:{" "}
              {percent(q.score_completeness)}
            </p>
            <p>
              Ventanas con los cinco partidos completos:{" "}
              {percent(q.full_last5_ratio)} ({q.form_snapshots} ventanas)
            </p>
            <p>
              Identificadores externos repetidos:{" "}
              {q.duplicate_external_id_groups} grupos por revisar
            </p>
            <p>
              Versiones evaluadas:{" "}
              {Object.entries(e.model_versions)
                .map(([v, n]) => `${v}: ${n}`)
                .join(" · ") || "Ninguna"}
            </p>
            <p>
              Exclusiones:{" "}
              {Object.entries(e.excluded)
                .map(([v, n]) => `${v}: ${n}`)
                .join(" · ") || "Ninguna"}
            </p>
          </div>
          <ul className="text-sm text-mute list-disc pl-5 space-y-2">
            {data.limitations.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
