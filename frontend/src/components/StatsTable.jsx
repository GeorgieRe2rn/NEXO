import { POS } from "../api/client";
import Crest from "./Crest";

function Flag({ code }) {
  if (!code || code === "UN") return null;
  return (
    <img
      src={`https://flagcdn.com/w40/${code}.png`}
      alt=""
      className="h-3.5 w-5 inline-block rounded-sm object-cover"
      onError={(e) => {
        e.currentTarget.style.display = "none";
      }}
    />
  );
}

function n(v) {
  return v === null || v === undefined || v === "" ? "—" : v;
}

export default function StatsTable({ players = [], showClub = false }) {
  if (!players.length) {
    return <p className="text-sm text-mute p-4">No hay jugadores en esta lista.</p>;
  }
  return (
    <div className="overflow-x-auto glass rounded-lg">
      <table className="w-full text-sm">
        <thead className="text-[11px] uppercase tracking-wider text-mute bg-ink-950/5">
          <tr>
            {showClub && <th className="text-left px-3 py-2 font-medium">Club</th>}
            <th className="text-right px-2 py-2 font-medium">#</th>
            <th className="text-left px-3 py-2 font-medium">Jugador</th>
            <th className="text-left px-2 py-2 font-medium">Pos</th>
            <th className="text-right px-2 py-2 font-medium">Edad</th>
            <th className="text-right px-2 py-2 font-medium">PJ</th>
            <th className="text-right px-2 py-2 font-medium">Goles</th>
            <th className="text-right px-2 py-2 font-medium">Asist.</th>
            <th className="text-right px-2 py-2 font-medium">Min</th>
            <th className="text-right px-2 py-2 font-medium">Tiros</th>
            <th className="text-right px-2 py-2 font-medium" title="Tiros a puerta">TP</th>
            <th className="text-right px-2 py-2 font-medium">Titular</th>
            <th className="text-right px-2 py-2 font-medium">Atajadas</th>
            <th className="text-right px-2 py-2 font-medium" title="Porterías a cero">PC</th>
            <th className="text-right px-2 py-2 font-medium">xG</th>
            <th className="text-right px-2 py-2 font-medium">Rating</th>
            <th className="text-right px-2 py-2 font-medium">TA</th>
            <th className="text-right px-2 py-2 font-medium">TR</th>
            {["Faltas", "Faltas recibidas", "Autogoles", "Ingresos de suplente", "Fuera de juego", "Tiros recibidos", "Goles recibidos"].map(label=><th key={label} className="text-right px-2 py-2 font-medium whitespace-nowrap">{label}</th>)}
            <th className="text-left px-3 py-2 font-medium">Estado</th>
          </tr>
        </thead>
        <tbody>
          {players.map((p) => {
            const t = p.tabla || {};
            return (
              <tr key={p.id} className="border-t border-ink-950/5 hover:bg-led/5">
                {showClub && (
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Crest src={p.team?.logo_url} name={p.team?.name} size={22} />
                      <span className="text-xs">{p.team?.tla || p.club}</span>
                    </div>
                  </td>
                )}
                <td className="px-2 py-2 text-right stat-num text-mute">{p.shirt_number || "—"}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2 min-w-[160px]">
                    {p.photo_url ? (
                      <img
                        src={p.photo_url}
                        alt=""
                        referrerPolicy="no-referrer"
                        className="h-8 w-8 rounded-full object-cover bg-ink-950/5"
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
                      />
                    ) : (
                      <span className="h-8 w-8 rounded-full bg-ink-950/5 grid place-items-center text-[10px] text-mute">
                        {(p.name || "?").split(" ").map((x) => x[0]).slice(-2).join("")}
                      </span>
                    )}
                    <Flag code={p.nationality_code} />
                    <span className="font-medium">{p.name}</span>
                  </div>
                </td>
                <td className="px-2 py-2 text-mute">{POS[p.position] || p.position}</td>
                <td className="px-2 py-2 text-right stat-num">{n(p.age)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.partidos)}</td>
                <td className="px-2 py-2 text-right stat-num text-led">{n(t.goles)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.asistencias)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.minutos)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.tiros)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.tiros_puerta)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.titular)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.atajadas)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.vallas)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.xg)}</td>
                <td className="px-2 py-2 text-right stat-num">{n(t.rating)}</td>
                <td className="px-2 py-2 text-right stat-num text-amber">{n(t.amarillas)}</td>
                <td className="px-2 py-2 text-right stat-num text-rust-500">{n(t.rojas)}</td>
                {["faltas", "faltas_recibidas", "autogoles", "suplente", "fueras_juego", "tiros_recibidos", "goles_recibidos"].map(key=><td key={key} className="px-2 py-2 text-right stat-num">{n(t[key])}</td>)}
                <td className="px-3 py-2 text-xs">{p.injured ? <span className="text-rust-400">{p.injury || "Lesión reportada"}</span> : "Sin lesión reportada"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
