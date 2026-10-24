import { pct } from "../api/client";

export default function ProbabilityBar({ pHome, pDraw, pAway, compact = false }) {
  const h = Math.max(2, (pHome || 0) * 100);
  const d = Math.max(2, (pDraw || 0) * 100);
  const a = Math.max(2, (pAway || 0) * 100);
  return (
    <div>
      <div className="flex h-1.5 overflow-hidden rounded-full bg-pitch-800">
        <div className="bg-paper" style={{ width: `${h}%` }} />
        <div className="bg-mute" style={{ width: `${d}%` }} />
        <div className="bg-rust-500" style={{ width: `${a}%` }} />
      </div>
      <div className={`mt-2 grid grid-cols-3 ${compact ? "text-[11px]" : "text-xs"}`}>
        <div>
          <p className="text-mute">Local</p>
          <p className="stat-num text-base">{pct(pHome)}</p>
        </div>
        <div className="text-center">
          <p className="text-mute">Empate</p>
          <p className="stat-num text-base">{pct(pDraw)}</p>
        </div>
        <div className="text-right">
          <p className="text-mute">Visitante</p>
          <p className="stat-num text-base">{pct(pAway)}</p>
        </div>
      </div>
    </div>
  );
}
