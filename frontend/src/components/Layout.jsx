import NexoBrand from "./NexoBrand";
import ThemeToggle from "./ThemeToggle";
import { NavLink, Link, useLocation, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  Activity,
  CalendarDays,
  ChartNoAxesCombined,
  ChevronRight,
  Layers,
  Radio,
  Shield,
  X,
  ArrowUpRight,
  Menu,
} from "lucide-react";
import { useFeed } from "./FeedContext";

import { dateLabel } from "../api/client";
const LINKS = [
  ["/", "Partidos", CalendarDays],
  ["/en-vivo", "En vivo", Radio],
  ["/plantillas", "Equipos", ChartNoAxesCombined],
  ["/posiciones", "Posiciones", Layers],
  ["/mis-pronosticos", "Mis apuestas", Shield],
  ["/cartelera", "Calendario", CalendarDays],
];
export default function Layout({ children }) {
  const { pathname } = useLocation();
  const [menuOpen,setMenuOpen]=useState(false);
  useEffect(()=>setMenuOpen(false),[pathname]);
  const [params] = useSearchParams();
  const { leagues, items, meta, notice, dismissNotice } = useFeed();
  const league = params.get("liga") || "ALL";
  const liveCount = items.filter((m) => m.status === "LIVE" && !m.stale).length;
  if (pathname.startsWith("/admin")) return <>{children}</>;
  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:z-50 focus:bg-led focus:text-ink-950 focus:p-4"
      >
        Ir al contenido
      </a>
      <header onKeyDown={e=>{if(e.key==="Escape")setMenuOpen(false);}} className="h-[72px] border-b border-ink-950/10 bg-pitch-950 sticky top-0 z-30 flex items-center px-4 md:px-7 gap-4 xl:gap-7">
        <Link to="/" className="flex items-center gap-2.5 shrink-0">
          <NexoBrand />
        </Link>
        <nav
          className="hidden lg:flex self-stretch items-stretch gap-4 xl:gap-5 flex-1"
          aria-label="Principal"
        >
          {LINKS.map(([to, text]) => (
            <NavLink
              key={to}
              to={to}
              end
              className={({ isActive }) =>
                `inline-flex gap-2 items-center border-b-2 text-[12px] font-medium ${isActive ? "border-led text-led" : "border-transparent text-mute hover:text-paper"}`
              }
            >
              {text}
              {to === "/en-vivo" && liveCount > 0 && (
                <span className="bg-led/15 text-led rounded px-1.5 text-[10px]">
                  {liveCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto"><ThemeToggle /></div>
        <Link
          to="/admin"
          aria-label="Administración"
          className="ml-auto shrink-0 flex items-center gap-2 text-mute hover:text-paper border border-ink-950/15 rounded-lg px-3 py-2 text-xs"
        >
          <Shield size={14} />
          <span className="hidden sm:inline">Administración</span>
        </Link>
        {menuOpen && <nav id="explore-navigation" aria-label="Más secciones" className="absolute top-[72px] inset-x-0 bg-pitch-900 border-b border-ink-950/15 shadow-2xl p-5 grid sm:grid-cols-2 lg:grid-cols-4 gap-2">{LINKS.map(([to,label,Icon])=><NavLink key={to} to={to} end onClick={()=>setMenuOpen(false)} className={({isActive})=>`flex items-center gap-3 p-4 rounded-lg text-sm ${isActive?'text-led bg-led/10':'text-mute hover:bg-ink-950/5 hover:text-paper'}`}><Icon size={18}/>{label}</NavLink>)}</nav>}
      </header>
      <div className="flex mx-auto max-w-[1800px]">
        <aside className="hidden lg:flex w-[212px] shrink-0 flex-col sticky top-[72px] h-[calc(100vh-72px)] overflow-y-auto p-5 border-r border-ink-950/10">
          <p className="eyebrow mb-4 mt-3">Competiciones</p>
          <NavLink
            to={["/en-vivo", "/posiciones"].includes(pathname) ? pathname : "/"}
            className={`flex items-center gap-2.5 p-3 text-xs rounded-md mb-1 ${league === "ALL" ? "bg-ink-950/5 text-paper" : "text-mute"}`}
          >
            <Layers size={15} /> Todas las ligas
          </NavLink>
          {leagues.map((l) => (
            <Link
              key={l.code}
              to={`${["/plantillas", "/en-vivo", "/posiciones"].includes(pathname) ? pathname : "/"}?liga=${l.code}`}
              className={`flex gap-3 items-center px-3 py-3 rounded-md text-xs mb-1 ${league === l.code ? "text-led bg-led/10 border-l-2 border-led" : "text-mute hover:bg-ink-950/5"}`}
            >
              {l.logo_url ? (
                <img
                  src={l.logo_url}
                  alt=""
                  className="w-5 h-5 object-contain"
                />
              ) : (
                <span className="w-5 text-center">⚽</span>
              )}
              <span>{l.name}</span>
            </Link>
          ))}
        </aside>
        <div className="flex-1 min-w-0">
          <main
            id="main-content"
            className="p-4 md:p-7 xl:p-9 max-w-[1440px] mx-auto pb-24 lg:pb-10"
          >
            {children}
          </main>
          <footer className="border-t border-ink-950/10 mx-4 md:mx-7 py-5 text-[10px] text-mute flex flex-wrap gap-2 justify-between pb-24 lg:pb-5">
            <span>NEXO · Fútbol en contexto</span>
            
            <span>
              Horarios de Hermosillo · UTC−7
            </span>
          </footer>
        </div>
      </div>
      <nav
        aria-label="Navegación móvil"
        className="lg:hidden fixed bottom-0 z-40 h-[70px] left-0 right-0 bg-pitch-900 border-t border-ink-950/10 flex justify-around pb-1"
      >
        {LINKS.filter(([to])=>["/","/en-vivo","/plantillas","/mis-pronosticos"].includes(to)).map(([to, text, Icon]) => (
          <NavLink
            key={to}
            to={to}
            end
            className={({ isActive }) =>
              `flex flex-col gap-1 justify-center items-center min-w-0 flex-1 text-center text-[9px] px-1 ${isActive ? "text-led" : "text-mute"}`
            }
          >
            <Icon size={19} />
            {text}
          </NavLink>
        ))}
        <button onClick={()=>setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-label="Más secciones" className="flex flex-col gap-1 justify-center items-center flex-1 text-[9px] text-mute"><Menu size={19}/>Más</button>
      </nav>
      {notice && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-24 lg:bottom-6 right-4 left-4 md:left-auto md:max-w-md z-50 bg-pitch-800 border border-led/50 rounded-lg shadow-2xl p-4 flex gap-3 items-center"
        >
          <span className="live-dot shrink-0" />
          <Link to={`/match/${notice.id}`} className="text-xs flex-1">
            {notice.text}
            <ChevronRight className="inline ml-2" size={12} />
          </Link>
          <button onClick={dismissNotice} aria-label="Cerrar aviso">
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

