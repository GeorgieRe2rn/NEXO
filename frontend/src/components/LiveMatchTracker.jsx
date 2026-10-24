import { useEffect, useId, useRef, useState } from "react";
import { Flag, Goal, Square, ArrowLeftRight, Radio, ShieldCheck, RotateCcw, Hand } from "lucide-react";
import { ACTIONS, actionKind, liveState, newLiveActions } from "../utils/liveEvents";
import useMatchClock from "../hooks/useMatchClock";

const ICONS = {goal:Goal,corner:Flag,yellow:Square,red:Square,substitution:ArrowLeftRight,foul:Hand};

export default function LiveMatchTracker({match}) {
  const id = useId().replace(/:/g, "");
  const clock=useMatchClock(match);
  const previous = useRef(null), queue = useRef([]), running = useRef(false), timer = useRef(null);
  const [active,setActive] = useState(null);
  const last = (match.live?.events || []).find(e=>actionKind(e.type));
  const fresh = match.status === "LIVE" && !match.stale;
  function play() {
    if (!queue.current.length) { running.current=false;setActive(null);return; }
    running.current=true;
    setActive({...queue.current.shift(),animationId:Date.now()});
    timer.current=setTimeout(play,6500);
  }
  useEffect(()=>{
    const next=newLiveActions(previous.current,match);
    previous.current=liveState(match,previous.current);
    if (next.some(e=>["goal","correction","score"].includes(e.kind))) {
      clearTimeout(timer.current);queue.current=next;play();
    } else {
      queue.current=[...queue.current,...next].slice(-4);
      if (!running.current && queue.current.length) play();
    }
    if (!fresh) { clearTimeout(timer.current);queue.current=[];running.current=false;setActive(null); }
  },[match]);
  useEffect(()=>()=>clearTimeout(timer.current),[]);
  const event=active || (last ? {...last,kind:actionKind(last.type)} : null);
  const style={...(ACTIONS[event?.kind] || {label:"Esperando acciones",color:"#FF783E"}),...(event?.label ? {label:event.label} : {})};
  const Icon=ICONS[event?.kind] || ShieldCheck;
  const team=event?.team || (event?.team_id && [match.home,match.away].find(t=>String(t.espn_id)===String(event.team_id))?.name);
  return <section className="live-tracker" aria-label="Cancha y acciones confirmadas del partido">
    <header className="live-tracker-heading">
      <span><Radio size={13}/>{fresh ? "Acción en vivo" : match.status==="LIVE" ? "Seguimiento sin actualización reciente" : match.status==="SCHEDULED" ? "La cancha espera el inicio" : "Acciones del partido"}</span>
      <span className="live-tracker-source">{clock.label || "Sin minuto confirmado"}{clock.estimated ? " ≈" : ""} · ESPN {match.live?.clock || ""}</span>
    </header>
    <div className={`live-stadium ${active?.kind==="goal" ? "live-stadium-goal" : ""}`}>
      <div className="live-stadium-lights" aria-hidden="true"/>
      <div className="live-pitch-perspective" aria-hidden="true">
        <svg viewBox="0 0 1000 620" className="live-pitch" role="presentation">
          <defs>
            <pattern id={`${id}grass`} width="166" height="620" patternUnits="userSpaceOnUse"><rect width="83" height="620" fill="#1c6547"/><rect x="83" width="83" height="620" fill="#205b43"/></pattern>
            <pattern id={`${id}net`} width="12" height="12" patternUnits="userSpaceOnUse"><path d="M0 0H12V12" fill="none" stroke="#d5ecda" strokeOpacity=".35" strokeWidth="1"/></pattern>
          </defs>
          <rect width="1000" height="620" rx="10" fill={`url(#${id}grass)`}/>
          <g fill="none" stroke="#d3eadb" strokeOpacity=".66" strokeWidth="3">
            <path d="M42 42H958V578H42Z M500 42V578"/>
            <circle cx="500" cy="310" r="78"/>
            <path d="M42 155H192V465H42 M958 155H808V465H958 M42 235H101V385H42 M958 235H899V385H958"/>
            <path d="M192 252A78 78 0 0 1 192 368 M808 252A78 78 0 0 0 808 368"/>
            <path d="M42 67A25 25 0 0 0 67 42 M933 42A25 25 0 0 0 958 67 M42 553A25 25 0 0 1 67 578 M933 578A25 25 0 0 1 958 553"/>
          </g>
          <g fill="#e3f0e7"><circle cx="500" cy="310" r="4"/><circle cx="146" cy="310" r="4"/><circle cx="854" cy="310" r="4"/></g>
          <g fill={`url(#${id}net)`} stroke="#d5ecda" strokeOpacity=".7" strokeWidth="3"><path d="M12 262H42V358H12Z"/><path d="M958 262H988V358H958Z"/></g>
        </svg>
      </div>
      <div className="live-pitch-team live-pitch-team-home">{match.home.short_name}</div>
      <div className="live-pitch-team live-pitch-team-away">{match.away.short_name}</div>
      {event ? <div key={active?.animationId || "last"} className={`live-event-palette ${active ? "live-event-enter" : "live-event-static"}`} style={{"--action-color":style.color}}>
        {active?.kind==="goal" && <div className="live-goal-rays" aria-hidden="true"/>}
        <div className={`live-event-symbol live-event-symbol-${event.kind}`}><Icon size={28} fill={/yellow|red/.test(event.kind) ? "currentColor" : "none"}/></div>
        <div className="live-event-copy">
          <p className="live-event-caption">{active?.replay ? "Repetición · acción confirmada" : active ? event.note || "Nueva acción confirmada" : "Última acción publicada"}{event.minute ? ` · ${event.minute}` : ""}</p>
          <p className="live-event-title">{style.label}</p>
          <p className="live-event-team">{team || "Equipo no informado"}{event.player ? ` · ${event.player}` : ""}</p>
          {event.score && <p className="live-event-score">{event.score}</p>}
        </div>
        {active && <div className="live-event-progress"/>}
      </div> : <div className="live-event-empty"><ShieldCheck size={20}/><span>{match.status==="SCHEDULED" ? "Las acciones aparecerán al comenzar" : "Esperando eventos confirmados"}</span></div>}
      <div role="status" aria-live="polite" className="sr-only">{active ? `${active.replay ? "Repetición" : "Acción confirmada"}: ${style.label}. ${team || ""}. ${event.minute || ""}` : ""}</div>
    </div>
    <footer className="live-tracker-footer"><span>Cancha ilustrativa, sin ubicación real del evento.{clock.estimated ? " ≈ Segundos aproximados; ESPN confirma solo el minuto." : ""}</span>
      {last && <button type="button" disabled={!!active} onClick={()=>{queue.current.push({...last,kind:actionKind(last.type),replay:true});if(!running.current)play();}}><RotateCcw size={11}/>Repetir última acción</button>}
    </footer>
  </section>;
}
