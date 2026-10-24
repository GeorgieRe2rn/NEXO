import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, MapPin, ShieldCheck } from "lucide-react";
import { api, kickoffLabel, pct, localTime } from "../api/client";
import usePolling from "../hooks/usePolling";
import Crest from "../components/Crest";
import MatchStatus from "../components/MatchStatus";
import LiveStats from "../components/LiveStats";
import LiveCoverage from "../components/LiveCoverage";
import EventTimeline from "../components/EventTimeline";
import FormPills from "../components/FormPills";
import StatsTable from "../components/StatsTable";
import PredictionMatrix from "../components/PredictionMatrix";
import H2H from "../components/H2H";

import { useFeed } from "../components/FeedContext";
import ForecastMarkets from "../components/ForecastMarkets";

export default function MatchDetail() {
  const { id } = useParams();
  const { account } = useFeed();
  const { data, error, loading, reload } = usePolling(() => api.match(id), id);
  const match = data ? { ...data, stale: data.stale || !!error } : null;
  const [tab, setTab] = useState("resumen");
  if (!match)
    return (
      <div className="space-y-4">
        <Link to="/" className="text-mute text-xs">
          ← Volver a la jornada
        </Link>
        {loading ? (
          <div
            className="skeleton h-80"
            role="status"
            aria-label="Cargando partido"
          />
        ) : (
          <div className="empty-state">
            <p>No se pudo cargar este encuentro.</p>
            <button className="text-led mt-4" onClick={reload}>
              Reintentar
            </button>
          </div>
        )}
      </div>
    );
  const p = match.prediction;
  const score =
    match.home_goals != null && match.away_goals != null
      ? `${match.home_goals} – ${match.away_goals}`
      : "VS";
  const tabs = [
    ["resumen", "Resumen"],
    ["stats", "Estadísticas"],
    ["plantillas", "Plantillas"],
    ["analisis", "Análisis previo"],
  ];
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center gap-3">
        <Link
          to="/"
          className="flex items-center gap-2 text-xs text-mute hover:text-paper"
        >
          <ArrowLeft size={14} />
          Jornada <span className="text-ink-950/20">/</span>
          {match.league.name}
        </Link>
        <span className="text-[10px] text-mute">
          {match.verified_at
            ? `Consultado ${localTime(match.verified_at)} · ESPN`
            : "Sin verificación actual"}
        </span>
      </div>
      {error && (
        <p role="alert" className="text-amber text-xs">
          {error} La información puede estar desactualizada.
        </p>
      )}
      <section className="panel rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-ink-950/10 flex flex-wrap gap-3 justify-between text-[10px] text-mute">
          <span>
            {match.league.name} · {kickoffLabel(match.kickoff)} · Hermosillo
          </span>
          <span className="flex items-center gap-1">
            <MapPin size={11} />
            {match.venue || "Estadio por confirmar"}
          </span>
        </div>
        <div className="py-9 px-3 md:px-8 grid grid-cols-[1fr_auto_1fr] items-center gap-2 md:gap-8">
          <Link
            to={`/equipo/${match.home.id}`}
            className="flex flex-col items-center gap-3 text-center"
          >
            <Crest src={match.home.logo_url} name={match.home.name} size={70} />
            <h1 className="font-display text-base md:text-2xl">
              {match.home.name}
            </h1>
            <span className="text-mute text-[10px]">LOCAL</span>
          </Link>
          <div className="text-center">
            <MatchStatus match={match} />
            <p
              key={score}
              className="stat-num text-4xl md:text-6xl mt-4 score-flash"
            >
              {score}
            </p>
            {score === "VS" && (
              <p className="text-mute text-xs mt-3">
                {localTime(match.kickoff)} · UTC−7
              </p>
            )}
            {match.live?.time_confirmed === false && (
              <p className="text-amber text-[10px] mt-3">
                Horario por confirmar
              </p>
            )}
          </div>
          <Link
            to={`/equipo/${match.away.id}`}
            className="flex flex-col items-center gap-3 text-center"
          >
            <Crest src={match.away.logo_url} name={match.away.name} size={70} />
            <h2 className="font-display text-base md:text-2xl">
              {match.away.name}
            </h2>
            <span className="text-mute text-[10px]">VISITANTE</span>
          </Link>
        </div>
        <nav
          aria-label="Secciones del partido"
          className="flex overflow-x-auto no-scrollbar border-t border-ink-950/10 px-4 md:px-6 gap-6"
        >
          {tabs.map(([id, label]) => (
            <button
              onClick={() => setTab(id)}
              key={id}
              className={`text-xs whitespace-nowrap py-4 border-b-2 ${tab === id ? "border-led text-led" : "border-transparent text-mute"}`}
            >
              {label}
            </button>
          ))}
        </nav>
      </section>
      {match.status === "LIVE" && <LiveCoverage key={match.id} match={match} />}
      {match.stale && match.status === "LIVE" && (
        <p className="text-amber text-xs panel p-4 rounded-lg">
          El proveedor no ha confirmado el estado recientemente. El marcador y
          minuto mostrados son los últimos recibidos.
        </p>
      )}
      {match.live?.score_pending_confirmation && (
        <p className="text-amber text-xs panel p-4 rounded-lg" role="status">
          La fuente reporta un nuevo evento de gol y todavía está confirmando el
          marcador. Se actualizará en la siguiente consulta.
        </p>
      )}
      {account?.authenticated && (
        <>
          <section
            className="space-y-4"
            aria-label="Pronóstico previo estadístico"
          >
            <div>
              <h2 className="font-display text-2xl">Pronóstico previo</h2>
              <span className="text-[10px] text-mute">Estimación experimental</span>
            </div>
            {!match.forecasts?.PRE && p ? (
              <div className="panel rounded-xl p-5 text-sm">
                <p>
                  Local: {pct(p.p_home)} · Empate: {pct(p.p_draw)} · Visitante:{" "}
                  {pct(p.p_away)}
                </p>
                <p className="text-xs text-mute mt-3">
                  Previo original conservado. Los otros mercados no se
                  registraron antes del inicio; no se reconstruyen
                  retroactivamente.
                </p>
              </div>
            ) : (
              <ForecastMarkets snapshot={match.forecasts?.PRE} matchId={id} technical={false} />
            )}
          </section>
          {(match.status === "LIVE" || match.forecasts?.LIVE) && <section
            className="space-y-4"
            aria-label="Pronóstico en vivo estadístico"
          >
            <h2 className="font-display text-2xl">Pronóstico en vivo</h2>

            {match.status === "LIVE" && !match.forecasts?.live_current && (
              <p className="text-xs text-amber" role="status">
                Esperando un pronóstico actualizado.
              </p>
            )}
            {match.forecasts?.LIVE ? (
              <ForecastMarkets snapshot={match.forecasts.LIVE} matchId={id} technical={false} />
            ) : (
              <p className="empty-state text-xs">
                Disponible cuando el encuentro comience y existan datos
                confirmados.
              </p>
            )}
          </section>}
          <section
            className="panel rounded-xl p-5 space-y-3"
            aria-label="Apuestas automáticas"
          >
            <h2 className="font-display text-2xl">
              Apuestas automáticas del modelo
            </h2>
            <p className="text-xs text-mute">Simulación sin dinero.</p>
            <Link className="text-led text-sm" to="/mis-pronosticos">
              Ver apuestas automáticas y resultados →
            </Link>
          </section>
        </>
      )}
      {(tab === "resumen" || tab === "stats") && (
        <div
          className={`grid gap-5 ${tab === "resumen" ? (match.status === "LIVE" ? "" : "xl:grid-cols-[1fr_1fr_.85fr]") : "lg:grid-cols-2"}`}
        >
          {tab === "resumen" && match.status !== "LIVE" && (
            <section className={`${match.live?.events?.length ? "" : "hidden sm:block"} panel rounded-xl p-5`}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold">
                  Cronología del partido
                </h2>
                <span className="text-[9px] text-mute">ESPN</span>
              </div>
              <div className="max-h-[480px] overflow-y-auto">
                <EventTimeline events={match.live?.events} />
              </div>
              <p className="text-[10px] text-mute mt-3">
                Los comentarios originales del proveedor pueden estar en inglés.
              </p>
            </section>
          )}
          {!(match.status === "LIVE" && tab === "resumen") && <section className={`${match.status === "SCHEDULED" && tab === "resumen" ? "hidden sm:block" : ""} panel rounded-xl p-5`}>
            <h2 className="text-sm font-semibold mb-6">
              Estadísticas del partido
            </h2>
            <LiveStats
              stats={match.live?.stats}
              home={match.home.short_name}
              away={match.away.short_name}
            />
            {match.live?.details_at && (
              <p className="text-[10px] text-mute mt-4">
                Último detalle: {localTime(match.live.details_at)} · Hermosillo
              </p>
            )}
          </section>}
          <section className="panel rounded-xl p-5 space-y-5">
            <h2 className="text-sm font-semibold">Cómo llegan al encuentro</h2>
            {[match.home, match.away].map((t) => (
              <div key={t.id}>
                <p className="text-xs text-mute mb-3">
                  {t.short_name} · {t.form?.matches_used || 0}/5 partidos
                </p>
                <FormPills form={t.form?.form_string} />
              </div>
            ))}
            {!account?.authenticated && <div className="border-t border-ink-950/10 pt-5">
              <p className="text-xs font-semibold mb-3">
                Pronóstico previo al inicio
              </p>
              {p ? (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      ["Local", p.p_home],
                      ["Empate", p.p_draw],
                      ["Visitante", p.p_away],
                    ].map(([label, value]) => (
                      <div
                        key={label}
                        className="bg-ink-950/5 rounded-md p-3 text-center"
                      >
                        <p className="text-[9px] text-mute">{label}</p>
                        <p className="text-lg stat-num mt-1 text-led">
                          {pct(value)}
                        </p>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-mute mt-3">
                    {p.model_version} · {kickoffLabel(p.computed_at)}
                  </p>
                </>
              ) : (
                <p className="text-xs text-mute leading-6">
                  Sin pronóstico previo disponible. Se requieren cinco
                  encuentros verificados de cada equipo y un cálculo anterior al
                  inicio.
                </p>
              )}
            </div>}
          </section>
        </div>
      )}
      {tab === "plantillas" && (
        <div className="space-y-6">
          <p className="text-xs text-amber panel p-4 rounded-lg">
            Plantillas registradas · alineaciones por confirmar.
          </p>
          {[match.home, match.away].map((t) => (
            <section key={t.id}>
              <h2 className="text-base font-semibold mb-4 flex items-center gap-2">
                <Crest src={t.logo_url} name={t.name} size={24} />
                {t.name}
              </h2>
              <StatsTable players={t.squad} />
            </section>
          ))}
        </div>
      )}
      {tab === "analisis" && (
        <div className="space-y-5">
          {p ? (
            <>
              <PredictionMatrix match={match} />
              {p.model_version?.startsWith("global-") && <section className="panel rounded-xl p-5 space-y-4">
                <h2 className="font-semibold text-sm">Antecedentes publicados usados en el previo</h2>
                <div className="grid md:grid-cols-2 gap-5">
                  {[[match.home, p.explanation.home_history], [match.away, p.explanation.away_history]].map(([team, rows]) => <div key={team.id}>
                    <h3 className="text-sm text-led mb-3">{team.name}</h3>
                    {(rows || []).map(row => <a key={row.id} href={row.source_url} target="_blank" rel="noreferrer" className="block text-xs text-mute border-b border-ink-950/5 py-2">{kickoffLabel(row.kickoff)} · {row.opponent} · {row.goals}–{row.goals_against} · {row.competition} ↗</a>)}
                  </div>)}
                </div>
              </section>}
              <div className="panel rounded-xl p-5">
                <h2 className="font-semibold text-sm mb-4">
                  Total de goles · pronóstico previo
                </h2>
                <div className="flex gap-8 text-sm">
                  <span>
                    Más de 2.5{" "}
                    <strong className="text-led ml-2">
                      {pct(p.p_over_25)}
                    </strong>
                  </span>
                  <span>
                    Menos de 2.5{" "}
                    <strong className="text-led ml-2">
                      {pct(p.p_under_25)}
                    </strong>
                  </span>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">
              Este encuentro no tiene un pronóstico previo válido. No se
              reconstruyen predicciones después de conocer el resultado.
            </div>
          )}
          <section className="panel rounded-xl p-5">
            <h2 className="text-sm font-semibold mb-5">
              Enfrentamientos directos registrados
            </h2>
            <H2H
              items={match.h2h}
              homeTla={match.home.tla}
              awayTla={match.away.tla}
            />
          </section>
        </div>
      )}
      <div className="flex flex-wrap justify-between gap-3 text-[10px] text-mute">
        <span>
          ESPN · Horarios de Hermosillo
        </span>
        {match.live?.source_url && (
          <a
            href={match.live.source_url}
            target="_blank"
            rel="noreferrer"
            className="text-led flex items-center gap-1"
          >
            Consultar fuente <ArrowUpRight size={11} />
          </a>
        )}
      </div>
    </div>
  );
}


