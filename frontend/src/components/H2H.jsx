export default function H2H({ items = [], homeTla, awayTla }) {
  if (!items.length) {
    return <p className="text-slate-400 text-sm">Sin enfrentamientos directos en caché.</p>;
  }
  return (
    <div className="space-y-3">
      {items.map((m) => (
        <div key={m.id} className="flex items-center justify-between rounded-2xl bg-ink-950/5 px-4 py-3">
          <div className="text-xs text-slate-400 w-28">
            {new Date(m.kickoff).toLocaleDateString("es-MX", { year: "numeric", month: "short", day: "2-digit" })}
          </div>
          <div className="flex-1 grid grid-cols-[1fr_auto_1fr] items-center gap-3 font-display">
            <span className={`text-right text-sm ${m.home_tla === homeTla ? "text-sky-300" : "text-paper"}`}>{m.home}</span>
            <span className="font-mono text-lg stat-num px-3 py-1 rounded-xl bg-pitch-800">
              {m.home_goals}–{m.away_goals}
            </span>
            <span className={`text-sm ${m.away_tla === awayTla ? "text-rose-300" : "text-paper"}`}>{m.away}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
