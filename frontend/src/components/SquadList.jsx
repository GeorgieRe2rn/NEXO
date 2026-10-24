import { useState } from "react";
import { POS } from "../api/client";

const GROUPS = [
  ["GK", "Porteros"],
  ["DF", "Defensas"],
  ["MF", "Mediocampistas"],
  ["FW", "Delanteros"],
];

function MiniPhoto({ player }) {
  const [ok, setOk] = useState(true);
  const initials = (player.name || "?")
    .split(" ")
    .filter(Boolean)
    .slice(-2)
    .map((p) => p[0])
    .join("");
  if (ok && player.photo_url) {
    return (
      <img
        src={player.photo_url}
        alt=""
        referrerPolicy="no-referrer"
        onError={() => setOk(false)}
        className="h-12 w-12 rounded-xl object-cover bg-pitch-800 ring-1 ring-ink-950/10"
      />
    );
  }
  return (
    <div className="h-12 w-12 rounded-xl grid place-items-center bg-ink-950/5 font-display text-sm ring-1 ring-ink-950/10">
      {initials}
    </div>
  );
}

function Flag({ code }) {
  if (!code || code === "UN") return null;
  return (
    <img
      src={`https://flagcdn.com/w40/${code}.png`}
      alt={code}
      className="h-3.5 w-5 rounded-sm object-cover"
      onError={(e) => {
        e.currentTarget.style.display = "none";
      }}
    />
  );
}

export default function SquadList({ squad = [], compact = false }) {
  if (!squad.length) {
    return <p className="text-sm text-slate-500">Plantilla aún no sincronizada.</p>;
  }
  return (
    <div className="space-y-5">
      {GROUPS.map(([code, label]) => {
        const rows = squad.filter((p) => p.position === code);
        if (!rows.length) return null;
        return (
          <div key={code}>
            <p className="text-[10px] uppercase tracking-[0.28em] text-slate-500 mb-2">
              {label} · {rows.length}
            </p>
            <div className={`grid gap-2 ${compact ? "grid-cols-1" : "sm:grid-cols-2"}`}>
              {rows.map((p) => (
                <div key={p.id} className="flex items-center gap-3 rounded-2xl bg-ink-950/[0.04] border border-ink-950/5 px-3 py-2">
                  <span className="font-mono text-xs text-slate-500 w-6 text-right">{p.shirt_number || "—"}</span>
                  <MiniPhoto player={p} />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium truncate">{p.name}</p>
                    <div className="flex items-center gap-2 text-[11px] text-mute flex-wrap">
                      <Flag code={p.nationality_code} />
                      <span className="truncate">{p.nationality && p.nationality !== "—" ? p.nationality : POS[p.position]}</span>
                      {p.age ? <span>{p.age} años</span> : null}
                      {p.injured ? <span className="text-rust-400">Lesión</span> : null}
                    </div>
                    <p className="text-[11px] text-mute mt-0.5">
                      G {p.season?.goals ?? p.recent?.goals ?? "—"} · A {p.season?.assists ?? p.recent?.assists ?? "—"}
                      {p.season?.played != null ? ` · PJ ${p.season.played}` : ""}
                      {p.recent?.minutes != null ? ` · ${p.recent.minutes} min (5)` : ""}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
