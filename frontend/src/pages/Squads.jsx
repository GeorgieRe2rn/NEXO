import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Search, ArrowUpRight, Users } from "lucide-react";
import { api, kickoffLabel } from "../api/client";
import usePolling from "../hooks/usePolling";
import { useFeed } from "../components/FeedContext";
import Crest from "../components/Crest";
import StatsTable from "../components/StatsTable";
export default function Squads() {
  const { leagues } = useFeed();
  const [params, setParams] = useSearchParams();
  const code = params.get("liga") || "MX";
  const { data, loading, error, reload } = usePolling(
    () => api.leagueTeams(code),
    code,
    60000,
  );
  const [view, setView] = useState("equipos"),
    [query, setQuery] = useState(""),
    [pos, setPos] = useState("ALL");
  const teams = data?.items || [];
  const players = useMemo(
    () =>
      teams.flatMap((t) =>
        (t.squad || []).map((p) => ({
          ...p,
          team: {
            id: t.id,
            name: t.short_name,
            logo_url: t.logo_url,
            tla: t.tla,
          },
        })),
      ),
    [data],
  );
  const filtered = players.filter(
    (p) =>
      (pos === "ALL" || p.position === pos) &&
      `${p.name} ${p.club}`.toLowerCase().includes(query.toLowerCase()),
  );
  const list = teams.filter((t) =>
    `${t.name} ${t.short_name}`.toLowerCase().includes(query.toLowerCase()),
  );
  const verified = players
    .map((p) => p.verified_at)
    .filter(Boolean)
    .sort()
    .at(-1);
  return (
    <div className="space-y-6">
      <div>
        <p className="eyebrow text-led mb-3">Equipos y jugadores</p>
        <h1 className="page-title">El detalle hace la diferencia.</h1>
        <p className="text-mute text-xs md:text-sm mt-3">
          Plantillas y cifras publicadas por la fuente. Explora{" "}
          {leagues.find((l) => l.code === code)?.name || code}.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {leagues.map((l) => (
          <button
            key={l.code}
            className={`pill ${code === l.code ? "active" : ""}`}
            onClick={() => {
              setParams({ liga: l.code });
              setQuery("");
            }}
          >
            {l.name}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-3 justify-between items-center">
        <div className="flex gap-1 border border-ink-950/10 rounded-lg p-1">
          {[
            ["equipos", "Equipos"],
            ["jugadores", "Jugadores"],
          ].map(([id, label]) => (
            <button
              className={`px-5 py-2 rounded-md text-xs ${view === id ? "bg-ink-950/10 text-paper" : "text-mute"}`}
              key={id}
              onClick={() => setView(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="relative flex-1 sm:flex-none sm:w-72">
          <Search size={15} className="absolute left-3 top-3 text-mute" />
          <input
            className="field pl-9"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar equipo o jugador"
            aria-label="Buscar equipo o jugador"
          />
        </label>
      </div>
      {verified && (
        <p className="text-[10px] text-mute">
          Plantillas consultadas {kickoffLabel(verified)} · Hermosillo. Las
          cifras pertenecen a la temporada indicada por ESPN.
        </p>
      )}
      {error && (
        <div role="alert" className="text-amber text-xs">
          {error} <button onClick={reload}>Reintentar</button>
        </div>
      )}
      {loading ? (
        <div className="grid sm:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-40" />
          ))}
        </div>
      ) : view === "equipos" ? (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {list.map((t) => (
            <Link
              to={`/equipo/${t.id}`}
              key={t.id}
              className="panel rounded-xl p-5 hover:border-led/40 group"
            >
              <div className="flex justify-between items-start mb-5">
                <Crest src={t.logo_url} name={t.name} size={46} />
                <ArrowUpRight
                  size={15}
                  className="text-mute group-hover:text-led"
                />
              </div>
              <h2 className="text-base font-semibold">{t.name}</h2>
              <div className="flex justify-between text-[11px] text-mute mt-2">
                <span>{t.tla}</span>
                <span className="flex items-center gap-1">
                  <Users size={12} />
                  {t.squad_size} verificados
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {[
              ["ALL", "Todos"],
              ["GK", "Porteros"],
              ["DF", "Defensas"],
              ["MF", "Medios"],
              ["FW", "Delanteros"],
            ].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setPos(id)}
                className={`pill ${pos === id ? "active" : ""}`}
              >
                {label}
              </button>
            ))}
            <span className="text-[10px] text-mute ml-auto">
              {filtered.length} jugadores
            </span>
          </div>
          <StatsTable players={filtered} showClub />
        </>
      )}
      {!loading && view === "equipos" && list.length === 0 && (
        <div className="empty-state">
          No se encontraron equipos para esta búsqueda.
        </div>
      )}
      <p className="text-[10px] text-mute leading-5">
        Las plantillas no equivalen a alineaciones confirmadas. Una raya indica
        un dato no proporcionado; las actualizaciones de plantillas se cachean
        durante 24 horas.
      </p>
    </div>
  );
}
