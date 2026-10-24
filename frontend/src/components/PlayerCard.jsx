import { POS } from "../api/client";

function Cell({ label, value }) {
  return (
    <div className="px-2 py-3 text-center border-ink-950/10 border-r last:border-0">
      <p className="stat-num text-3xl text-led leading-none">{value ?? "—"}</p>
      <p className="mt-1 text-[11px] text-mute">{label}</p>
    </div>
  );
}

export default function PlayerCard({ player }) {
  if (!player) {
    return (
      <div className="glass rounded-lg p-6 text-mute text-sm">
        Todavía no hay un destacado con minutos en los últimos cinco partidos.
      </div>
    );
  }
  const t = player.tabla || {};
  const r = player.recent || {};
  return (
    <article className="glass rounded-lg overflow-hidden">
      <div className="flex items-start gap-4 p-4 pitch-stripe">
        <div className="stat-num text-5xl text-line/40 w-14 text-center leading-none">
          {player.shirt_number || "—"}
        </div>
        <div className="min-w-0">
          <p className="text-[11px] text-led tracking-widest uppercase">
            {POS[player.position] || player.position} · {player.club}
          </p>
          <h3 className="font-display text-3xl leading-tight">{player.name}</h3>
          <p className="text-sm text-mute mt-1">
            {player.nationality && player.nationality !== "—" ? player.nationality : ""}
            {player.age ? ` · ${player.age} años` : ""}
            {player.injured ? " · baja" : ""}
          </p>
        </div>
      </div>
      <div className="grid grid-cols-5 border-t border-ink-950/10">
        <Cell label="Goles (5)" value={r.goals ?? t.goles} />
        <Cell label="Asist. (5)" value={r.assists ?? t.asistencias} />
        <Cell label="Rating" value={r.rating_avg ?? t.rating} />
        <Cell label="Tiros" value={r.shots ?? t.tiros} />
        <Cell label="Minutos" value={r.minutes ?? t.minutos} />
      </div>
      <div className="grid grid-cols-5 border-t border-ink-950/10 bg-ink-950/5">
        <Cell label="Goles temp." value={t.goles} />
        <Cell label="Asist. temp." value={t.asistencias} />
        <Cell label="Partidos" value={t.partidos} />
        <Cell label="Amarillas" value={t.amarillas} />
        <Cell label="Rojas" value={t.rojas} />
      </div>
    </article>
  );
}
