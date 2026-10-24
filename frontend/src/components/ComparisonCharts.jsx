import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const TOOLTIP = {
  background: "#17212B",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 12,
  color: "#e2e8f0",
};

export default function ComparisonCharts({ home, away }) {
  const hf = home.form || {};
  const af = away.form || {};
  const rows = [
    { k: "Goles a favor", home: hf.gf_avg, away: af.gf_avg },
    { k: "Goles en contra", home: hf.ga_avg, away: af.ga_avg },
    { k: "xG", home: hf.xg_avg, away: af.xg_avg },
    { k: "Tiros", home: hf.shots_avg, away: af.shots_avg },
    { k: "A puerta", home: hf.sot_avg, away: af.sot_avg },
    { k: "Posesión %", home: hf.possession_avg, away: af.possession_avg },
    { k: "Córners", home: hf.corners_avg, away: af.corners_avg },
  ];

  const homeSlices = (hf.breakdown?.slices || []).slice().reverse();
  const awaySlices = (af.breakdown?.slices || []).slice().reverse();
  const lines = [0, 1, 2, 3, 4].map((i) => ({
    k: `P${i + 1}`,
    [home.short_name]: homeSlices[i]?.goals_for ?? 0,
    [away.short_name]: awaySlices[i]?.goals_for ?? 0,
  }));

  return (
    <div className="grid lg:grid-cols-2 gap-5">
      <div className="glass rounded-3xl p-5">
        <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Promedios last-5</p>
        <h3 className="font-display text-xl mt-1 mb-4">Comparativa de forma reciente</h3>
        <div className="h-[320px]">
          <ResponsiveContainer>
            <BarChart data={rows} layout="vertical" margin={{ left: 24, right: 12 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" horizontal={false} />
              <XAxis type="number" stroke="#64748b" fontSize={11} />
              <YAxis type="category" dataKey="k" stroke="#94a3b8" fontSize={11} width={110} />
              <Tooltip contentStyle={TOOLTIP} />
              <Legend />
              <Bar dataKey="home" name={home.short_name} fill="#D85722" radius={[0, 6, 6, 0]} />
              <Bar dataKey="away" name={away.short_name} fill="#74899B" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="glass rounded-3xl p-5">
        <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Goles marcados por partido</p>
        <h3 className="font-display text-xl mt-1 mb-4">Serie de los últimos 5</h3>
        <div className="h-[320px]">
          <ResponsiveContainer>
            <BarChart data={lines}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="k" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP} />
              <Legend />
              <Bar dataKey={home.short_name} fill="#D85722" radius={[6, 6, 0, 0]} />
              <Bar dataKey={away.short_name} fill="#74899B" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
