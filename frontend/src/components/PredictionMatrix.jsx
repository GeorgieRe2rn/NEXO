import FormPills from "./FormPills";

function Cell({ label, value, sub }) {
  return (
    <div className="rounded-2xl bg-ink-950/[0.04] border border-ink-950/5 px-4 py-3">
      <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">{label}</p>
      <p className="mt-1 font-display text-xl">{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
    </div>
  );
}

export default function PredictionMatrix({ match }) {
  const h = match.home.form || {};
  const a = match.away.form || {};
  const p = match.prediction || {};
  return (
    <div className="glass rounded-3xl p-5 md:p-6">
      <p className="text-[11px] uppercase tracking-[0.28em] text-gold-400">Matriz de predicción</p>
      <h3 className="font-display text-2xl mt-1">Conocimiento extraído (last-5)</h3>
      <div className="mt-5 grid md:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-sky-400/20 bg-sky-400/5 p-4">
          <p className="text-xs uppercase tracking-widest text-sky-300">Forma local</p>
          <div className="mt-2"><FormPills form={h.form_string} /></div>
          <p className="mt-2 font-mono text-sm text-slate-300">{h.points ?? 0} pts · {h.matches_used ?? 0} partidos</p>
        </div>
        <div className="rounded-2xl border border-rose-400/20 bg-rose-400/5 p-4">
          <p className="text-xs uppercase tracking-widest text-rose-300">Forma visitante</p>
          <div className="mt-2"><FormPills form={a.form_string} /></div>
          <p className="mt-2 font-mono text-sm text-slate-300">{a.points ?? 0} pts · {a.matches_used ?? 0} partidos</p>
        </div>
      </div>
      <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Cell label="Media goles local" value={h.gf_avg?.toFixed?.(2) ?? "—"} sub={`xG ${h.xg_avg?.toFixed?.(2) ?? "—"}`} />
        <Cell label="Media goles visitante" value={a.gf_avg?.toFixed?.(2) ?? "—"} sub={`xG ${a.xg_avg?.toFixed?.(2) ?? "—"}`} />
        <Cell label="λ local" value={p.lambda_home?.toFixed?.(2) ?? "—"} sub="Goles esperados Poisson" />
        <Cell label="λ visitante" value={p.lambda_away?.toFixed?.(2) ?? "—"} sub="Goles esperados Poisson" />
        <Cell label="Ataque local" value={h.attack_index?.toFixed?.(2) ?? "—"} />
        <Cell label="Ataque visitante" value={a.attack_index?.toFixed?.(2) ?? "—"} />
        <Cell label="Defensa local" value={h.defense_index?.toFixed?.(2) ?? "—"} sub="Menor = más sólida" />
        <Cell label="Defensa visitante" value={a.defense_index?.toFixed?.(2) ?? "—"} sub="Menor = más sólida" />
      </div>
    </div>
  );
}
