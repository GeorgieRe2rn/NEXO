import { api, kickoffLabel } from "../api/client";
import usePolling from "../hooks/usePolling";
export default function LearningPanel() {
  const { data, error } = usePolling(api.learning, "learning", 60000);
  if (!data)
    return (
      <p className="text-xs text-mute">
        {error || "Consultando el estado del aprendizaje…"}
      </p>
    );
  const report = data.last_attempt;
  return (
    <section className="panel rounded-xl p-5 space-y-4">
      <h2 className="text-base font-semibold">
        Aprendizaje supervisado y validación temporal
      </h2>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="hidden lg:block">
          <p className="text-[10px] text-mute">Versión vigente</p>
          <p className="text-led text-sm mt-2">{data.version}</p>
        </div>
        <div>
          <p className="text-[10px] text-mute">Partidos de evaluación prospectiva</p>
          <p className="stat-num text-xl mt-2">
            {data.evaluated_matches} / {data.minimum_matches} mínimo
          </p>
        </div>
        <div>
          <p className="text-[10px] text-mute">Estado de calibración</p>
          <p className="text-sm mt-2">
            {data.status === "awaiting_evidence"
              ? "Recopilando evidencia"
              : "Evaluando nuevas revisiones"}
          </p>
        </div>
      </div>
      <p className="hidden md:block text-xs text-mute leading-6">{data.notice}</p>
      {data.specialists && <div className="md:hidden space-y-3">{data.specialists.filter(s=>s.phase==="PRE").map(s=><article className="mobile-model-card" key={s.market}><div className="flex justify-between gap-3"><h3 className="font-semibold text-sm">{{result:"Ganador / empate",goals:"Goles",corners:"Córners",yellows:"Amarillas"}[s.market]}</h3><span className="text-[10px] text-mute">Previo</span></div><p className="text-led text-sm mt-2">{s.active}</p><p className="text-xs text-mute mt-1">{s.report.samples} ejemplos utilizables</p><details className="mt-3 text-xs text-mute"><summary className="cursor-pointer py-2">Evaluación y modelo en vivo</summary><p>CatBoost experimental: {s.shadow?.predictions||0} pronósticos; {s.shadow?.evaluated||0} evaluados.</p>{s.report.candidate&&<p className="mt-2">Error de prueba: {s.report.candidate.log_loss.toFixed(3)} / base {s.report.baseline.log_loss.toFixed(3)}.</p>}<p className="mt-2">En vivo: {data.specialists.find(v=>v.market===s.market&&v.phase==="LIVE")?.active}. Se entrena con capturas reales independientes.</p></details></article>)}</div>}
      {data.specialists && <div className="hidden md:block overflow-x-auto border border-ink-950/10 rounded-lg"><table className="w-full text-xs"><caption className="text-left p-4 text-mute">Modelos independientes · {data.architecture}. Los resultados históricos válidos se reutilizan; los parámetros de v1 no se heredan.</caption><thead className="text-mute bg-ink-950/5"><tr>{["Mercado", "Fase", "Modelo activo", "Ejemplos", "Estado / prueba posterior", "CatBoost experimental"].map(h=><th key={h} className="p-3 text-left">{h}</th>)}</tr></thead><tbody>{data.specialists.map(s=><tr key={`${s.market}-${s.phase}`} className="border-t border-ink-950/5"><td className="p-3">{{result:"Ganador / empate",goals:"Goles",corners:"Córners",yellows:"Amarillas"}[s.market]}</td><td className="p-3">{s.phase==="PRE"?"Previo":"En vivo"}</td><td className="p-3 text-led">{s.active}</td><td className="p-3">{s.report.samples} / {s.report.minimum}</td><td className="p-3"><p>{{awaiting_evidence:"Recopilando evidencia",pending:"Pendiente de evaluación",adopted:"CatBoost adoptado",not_improved:"Se conserva el modelo vigente",awaiting_fresh_test:"Esperando un nuevo bloque de prueba"}[s.report.status] || s.report.status}</p>{s.report.candidate && <p className="text-mute mt-1">Prueba: {s.report.test_matches} partidos · Error candidato {s.report.candidate.log_loss.toFixed(3)} / base {s.report.baseline.log_loss.toFixed(3)} · peso CatBoost {Math.round(s.report.weight*100)}%</p>}</td><td className="p-3 min-w-[180px]">{s.shadow?.state==="running"?<><p className="text-led">En sombra · revisión {s.shadow.revision}</p><p className="text-mute mt-1">{s.shadow.predictions} pronósticos · {s.shadow.evaluated} evaluados</p>{s.shadow.metrics && <p className="text-mute mt-1">Log loss {s.shadow.metrics.log_loss.toFixed(3)} / base {s.shadow.baseline.log_loss.toFixed(3)}</p>}<p className="text-[10px] text-mute mt-2">No interviene en apuestas.</p></>:"Esperando entrenamiento"}</td></tr>)}</tbody></table><p className="p-4 text-[11px] text-mute">CatBoost se entrena por mercado y fase con un mínimo de 200 ejemplos utilizables. Separación temporal: entrenamiento 60%, validación 20%, prueba 20%, con separación entre partidos simultáneos. El peso de la combinación se elige en validación; la prueba posterior decide la adopción. Los datos previos reconstruidos no equivalen a una evaluación prospectiva. En vivo solo se usan capturas guardadas de v2.</p></div>}
      {report && (
        <div className="hidden md:block text-xs text-mute space-y-2 border-t border-ink-950/10 pt-4">
          <p>{report.reason}</p>
          {report.candidate_log_loss != null && (
            <>
              <p>
                Log loss del candidato: {report.candidate_log_loss.toFixed(4)} ·
                Vigente: {report.champion_log_loss.toFixed(4)}. Menor es mejor.
              </p>
              <p>
                {report.train_matches} partidos de entrenamiento /{" "}
                {report.validation_matches} de validación posterior.
              </p>
              <p>
                Entrenamiento hasta {kickoffLabel(report.train_end)} ·
                Validación desde {kickoffLabel(report.validation_start)}
              </p>
            </>
          )}
          <p>
            {report.scope ||
              (data.specialists?.some(s=>s.active_revision) ? "Hay especialistas entrenados con datos históricos. La calibración prospectiva de este despliegue se evalúa por separado." : "La base estadística está activa; los candidatos se entrenan al reunir evidencia suficiente.")}
          </p>
        </div>
      )}
      <details className="md:hidden text-xs text-mute leading-6"><summary className="cursor-pointer py-2 text-paper">Cómo se evalúa el aprendizaje</summary><p>{data.notice}</p><p className="mt-2">Versión: {data.version}. Se necesitan al menos 200 ejemplos por especialista, con entrenamiento, validación y prueba separados en el tiempo. Los candidatos no cambian el modelo activo sin demostrar mejora.</p></details>
      <p className="hidden md:block text-[10px] text-mute leading-5">
        Se calibran probabilidades 1X2 y tasas de goles, córners y amarillas por
        separado para previo/en vivo. Un partido no aparece a la vez en
        entrenamiento y validación; múltiples minutos del mismo encuentro no
        cuentan como partidos distintos. La validación es interna y no garantiza
        mejora futura.
      </p>
    </section>
  );
}


