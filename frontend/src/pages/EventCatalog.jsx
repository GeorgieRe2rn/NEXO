import { useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { api, kickoffLabel, localDay, localTime } from "../api/client";
import { useFeed } from "../components/FeedContext";
import usePolling from "../hooks/usePolling";
import { normalizeSearch } from "../utils/matchFilters";
const SPORTS = { soccer: "Fútbol · competiciones compatibles con la API" };
const STATUS = {
  SCHEDULED: "Programado",
  LIVE: "En vivo",
  FINISHED: "Finalizado",
  POSTPONED: "Pospuesto",
  CANCELLED: "Cancelado",
  DELAYED: "Retrasado",
  SUSPENDED: "Suspendido",
};
export default function EventCatalog() {
  const { account, meta } = useFeed();
  const [params, setParams] = useSearchParams();
  const today = localDay(meta?.server_time || new Date());
  const tomorrow = localDay(
    new Date(new Date(`${today}T12:00:00-07:00`).getTime() + 86400000),
  );
  const day = params.get("fecha") || today;
  const referenceOnly = false;
  const sport = params.get("deporte") || "soccer";
  const [competition, setCompetition] = useState("ALL"),
    [query, setQuery] = useState(""),
    [status, setStatus] = useState("ALL"),
    [page, setPage] = useState(1);
  const { data, error, loading, reload } = usePolling(
    () =>
      account?.authenticated ? api.catalog(day, sport) : Promise.resolve(null),
    `${!!account?.authenticated}:${day}:${sport}`,
    60000,
  );
  const update = (key, value) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next);
  };
  useEffect(() => {
    setCompetition("ALL");
    setPage(1);
  }, [day, sport, referenceOnly]);
  useEffect(() => setPage(1), [competition, query, status, referenceOnly]);
  if (!account) return <p className="text-xs text-mute">Comprobando sesión…</p>;
  if (!account.authenticated)
    return <Navigate to="/admin/login?volver=%2Fcartelera" replace />;
  const sourceItems = (data?.items || []).filter(
    (e) => !referenceOnly || !!e.draftea_reference,
  );
  const competitions = [
    ...new Set(sourceItems.map((e) => e.competition.name)),
  ].sort();
  const items = (data?.items || []).filter(
    (e) =>
      (!referenceOnly || !!e.draftea_reference) &&
      (competition === "ALL" || e.competition.name === competition) &&
      (status === "ALL" || e.status === status) &&
      normalizeSearch(`${e.home} ${e.away} ${e.competition.name}`).includes(normalizeSearch(query)),
  );
  const pages = Math.max(1, Math.ceil(items.length / 40));
  const current = Math.min(page, pages);
  return (
    <div className="space-y-5">
      <header>
        <p className="eyebrow text-led mb-3">
          Calendario · Cinco ligas originales
        </p>
        <h1 className="page-title">Cartelera de partidos.</h1>
        <p className="text-xs text-mute leading-6 mt-3">
          Competiciones compatibles con la API y el motor de fútbol. Los previos
          con historial suficiente generan apuestas académicas solo para mercados con datos suficientes en tu cuenta.
          Fecha y hora de Hermosillo; los datos insuficientes se indican en cada encuentro.
        </p>
      </header>
      <div className="panel rounded-xl p-4 text-xs text-amber leading-6">
        <strong>Referencia de Draftea: capturas aportadas.</strong> Los partidos
        se cruzan con el calendario de ESPN. Los momios son los visibles en tus
        imágenes del 15 de octubre, no precios actuales; la disponibilidad debe
        comprobarse en Draftea. Un favorito por precio no es una apuesta segura
        ni implica valor esperado positivo.
      </div>
      <section
        className="panel rounded-xl p-4 space-y-4"
        aria-label="Filtros de cartelera"
      >
        <div className="flex flex-wrap gap-3">
          <button
            className="text-xs text-led"
            onClick={() => update("fecha", today)}
          >
            Hoy
          </button>
          <button
            className="text-xs text-led"
            onClick={() => update("fecha", tomorrow)}
          >
            Mañana
          </button>
          <button className="text-xs text-led ml-auto" onClick={reload}>
            Actualizar
          </button>
        </div>
        <label className="text-xs text-mute block">
          Origen
          <select
            aria-label="Origen de cartelera"
            className="field w-full mt-2"
            value={referenceOnly ? "capturas" : "todos"}
            onChange={(e) => update("origen", e.target.value)}
          >
            <option value="capturas">
              Solo partidos de las capturas de Draftea
            </option>
            <option value="todos">Todo el calendario de la fuente</option>
          </select>
        </label>
        <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <label className="text-xs text-mute">
            Fecha
            <input
              aria-label="Fecha de cartelera"
              className="field w-full mt-2"
              type="date"
              value={day}
              onChange={(e) =>
                e.target.value && update("fecha", e.target.value)
              }
            />
          </label>
          <label className="text-xs text-mute">
            Deporte
            <select
              aria-label="Deporte de cartelera"
              className="field w-full mt-2"
              value={sport}
              onChange={(e) => update("deporte", e.target.value)}
            >
              {Object.entries(SPORTS).map(([key, name]) => (
                <option key={key} value={key}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-mute">
            Competición
            <select
              aria-label="Competición de cartelera"
              className="field w-full mt-2"
              value={competition}
              onChange={(e) => setCompetition(e.target.value)}
            >
              <option value="ALL">Todas las competiciones</option>
              {competitions.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-mute">
            Estado
            <select
              aria-label="Estado de cartelera"
              className="field w-full mt-2"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="ALL">Todos</option>
              {Object.entries(STATUS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <input
          className="field w-full"
          aria-label="Buscar en cartelera"
          placeholder="Buscar equipo o competición"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </section>
      {loading && (
        <div
          className="skeleton h-40"
          role="status"
          aria-label="Consultando calendario ampliado"
        />
      )}
      {error && (
        <p role="alert" className="text-xs text-amber">
          {error}
        </p>
      )}
      {data && (
        <>
          <div className="flex flex-wrap gap-3 justify-between text-xs text-mute">
            <p>
              {items.length} encuentros · {day} · {competitions.length}{" "}
              competiciones
            </p>
            <p>
              Consulta: {localTime(data.fetched_at)} · ESPN · America/Hermosillo
            </p>
          </div>
          {data.errors.length > 0 && (
            <p role="status" className="text-xs text-amber">
              Cobertura parcial: algunas consultas al proveedor fallaron.
            </p>
          )}
          <div className="space-y-3">
            {items.slice((current - 1) * 40, current * 40).map((e) => (
              <article
                key={e.id}
                className="panel rounded-xl p-5 flex flex-wrap items-center justify-between gap-4"
              >
                <div className="min-w-0">
                  <p className="text-[10px] text-mute mb-2">
                    {e.sport_name} · {e.competition.name}
                  </p>
                  <h2 className="font-semibold text-sm break-words">
                    {e.home} vs {e.away}
                  </h2>
                  <p className="text-xs text-mute mt-2">
                    {kickoffLabel(e.kickoff)} · {STATUS[e.status] || e.status}
                  </p>
                </div>
                <div className="text-xs space-y-2 shrink-0">
                  <p className={e.forecast_available ? "text-led" : "text-mute"}>{e.forecast_reason}</p>
                  {e.forecast_available && <p className="text-[10px] text-mute">Mercados con historial real suficiente</p>}
                  {e.automatic_count > 0 && <Link to="/mis-pronosticos" className="text-led block">{e.automatic_count} apuestas automáticas registradas →</Link>}
                  {e.match_id ? (
                    <Link
                      className="text-led block"
                      to={`/match/${e.match_id}`}
                    >
                      Ver análisis local →
                    </Link>
                  ) : (
                    <p className="text-mute">Sin análisis local disponible</p>
                  )}
                  {e.source_url && (
                    <a
                      className="text-led block"
                      target="_blank"
                      rel="noreferrer"
                      href={e.source_url}
                    >
                      Ver fuente del encuentro ↗
                    </a>
                  )}
                  <p className="text-[10px] text-mute">
                    {e.draftea_reference
                      ? `Visto en tus capturas · ${e.draftea_reference.pick} · Momio ${e.draftea_reference.american_odds > 0 ? "+" : ""}${e.draftea_reference.american_odds}`
                      : "Draftea: sin verificar"}
                  </p>
                </div>
              </article>
            ))}
          </div>
          {!items.length && (
            <div className="empty-state">
              No hay encuentros devueltos por la fuente con estos filtros.
            </div>
          )}
          <div className="flex justify-between items-center text-xs text-mute">
            <span>
              Página {current} de {pages}
            </span>
            <div className="flex gap-4">
              <button
                disabled={current <= 1}
                className="text-led disabled:text-mute"
                onClick={() => setPage(current - 1)}
              >
                Anterior
              </button>
              <button
                disabled={current >= pages}
                className="text-led disabled:text-mute"
                onClick={() => setPage(current + 1)}
              >
                Siguiente
              </button>
            </div>
          </div>
          <p className="text-[10px] text-mute leading-5">
            {data.coverage} Las consultas se comparten y se actualizan
            aproximadamente cada cinco minutos; el proveedor puede retrasarse.
          </p>
        </>
      )}
    </div>
  );
}
