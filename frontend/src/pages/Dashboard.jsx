import { useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  CalendarDays,
  Search,
  ChevronRight,
  Radio,
} from "lucide-react";
import { dateLabel, localDay, localTime, pct } from "../api/client";
import { useFeed } from "../components/FeedContext";
import LeagueFilter from "../components/LeagueFilter";
import FeedStatus from "../components/FeedStatus";
import MatchStatus from "../components/MatchStatus";
import EventTimeline from "../components/EventTimeline";
import Crest from "../components/Crest";
import LiveCoverage from "../components/LiveCoverage";

import { isUpcoming, normalizeSearch } from "../utils/matchFilters";

function Forecast({ prediction, snapshot }) {
  if (snapshot?.markets?.result?.available) {
    const c = snapshot.markets.result.choices;
    prediction = { p_home: c.LOCAL, p_draw: c.EMPATE, p_away: c.VISITANTE };
  }
  if (!prediction)
    return <span className="text-[10px] text-mute">Sin pronóstico previo</span>;
  return (
    <div className="w-full max-w-[200px]">
      <div className="flex h-1.5 rounded-full overflow-hidden gap-0.5">
        <div
          className="bg-led"
          style={{ width: `${prediction.p_home * 100}%` }}
        />
        <div
          className="bg-slate-500"
          style={{ width: `${prediction.p_draw * 100}%` }}
        />
        <div
          className="bg-slate-300"
          style={{ width: `${prediction.p_away * 100}%` }}
        />
      </div>
      <div className="flex justify-between text-[9px] text-mute mt-2">
        <span>L {pct(prediction.p_home)}</span>
        <span>E {pct(prediction.p_draw)}</span>
        <span>V {pct(prediction.p_away)}</span>
      </div>
    </div>
  );
}
export default function Dashboard() {
  const { items, leagues, meta, loading, error, reload } = useFeed();
  const [params, setParams] = useSearchParams();
  const { pathname } = useLocation();
  const onlyLive = pathname === "/en-vivo";
  const league = params.get("liga") || "ALL";
  const selectedDate = params.get("fecha") || "all";
  const [filter, setFilter] = useState("ALL");
  const [expandedLeagues,setExpandedLeagues]=useState({});
  const [query, setQuery] = useState("");
  const today = localDay(meta?.server_time || new Date());
  const now = meta?.server_time || new Date().toISOString();
  const setParam = (key, value) => {
    const next = new URLSearchParams(params);
    value === "all" || value === "ALL"
      ? next.delete(key)
      : next.set(key, value);
    setParams(next);
  };
  const dateBase = new Date(`${today}T12:00:00-07:00`).getTime();
  const dates = Array.from(
    { length: 10 },
    (_, i) => new Date(dateBase + i * 86400000),
  );
  const visible = useMemo(
    () =>
      items.filter((m) => {
        if (league !== "ALL" && m.league.code !== league) return false;
        if (selectedDate !== "all" && localDay(m.kickoff) !== selectedDate)
          return false;
        if ((onlyLive || filter === "LIVE") && (m.status !== "LIVE" || m.stale))
          return false;
        if (!onlyLive && filter === "SCHEDULED" && !isUpcoming(m, now))
          return false;
        if (!onlyLive && filter === "FINISHED" && m.status !== "FINISHED")
          return false;
        if (
          query &&
          !normalizeSearch(`${m.home.name} ${m.away.name} ${m.league.name}`).includes(normalizeSearch(query))
        )
          return false;
        return true;
      }).sort((a,b)=>{const rank={LIVE:0,SCHEDULED:1,FINISHED:2};return (rank[a.status]??3)-(rank[b.status]??3)||new Date(a.kickoff)-new Date(b.kickoff);}),
    [items, league, selectedDate, onlyLive, filter, query, now],
  );
  const grouped = leagues
    .map((l) => [l, visible.filter((m) => m.league.code === l.code)])
    .filter(([, matches]) => matches.length);
  const featured =
    visible.find((m) => m.status === "LIVE" && !m.stale) ||
    visible.find((m) => isUpcoming(m, now)) ||
    visible.at(-1);
  const live = items.filter((m) => m.status === "LIVE" && !m.stale).length;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between gap-4 items-start">
        <div>
          <p className="eyebrow text-led mb-3">
            {onlyLive ? "Centro de seguimiento" : "Tu jornada de fútbol"}
          </p>
          <h1 className="page-title">
            {onlyLive ? "El juego está pasando." : "Conecta los datos. Entiende el juego."}
          </h1>
          <p className="hidden sm:block text-mute text-xs md:text-sm mt-3 max-w-xl leading-relaxed">
            Partidos, resultados y pronósticos.
          </p>
        </div>
      </div>
      <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1 lg:hidden">
        <button
          className={`pill ${league === "ALL" ? "active" : ""}`}
          onClick={() => setParam("liga", "ALL")}
        >
          Todas las ligas
        </button>
        {leagues.map((l) => (
          <button
            className={`pill ${league === l.code ? "active" : ""}`}
            key={l.code}
            onClick={() => setParam("liga", l.code)}
          >
            {l.name}
          </button>
        ))}
      </div>
      <section aria-label="Filtrar partidos" className="space-y-4">
        <div className="flex gap-2 overflow-x-auto no-scrollbar pb-2 items-stretch">
          <button
            onClick={() => setParam("fecha", "all")}
            className={`px-4 py-3 rounded-lg shrink-0 border text-[11px] ${selectedDate === "all" ? "bg-ink-950/10 border-ink-950/30 text-paper" : "border-ink-950/10 text-mute"}`}
          >
            <CalendarDays size={15} className="mx-auto mb-1" />
            Todas
          </button>
          {dates.map((d) => {
            const key = localDay(d);
            return (
              <button
                key={key}
                onClick={() => setParam("fecha", key)}
                className={`rounded-lg shrink-0 min-w-[74px] whitespace-nowrap py-2.5 px-3 text-xs border ${selectedDate === key ? "border-led bg-led/10 text-led" : "border-transparent text-mute hover:bg-ink-950/5"}`}
              >
                <span className="block text-[10px] mb-1 capitalize">
                  {key === today
                    ? "Hoy"
                    : dateLabel(d, {
                        weekday: "short",
                        day: undefined,
                        month: undefined,
                      })}
                </span>
                <span className="font-semibold text-base">{dateLabel(d)}</span>
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap gap-3 justify-between">
          <div className="flex gap-2 overflow-x-auto max-w-full no-scrollbar pb-1">
            {!onlyLive &&
              [
                ["ALL", "Todos"],
                ["LIVE", `En vivo ${live}`],
                ["SCHEDULED", "Próximos"],
                ["FINISHED", "Finalizados"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setFilter(id)}
                  className={`pill ${filter === id ? "active" : ""}`}
                >
                  {id === "LIVE" && <Radio size={13} />} {label}
                </button>
              ))}
            {onlyLive && (
              <span className="pill active">
                <Radio size={13} />
                En vivo · {live}
              </span>
            )}
          </div>
          <label className="relative min-w-[220px] flex-1 sm:flex-none">
            <Search className="absolute left-3 top-3 text-mute" size={15} />
            <input
              className="field pl-9"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar equipo o competición"
              aria-label="Buscar equipo o competición"
            />
          </label>
        </div>
      </section>
      {error && (
        <div
          role="alert"
          className="p-4 rounded-lg border border-amber/30 text-amber text-xs flex justify-between gap-3"
        >
          <span>{error} Los datos guardados pueden estar desactualizados.</span>
          <button onClick={reload}>Reintentar</button>
        </div>
      )}
      {loading && (
        <div className="space-y-3" role="status" aria-label="Cargando partidos">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-24" />
          ))}
        </div>
      )}
      {!loading && visible.length === 0 && (
        <div className="empty-state">
          <CalendarDays size={28} className="mx-auto mb-4 opacity-50" />
          <h2 className="text-paper font-medium mb-2">
            {onlyLive
              ? "No hay partidos en vivo confirmados"
              : "No hay encuentros para esta selección"}
          </h2>
          <p className="text-xs leading-6">
            {query
              ? "Prueba con otro equipo o competición."
              : "Consulta otra fecha o la jornada completa. No se generan partidos de relleno."}
          </p>
          <button
            onClick={() => {
              setParam("fecha", "all");
              setFilter("ALL");
              setQuery("");
            }}
            className="text-led text-xs mt-4"
          >
            Limpiar filtros
          </button>
        </div>
      )}

      {featured && (
        <section className="panel rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-ink-950/10">
            <div className="flex gap-2 items-center text-xs">
              {featured.league.logo_url && (
                <img
                  className="w-4 h-4 object-contain"
                  src={featured.league.logo_url}
                  alt=""
                />
              )}
              {featured.league.name}
              <span className="text-mute hidden sm:inline">
                {" "}
                / Partido destacado
              </span>
            </div>
            <Link
              to={`/match/${featured.id}`}
              className="text-led text-[11px] inline-flex items-center gap-1"
            >
              Ver partido <ArrowRight size={13} />
            </Link>
          </div>
          <div className="grid">
            <div className="min-w-0">
            <Link
              to={`/match/${featured.id}`}
              className="py-7 px-4 sm:px-7 grid grid-cols-[1fr_auto_1fr] gap-3 items-center"
            >
              <div className="flex flex-col sm:flex-row items-center gap-3 justify-end text-center">
                <span className="font-semibold text-sm sm:text-lg order-2 sm:order-1">
                  {featured.home.short_name}
                </span>
                <Crest
                  src={featured.home.logo_url}
                  name={featured.home.name}
                  size={54}
                />
              </div>
              <div className="text-center min-w-[95px]">
                <MatchStatus match={featured} />
                <p
                  key={`${featured.home_goals}-${featured.away_goals}`}
                  className="stat-num text-4xl md:text-5xl mt-3 score-flash"
                >
                  {featured.home_goals != null && featured.away_goals != null
                    ? `${featured.home_goals} – ${featured.away_goals}`
                    : localTime(featured.kickoff)}
                </p>
                <p className="text-[10px] text-mute mt-2">
                  {dateLabel(featured.kickoff)} · UTC−7
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-3 items-center text-center">
                <Crest
                  src={featured.away.logo_url}
                  name={featured.away.name}
                  size={54}
                />
                <span className="font-semibold text-sm sm:text-lg">
                  {featured.away.short_name}
                </span>
              </div>
            </Link>
            {featured.status === "LIVE" && <LiveCoverage key={featured.id} match={featured}/>}
            </div>

          </div>
        </section>
      )}
      <div className="space-y-5">
        {grouped.map(([l, matches]) => (
          <section key={l.code} className="panel rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 flex items-center gap-2 border-b border-ink-950/10 bg-ink-950/[.015]">
              {l.logo_url && (
                <img
                  src={l.logo_url}
                  alt=""
                  className="h-5 w-5 object-contain"
                />
              )}
              <h2 className="text-sm font-semibold">{l.name}</h2>
              <Link to={`/posiciones?liga=${l.code}`} className="text-[10px] text-led ml-2">Tabla de posiciones ↗</Link>
              <span className="text-[10px] text-mute ml-2">
                {matches.length} partidos
              </span>
              <span className="text-[9px] text-mute ml-auto hidden md:block">
                LOCAL / EMPATE / VISITANTE
              </span>
            </div>
            <div className="divide-y divide-ink-950/5">
              {matches.slice(0,expandedLeagues[l.code]?matches.length:8).map((m) => (
                <Link
                  to={`/match/${m.id}`}
                  key={m.id}
                  className="grid grid-cols-[52px_1fr_60px_1fr_14px] md:grid-cols-[74px_1fr_65px_1fr_150px_14px] gap-2 md:gap-4 items-center py-4 px-3 md:px-5 hover:bg-ink-950/[.025]"
                >
                  <div className="text-[10px] text-mute">
                    <p className="capitalize">{dateLabel(m.kickoff)}</p>
                    <p className="mt-1 text-paper">{localTime(m.kickoff)}</p>
                  </div>
                  <div className="flex gap-2 items-center justify-end text-right min-w-0">
                    <span className="text-[11px] sm:text-xs truncate">
                      {m.home.short_name}
                    </span>
                    <Crest src={m.home.logo_url} name={m.home.name} size={25} />
                  </div>
                  <div className="text-center">
                    <p
                      key={`${m.home_goals}-${m.away_goals}`}
                      className={`stat-num text-base ${m.status === "LIVE" && !m.stale ? "text-led" : ""}`}
                    >
                      {m.home_goals != null && m.away_goals != null
                        ? `${m.home_goals} – ${m.away_goals}`
                        : "—"}
                    </p>
                    <span className="text-[8px] text-mute">
                      {m.status === "LIVE" && !m.stale
                        ? m.live?.clock
                        : m.status_label}
                    </span>
                  </div>
                  <div className="flex gap-2 items-center min-w-0">
                    <Crest src={m.away.logo_url} name={m.away.name} size={25} />
                    <span className="text-[11px] sm:text-xs truncate">
                      {m.away.short_name}
                    </span>
                  </div>
                  <div className="hidden md:flex justify-end">
                    <Forecast prediction={m.prediction} snapshot={m.forecast} />
                  </div>
                  <ChevronRight size={13} className="text-mute" />
                </Link>
              ))}
            </div>
            {matches.length>8&&<button className="w-full py-3 text-xs text-led border-t border-ink-950/10 hover:bg-ink-950/5" onClick={()=>setExpandedLeagues(v=>({...v,[l.code]:!v[l.code]}))}>{expandedLeagues[l.code]?"Mostrar menos":`Ver ${matches.length-8} partidos más`}</button>}
          </section>
        ))}
      </div>

    </div>
  );
}


