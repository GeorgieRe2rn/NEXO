import SportScoreTracker from "./SportScoreTracker";
import LiveStats from "./LiveStats";
import EventTimeline from "./EventTimeline";
import { verifiedTracker } from "../utils/verifiedTrackers";

export default function LiveCoverage({match}) {
  const source = verifiedTracker(match);
  return <section aria-label={`Seguimiento en vivo de ${match.home.name} y ${match.away.name}`} className="grid xl:grid-cols-[minmax(0,1fr)_320px] gap-4 p-3 md:p-4">
    <div className="min-w-0">
      {source ? <SportScoreTracker source={source} matchLabel={`${match.home.name} · ${match.away.name}`} /> : <div className="panel rounded-xl p-5">
        <h2 className="font-semibold text-sm mb-4">Últimos eventos</h2>
        <EventTimeline events={match.live?.events} />
      </div>}
    </div>
    <aside className="panel rounded-xl p-5 min-w-0" aria-label="Estadísticas en vivo">
      <div className="flex justify-between gap-3 mb-5"><h2 className="font-semibold text-sm">Estadísticas en vivo</h2><span className="text-[10px] text-mute">ESPN</span></div>
      {match.stale && <p className="text-xs text-amber mb-4">Últimos datos recibidos · Sin actualización reciente</p>}
      <LiveStats stats={match.live?.stats} home={match.home.short_name} away={match.away.short_name} />
    </aside>
  </section>;
}
