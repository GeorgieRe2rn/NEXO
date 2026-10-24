const ROWS = [
  ["possession", "Posesión", "%"],
  ["shots", "Tiros totales", ""],
  ["shots_on_target", "Tiros a puerta", ""],
  ["corners", "Córners", ""],
  ["yellows", "Tarjetas amarillas", ""],
  ["reds", "Tarjetas rojas", ""],
  ["fouls", "Faltas", ""],
];
export default function LiveStats({ stats, home, away }) {
  return (
    <div className="space-y-5">
      <div className="flex justify-between text-xs text-mute">
        <span>{home}</span>
        <span>{away}</span>
      </div>
      {ROWS.map(([key, label, suffix]) => {
        const h = stats?.home?.[key],
          a = stats?.away?.[key];
        const total = (h ?? 0) + (a ?? 0);
        return (
          <div key={key}>
            <div className="flex items-center justify-between text-xs mb-2">
              <span className="stat-num text-sm w-10">
                {h == null ? "—" : `${h}${suffix}`}
              </span>
              <span className="text-mute">{label}</span>
              <span className="stat-num text-sm w-10 text-right">
                {a == null ? "—" : `${a}${suffix}`}
              </span>
            </div>
            <div className="flex h-1.5 rounded-full overflow-hidden gap-1 bg-ink-950/5">
              <div
                className="bg-led rounded-full"
                style={{
                  width: `${total ? ((h ?? 0) / total) * 100 : 50}%`,
                  opacity: h == null ? 0.1 : 1,
                }}
              />
              <div
                className="bg-slate-500 rounded-full flex-1"
                style={{ opacity: a == null ? 0.1 : 1 }}
              />
            </div>
          </div>
        );
      })}
      <p className="text-[10px] text-mute">
        — indica que la fuente todavía no proporciona ese dato.
      </p>
    </div>
  );
}
