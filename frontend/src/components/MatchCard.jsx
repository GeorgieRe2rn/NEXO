import { Link } from "react-router-dom";
import { kickoffLabel, pct } from "../api/client";
import ConfidenceBadge from "./ConfidenceBadge";
import Crest from "./Crest";
import FormPills from "./FormPills";
import ProbabilityBar from "./ProbabilityBar";

export default function MatchCard({ match }) {
  const p = match.prediction || {};
  const pick = { LOCAL: "Gana local", EMPATE: "Empate", VISITANTE: "Gana visitante" }[p.pick] || p.pick;
  const status = match.status_label || "Por jugar";
  return (
    <Link to={`/match/${match.id}`} className="glass rounded-lg p-4 block hover:border-led/40 transition pitch-stripe">
      <div className="flex items-center justify-between text-[12px] text-mute">
        <span className="uppercase tracking-wider">{match.league?.name}</span>
        <span className={match.status === "LIVE" ? "text-led" : ""}>{status} · {kickoffLabel(match.kickoff)}</span>
      </div>
      <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
        <div className="flex flex-col items-center text-center gap-2 min-w-0">
          <Crest src={match.home.logo_url} name={match.home.name} size={52} />
          <p className="font-display text-xl leading-none">{match.home.short_name || match.home.name}</p>
          <FormPills form={match.home_form} size="sm" />
        </div>
        <div className="text-center px-2">
          <p className="stat-num text-2xl text-led">{pct(p.p_home)}</p>
          <p className="text-[11px] text-mute">local</p>
        </div>
        <div className="flex flex-col items-center text-center gap-2 min-w-0">
          <Crest src={match.away.logo_url} name={match.away.name} size={52} />
          <p className="font-display text-xl leading-none">{match.away.short_name || match.away.name}</p>
          <FormPills form={match.away_form} size="sm" />
        </div>
      </div>
      <div className="mt-4">
        <ProbabilityBar pHome={p.p_home} pDraw={p.p_draw} pAway={p.p_away} compact />
      </div>
      <div className="mt-3 flex items-center justify-between text-[12px]">
        <span className="text-mute">Más 2.5 goles {pct(p.p_over_25)}</span>
        <span className="text-led">{pick}</span>
        <ConfidenceBadge label={p.confidence_label} score={p.confidence} />
      </div>
    </Link>
  );
}
