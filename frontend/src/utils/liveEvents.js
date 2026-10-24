export const ACTIONS = {
  goal: { label: "¡GOL!", color: "#FF783E" },
  corner: { label: "Tiro de esquina", color: "#FF783E" },
  yellow: { label: "Tarjeta amarilla", color: "#ffd166" },
  red: { label: "Tarjeta roja", color: "#ff6577" },
  foul: { label: "Falta", color: "#8bc5ff" },
  penalty: { label: "Penal", color: "#ffd166" },
  substitution: { label: "Cambio", color: "#8bc5ff" },
  var: { label: "Revisión VAR", color: "#d3b9ff" },
  correction: { label: "Marcador corregido", color: "#8bc5ff" },
  score: { label: "Marcador actualizado", color: "#FF783E" },
};

export function actionKind(type = "") {
  if (/disallow|cancel|overturn|goal-kick|goalkeeper|miss|saved/i.test(type)) return null;
  if (/corner/i.test(type)) return "corner";
  if (/red-card|second-yellow|yellow-red/i.test(type)) return "red";
  if (/yellow/i.test(type)) return "yellow";
  if (/goal/i.test(type)) return "goal";
  if (/penalty/i.test(type)) return "penalty";
  if (/foul/i.test(type)) return "foul";
  if (/substitution/i.test(type)) return "substitution";
  if (/var/i.test(type)) return "var";
  return null;
}

export const eventKey = e => `${e.id}:${actionKind(e.type)}`;
export function liveState(match, previous) {
  const same = previous?.id === match.id;
  return { id: match.id, status: match.status, stale: match.stale,
    home: match.live?.score_pending_confirmation && same ? previous.home : match.home_goals,
    away: match.live?.score_pending_confirmation && same ? previous.away : match.away_goals,
    keys: (match.live?.events || []).map(eventKey),
    latest: Math.max(0,...(match.live?.events || []).map(e=>e.seconds || 0)),
    observedAt: match.verified_at, stats:match.live?.stats,
  };
}

export function newLiveActions(previous, match) {
  if (!previous || previous.id !== match.id || previous.status !== "LIVE" || match.status !== "LIVE" || previous.stale || match.stale) return [];
  if (new Date(match.verified_at)-new Date(previous.observedAt)>180000) return [];
  const known = new Set(previous.keys);
  const clock=String(match.live?.clock || "").replace(/[′'’\s]/g, "").match(/^(\d+)(?:\+(\d+))?/);
  const threshold=Math.max(previous.latest-120,clock ? (Number(clock[1])+Number(clock[2] || 0))*60-120 : 0);
  const events = (match.live?.events || []).filter(e => !known.has(eventKey(e)) && actionKind(e.type) && actionKind(e.type) !== "goal" && (e.seconds || 0) >= threshold)
    .slice(0,3).reverse().map(e => ({...e, kind:actionKind(e.type), key:eventKey(e)}));
  if (!match.live?.score_pending_confirmation && [previous.home,previous.away,match.home_goals,match.away_goals].every(Number.isFinite)) {
    const h=match.home_goals-previous.home, a=match.away_goals-previous.away;
    if (h || a) {
      const kind = h < 0 || a < 0 ? "correction" : h+a === 1 ? "goal" : "score";
      const team = h>0 && a===0 ? match.home.name : a>0 && h===0 ? match.away.name : null;
      const goalEvent=(match.live?.events || []).find(e=>actionKind(e.type)==="goal" && !known.has(eventKey(e)));
      events.unshift({kind,team,minute:goalEvent?.minute,key:`score:${match.home_goals}:${match.away_goals}`,score:`${match.home_goals} – ${match.away_goals}`});
    }
  }
  const detailsAge=new Date(match.verified_at)-new Date(match.live?.details_at);
  if (Number.isFinite(detailsAge) && Math.abs(detailsAge)<=180000) {
    for (const [field,kind] of [["corners","corner"],["yellows","yellow"],["reds","red"]]) {
      for (const side of ["home","away"]) {
        const before=previous.stats?.[side]?.[field],now=match.live?.stats?.[side]?.[field];
        if (!Number.isFinite(before) || !Number.isFinite(now) || now<=before) continue;
        const team=match[side].name;
        if (events.some(e=>e.kind===kind && (!e.team || e.team===team))) continue;
        events.push({kind,team,key:`stat:${side}:${field}:${now}`,note:"Cambio confirmado en las estadísticas",label:now-before>1 ? `${ACTIONS[kind].label} · total actualizado` : undefined});
      }
    }
  }
  return events.slice(0,4);
}
