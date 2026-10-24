import ThemeToggle from "../components/ThemeToggle";
import MarketDiagnostics from "../components/MarketDiagnostics";
import NexoBrand from "../components/NexoBrand";
import { useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  Database,
  LayoutDashboard,
  LogOut,
  RefreshCw,
  ShieldCheck,
  ChartNoAxesCombined,
  Radio,
  Menu,
  X,
  BrainCircuit,
  ListChecks,
} from "lucide-react";
import { api, kickoffLabel, pct } from "../api/client";
import { useFeed } from "../components/FeedContext";
import FeedStatus from "../components/FeedStatus";
import KnowledgeMetrics from "../components/KnowledgeMetrics";
import Methodology from "./Methodology";
import usePolling from "../hooks/usePolling";
import LeagueFilter from "../components/LeagueFilter";
import ForecastMarkets from "../components/ForecastMarkets";
import SelectionsHistory from "../components/SelectionsHistory";
import LearningPanel from "../components/LearningPanel";
import OddsPanel from "../components/OddsPanel";
import ModelsExplained from "../components/ModelsExplained";
import EventCatalog from "../pages/EventCatalog";
import TrainingAudit from "../components/TrainingAudit";
const TABS = [
  ["resumen", "Inicio del panel", LayoutDashboard, "Seguimiento"],
  ["cartelera", "Partidos", Radio, "Seguimiento"],
  ["predicciones", "Pronósticos", ChartNoAxesCombined, "Seguimiento"],
  ["selecciones", "Apuestas automáticas", ListChecks, "Seguimiento"],
  ["aprendizaje", "Modelos y aprendizaje", BrainCircuit, "Inteligencia"],
  ["auditoria", "Datos de entrenamiento", Database, "Inteligencia"],
  ["metricas", "Resultados y métricas", ChartNoAxesCombined, "Inteligencia"],
  ["datos", "Fuentes y sincronización", RefreshCw, "Sistema"],
  ["modelo", "Cómo funciona", ShieldCheck, "Sistema"],
];
const DESCRIPTIONS={resumen:"El estado del sitio y accesos a lo que necesitas.",cartelera:"Encuentra partidos por fecha y competición.",predicciones:"Estimaciones previas y en vivo por mercado.",selecciones:"Registro automático y comparación con resultados reales.",aprendizaje:"Distingue modelos activos, candidatos y pruebas en sombra.",auditoria:"Comprueba qué partidos históricos se aprovechan y cuáles necesitan datos.",metricas:"Evalúa probabilidades y aciertos sin mezclar versiones.",datos:"Cobertura, actualización y disponibilidad del proveedor.",modelo:"Entiende las variables, métodos y límites del proyecto."};
export default function AdminHome() {
  const [me, setMe] = useState(null),
    [navigationOpen, setNavigationOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const feed = useFeed();
  const [params, setParams] = useSearchParams();
  const tab=TABS.some(t=>t[0]===params.get("modulo"))?params.get("modulo"):"resumen";
  const setTab=(key)=>{const next=new URLSearchParams(params);next.set("modulo",key);setParams(next);setNavigationOpen(false);};
  const league = params.get("liga") || "ALL";
  const scopedItems = feed.items.filter(
    (m) => league === "ALL" || m.league.code === league,
  );
  const scopedMeta = {
    ...feed.meta,
    leagues: feed.meta?.leagues?.filter(
      (l) => league === "ALL" || l.code === league,
    ),
  };
  const overview = usePolling(
    () =>
      me?.authenticated ? api.adminOverview(league) : Promise.resolve(null),
    `${!!me?.authenticated}:${league}`,
    60000,
  );
  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe({ authenticated: false }));
  }, []);
  if (me && !me.authenticated) return <Navigate to="/admin/login" replace />;
  if (!me)
    return <div className="p-8 text-xs text-mute">Comprobando sesión…</div>;
  const run = async (fn) => {
    setBusy(true);
    setMessage("");
    try {
      await api.csrf();
      const r = await fn();
      setMessage(
        r.status === "partial"
          ? "Actualización parcial: algunas fuentes no respondieron."
          : r.status === "busy"
            ? "Ya hay una sincronización en curso."
            : "Solicitud completada. Los datos se actualizarán automáticamente.",
      );
      feed.reload();
      overview.reload();
    } catch {
      setMessage(
        "No se pudo completar la actualización. Revisa la conexión e inténtalo de nuevo.",
      );
    } finally {
      setBusy(false);
    }
  };
  const ov = overview.data;
  const forecasts = scopedItems.filter((m) => m.forecast);
  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <div className="lg:hidden fixed top-0 inset-x-0 h-16 z-40 bg-pitch-950 border-b border-ink-950/10 flex items-center justify-between px-4"><Link to="/" className="font-bold tracking-widest"><NexoBrand /></Link><ThemeToggle /><button className="p-2 border border-ink-950/15 rounded-lg" aria-label="Abrir navegación del panel" aria-expanded={navigationOpen} aria-controls="admin-navigation" onClick={()=>setNavigationOpen(!navigationOpen)}>{navigationOpen?<X size={20}/>:<Menu size={20}/>}</button></div>
      {navigationOpen && <button className="lg:hidden fixed inset-0 top-16 z-40 bg-black/60" aria-label="Cerrar navegación del panel" onClick={()=>setNavigationOpen(false)}/>}
      <aside id="admin-navigation" className={`${navigationOpen?"flex":"hidden"} lg:flex fixed top-16 bottom-0 left-0 z-50 w-[270px] lg:w-[248px] lg:sticky lg:top-0 lg:h-screen shrink-0 border-r border-ink-950/10 bg-pitch-900 p-5 flex-col overflow-y-auto`}>
        <Link
          to="/"
          className="flex items-center gap-2 text-xl font-bold tracking-widest mb-5"
        >
          <NexoBrand />
        </Link><div className="my-3"><ThemeToggle /></div>
        <p className="eyebrow mb-4">Centro de control</p>
        <nav
          aria-label="Administración"
          className="flex flex-col gap-5"
        >
          {["Seguimiento","Inteligencia","Sistema"].map(group=><div key={group}><p className="text-[9px] tracking-widest uppercase text-mute px-3 mb-2">{group}</p><div className="space-y-1">{TABS.filter(t=>t[3]===group).map(([key, label, Icon]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              aria-current={tab===key?"page":undefined}
              className={`w-full flex items-center gap-2.5 px-3 py-3 rounded-lg text-xs text-left ${tab === key ? "text-led bg-led/10 ring-1 ring-led/20" : "text-mute hover:text-paper hover:bg-ink-950/5"}`}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}</div></div>)}
        </nav>
        <div className="mt-5 md:mt-auto space-y-4 text-xs text-mute">
          <p className="hidden md:block border-t border-ink-950/10 pt-4">
            {me.username}
          </p>
          <div className="flex md:flex-col gap-4">
            <Link className="flex gap-2 items-center" to="/">
              Ver el sitio <ArrowUpRight size={12} />
            </Link>
            <button
              className="flex gap-2 items-center"
              onClick={async () => {
                await api.csrf();
                await api.logout();
                feed.clearAccount();
                setMe({ authenticated: false });
              }}
            >
              <LogOut size={13} />
              Cerrar sesión
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 min-w-0 max-w-[1600px] p-4 md:p-8 xl:p-10 pt-24 md:pt-24 lg:pt-8 xl:pt-10">
        <div className="flex flex-wrap justify-between gap-3 items-center border-b border-ink-950/10 pb-5 mb-6">
          <div><p className="eyebrow">Panel de control</p><h1 className="text-xl font-bold mt-2">{TABS.find((t) => t[0] === tab)?.[1]}</h1><p className="text-xs text-mute mt-2 max-w-xl">{DESCRIPTIONS[tab]}</p></div>
          {!["cartelera","aprendizaje","auditoria","modelo"].includes(tab) && (
            <LeagueFilter
              value={league}
              onChange={(v) => {const next=new URLSearchParams(params);v==="ALL"?next.delete("liga"):next.set("liga",v);setParams(next);}}
            />
          )}
          {tab !== "cartelera" && <FeedStatus compact league={["aprendizaje","auditoria"].includes(tab)?"ALL":league} />}
        </div>
        <nav aria-label="Accesos del panel" className="hidden md:flex flex-wrap gap-2 mb-7 text-[11px]"><Link className="pill" to="/">Ver jornada ↗</Link><Link className="pill" to="/plantillas">Equipos y jugadores ↗</Link><Link className="pill" to="/posiciones">Posiciones ↗</Link></nav>
        {tab === "resumen" && (
          <div className="space-y-6">
            <div>
              <h1 className="page-title">Una vista de todo.</h1>
              <p className="text-mute text-xs mt-3">
                Estado del seguimiento, la cobertura y los pronósticos
                guardados.
              </p>
            </div>
            <div className="grid sm:grid-cols-3 gap-3">{[["selecciones","Revisar apuestas","Consulta aciertos, fallos y pendientes."],["aprendizaje","Ver modelos","Producción y CatBoost experimental."],["auditoria","Revisar históricos","Datos reutilizados y motivos de exclusión."]].map(([key,title,description])=><button key={key} onClick={()=>setTab(key)} className="panel rounded-xl p-5 text-left hover:border-led/40"><p className="text-sm font-semibold text-led">{title} →</p><p className="text-xs text-mute mt-2">{description}</p></button>)}</div>
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
              {[
                [
                  "En vivo confirmados",
                  scopedItems.filter((m) => m.status === "LIVE" && !m.stale)
                    .length,
                ],
                [
                  "Próximos encuentros",
                  scopedItems.filter((m) => m.status === "SCHEDULED").length,
                ],
                ["Pronósticos disponibles", forecasts.length],
                [
                  "Ligas sincronizadas",
                  scopedMeta?.leagues?.filter(
                    (l) => l.status === "ok" && !l.stale,
                  ).length || 0,
                ],
              ].map(([k, v]) => (
                <div key={k} className="panel p-5 rounded-xl">
                  <p className="text-[11px] text-mute">{k}</p>
                  <p className="stat-num text-4xl mt-4 text-led">{v}</p>
                </div>
              ))}
            </div>
            <Sources meta={scopedMeta} />
            {overview.error && (
              <p className="text-amber text-xs">{overview.error}</p>
            )}
            {ov && (
              <section className="panel rounded-xl p-5">
                <h2 className="text-sm font-semibold mb-5">
                  Cobertura por competición
                </h2>
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr>
                      <th>Liga</th>
                      <th>Equipos</th>
                      <th>Jugadores registrados</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ov.ligas?.map((l) => (
                      <tr key={l.code} className="border-t border-ink-950/5">
                        <th className="py-4 font-normal">{l.name}</th>
                        <td>{l.equipos}</td>
                        <td>{l.jugadores}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
          </div>
        )}
        {tab === "datos" && (
          <div className="space-y-6">
            <div>
              <h1 className="page-title">Fuentes de datos.</h1>
              <p className="text-xs text-mute mt-3 leading-6">
                Resultados gratuitos de ESPN público. API-Football está
                restringida a temporadas antiguas en el plan configurado; no se
                utiliza para simular encuentros actuales.
              </p>
            </div>
            <Sources meta={scopedMeta} />
            {message && (
              <p
                role="status"
                className="border border-led/25 bg-led/5 rounded-lg p-4 text-xs"
              >
                {message}
              </p>
            )}
            <div className="grid lg:grid-cols-2 gap-4">
              <div className="panel p-6 rounded-xl">
                <Radio size={22} className="text-led mb-5" />
                <h2 className="font-semibold">Marcadores y eventos</h2>
                <p className="text-xs text-mute leading-6 mt-3 mb-5">
                  Actualización compartida cada minuto. Calendario de nueve días
                  y eventos de los partidos en curso. La fuente puede presentar
                  demoras.
                </p>
                <button
                  disabled={busy}
                  onClick={() => run(api.refreshFeed)}
                  className="primary-button inline-flex items-center gap-2"
                >
                  <RefreshCw size={13} />
                  {busy ? "Procesando…" : "Solicitar actualización"}
                </button>
              </div>
              <div className="panel p-6 rounded-xl">
                <Database size={22} className="text-led mb-5" />
                <h2 className="font-semibold">Plantillas y estadísticas</h2>
                <p className="text-xs text-mute leading-6 mt-3 mb-5">
                  Consulta jugadores y cifras disponibles de la temporada
                  actual. Se cachea por 24 horas; no utiliza plantillas de
                  demostración.
                </p>
                <button
                  disabled={busy}
                  onClick={() => run(api.runRosters)}
                  className="primary-button"
                >
                  {busy ? "Procesando…" : "Actualizar plantillas"}
                </button>
              </div>
            </div>
          </div>
        )}
        {tab === "predicciones" && (
          <div className="space-y-5">
            <h1 className="page-title">Pronósticos del modelo.</h1>
            <p className="text-xs text-mute">
              Consulta el análisis estadístico. Las selecciones se registran
              solas antes del partido en Apuestas automáticas.
            </p>
            {forecasts.length ? (
              forecasts.map((m) => (
                <article key={m.id} className="space-y-3">
                  <Link className="text-sm text-led" to={`/match/${m.id}`}>
                    {m.home.short_name} vs {m.away.short_name} ·{" "}
                    {m.forecast.phase === "LIVE" ? "En vivo" : "Previo"} →
                  </Link>
                  <ForecastMarkets
                    snapshot={m.forecast}
                    matchId={m.id}
                    canSelect={
                      !m.stale && ["LIVE", "SCHEDULED"].includes(m.status)
                    }
                  />
                </article>
              ))
            ) : (
              <div className="empty-state">
                Sin datos disponibles para esta liga.
              </div>
            )}
          </div>
        )}
        {tab === "metricas" && <KnowledgeMetrics league={league} />}
        {tab === "cartelera" && <EventCatalog />}
        {tab === "selecciones" && <SelectionsHistory league={league} />}
        {tab === "aprendizaje" && <div className="space-y-5"><LearningPanel /><OddsPanel /><MarketDiagnostics /><ModelsExplained /></div>}
        {tab === "auditoria" && <TrainingAudit />}
        {tab === "modelo" && <Methodology />}
      </main>
    </div>
  );
}
function Sources({ meta }) {
  return (
    <section className="panel rounded-xl p-5">
      <h2 className="text-sm font-semibold mb-5">Estado de las fuentes</h2>
      <div className="space-y-3">
        {meta?.leagues?.map((l) => (
          <div
            key={l.code}
            className="flex flex-wrap items-center gap-3 border-t border-ink-950/5 pt-3"
          >
            <span className="w-9 text-xs font-medium">{l.code}</span>
            <span
              className={`text-[10px] ${!l.stale && l.status === "ok" ? "text-led" : "text-amber"}`}
            >
              {!l.stale && l.status === "ok"
                ? "Sincronizado"
                : l.status === "error"
                  ? "Error de conexión"
                  : "Pendiente o desactualizado"}
            </span>
            <span className="text-mute text-[10px] ml-auto">
              {l.last_success
                ? kickoffLabel(l.last_success)
                : "Sin consulta exitosa"}
            </span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-mute mt-5">
        ESPN público · Sin SLA ni garantía de actualización inmediata. Horarios
        de Hermosillo.
      </p>
    </section>
  );
}

