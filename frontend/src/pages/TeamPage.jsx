import { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Users, MapPin, ArrowUpRight } from "lucide-react";
import { api, kickoffLabel } from "../api/client";
import usePolling from "../hooks/usePolling";
import Crest from "../components/Crest";
import StatsTable from "../components/StatsTable";
import FormPills from "../components/FormPills";
export default function TeamPage() {
  const { id } = useParams();
  const {
    data: team,
    error,
    loading,
    reload,
  } = usePolling(() => api.team(id), id, 60000);
  const [tab, setTab] = useState("plantilla"),
    [opponents, setOpponents] = useState([]),
    [compareId, setCompareId] = useState("");
  const comparison = usePolling(
    () => (compareId ? api.team(compareId) : Promise.resolve(null)),
    compareId,
    60000,
  );
  useEffect(() => {
    setCompareId("");
    if (team?.league?.code)
      api
        .leagueTeams(team.league.code)
        .then((d) => setOpponents(d.items || []))
        .catch(() => {});
  }, [team?.id]);
  if (!team)
    return (
      <div className="space-y-4">
        <Link to="/plantillas" className="text-xs text-mute">
          ← Equipos
        </Link>
        {loading ? (
          <div className="skeleton h-60" />
        ) : (
          <div className="empty-state">
            No se pudo cargar el equipo.{" "}
            <button onClick={reload}>Reintentar</button>
          </div>
        )}
      </div>
    );
  const form = team.form;
  return (
    <div className="space-y-6">
      <Link
        to={`/plantillas?liga=${team.league.code}`}
        className="inline-flex gap-2 items-center text-xs text-mute"
      >
        <ArrowLeft size={14} />
        Equipos / {team.league.name}
      </Link>
      {error && <p className="text-amber text-xs">{error}</p>}
      <section className="panel rounded-xl p-6 md:p-8">
        <div className="flex flex-col md:flex-row gap-6 md:items-center">
          <div className="flex items-center gap-5 flex-1">
            <Crest src={team.logo_url} name={team.name} size={76} />
            <div>
              <p className="eyebrow mb-2">{team.league.name}</p>
              <h1 className="page-title">{team.name}</h1>
              <p className="text-xs text-mute mt-2 flex gap-1 items-center">
                <MapPin size={12} />
                {team.city || team.league.name} · {team.tla}
              </p>
            </div>
          </div>
          <div>
            <p className="text-xs text-mute mb-3">
              Últimos {form?.matches_used || 0} partidos verificados
            </p>
            <FormPills form={form?.form_string} />
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-8">
          {[
            ["Goles a favor", form?.matches_used ? form.gf_avg : null],
            ["Goles recibidos", form?.matches_used ? form.ga_avg : null],
            ["Puntos recientes", form?.matches_used ? form.points : null],
            ["Jugadores verificados", team.squad.length],
          ].map(([label, value]) => (
            <div key={label} className="border-l border-ink-950/10 pl-4">
              <p className="text-[10px] text-mute">{label}</p>
              <p className="stat-num text-2xl mt-2">{value ?? "—"}</p>
            </div>
          ))}
        </div>
      </section>
      <nav className="border-b border-ink-950/10 flex gap-7">
        {[
          ["plantilla", "Plantilla"],
          ["forma", "Forma reciente"],
          ["comparativa", "Comparativa"],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`py-3 text-xs border-b-2 ${tab === key ? "text-led border-led" : "text-mute border-transparent"}`}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "plantilla" && (
        <>
          <div className="flex justify-between items-center">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <Users size={16} />
              {team.squad.length} jugadores
            </h2>
            <span className="text-[10px] text-mute">
              {team.squad[0]?.season_label || "Temporada sin confirmar"}
            </span>
          </div>
          <StatsTable players={team.squad} />
          <p className="text-xs text-mute leading-6">
            Plantilla consultada{" "}
            {team.squad[0]?.verified_at
              ? kickoffLabel(team.squad[0].verified_at)
              : "sin actualización disponible"}
            . No equivale a una alineación confirmada.
          </p>
        </>
      )}
      {tab === "forma" && (
        <div className="panel rounded-xl overflow-hidden">
          <div className="p-5 border-b border-ink-950/10">
            <h2 className="text-sm font-semibold">
              Últimos cinco encuentros de la competición
            </h2>
            <p className="text-xs text-mute mt-2">
              Ordenados del más reciente al más antiguo. Marcadores verificados
              por la fuente.
            </p>
          </div>
          {form?.slices?.length ? (
            form.slices.map((s, i) => (
              <div
                key={i}
                className="px-5 py-4 border-b border-ink-950/5 flex gap-4 items-center text-xs"
              >
                <span className="text-mute flex-1">
                  {kickoffLabel(s.kickoff)}
                </span>
                <span>
                  {s.is_home ? "Local" : "Visitante"} vs {s.opponent}
                </span>
                <strong className="stat-num text-base">
                  {s.goals_for} – {s.goals_against}
                </strong>
                <FormPills
                  form={s.result === "W" ? "V" : s.result === "D" ? "E" : "D"}
                  size="sm"
                />
              </div>
            ))
          ) : (
            <div className="empty-state">
              Aún no se dispone de resultados verificados de este equipo.
            </div>
          )}
        </div>
      )}
      {tab === "comparativa" && (
        <section className="panel rounded-xl p-5 space-y-6">
          <div className="flex flex-col sm:flex-row gap-3 justify-between sm:items-center">
            <h2 className="text-sm font-semibold">
              Forma reciente vs. otro equipo
            </h2>
            <select
              aria-label="Elegir equipo para comparar"
              className="field sm:max-w-xs"
              value={compareId}
              onChange={(e) => setCompareId(e.target.value)}
            >
              <option value="">Selecciona un equipo</option>
              {opponents
                .filter((t) => t.id !== team.id)
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
            </select>
          </div>
          {comparison.error && (
            <p className="text-amber text-xs">{comparison.error}</p>
          )}
          {comparison.data ? (
            <>
              <div className="flex justify-between text-xs text-mute">
                <span>
                  {team.short_name} · {form.matches_used} partidos
                </span>
                <span>
                  {comparison.data.short_name} ·{" "}
                  {comparison.data.form.matches_used} partidos
                </span>
              </div>
              {[
                ["gf_avg", "Goles a favor"],
                ["ga_avg", "Goles recibidos"],
                ["points", "Puntos"],
              ].map(([key, label]) => (
                <div
                  key={key}
                  className="flex justify-between border-t border-ink-950/10 py-4 text-sm"
                >
                  <strong className="text-led stat-num">
                    {form.matches_used ? form[key] : "—"}
                  </strong>
                  <span className="text-mute text-xs">{label}</span>
                  <strong className="stat-num">
                    {comparison.data.form.matches_used
                      ? comparison.data.form[key]
                      : "—"}
                  </strong>
                </div>
              ))}
            </>
          ) : (
            <p className="text-sm text-mute py-8 text-center">
              {comparison.loading && compareId
                ? "Cargando comparación…"
                : "Elige un equipo para comparar sus últimos resultados."}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
