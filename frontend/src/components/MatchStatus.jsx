import useMatchClock from "../hooks/useMatchClock";
export default function MatchStatus({ match }) {
  const live = match.status === "LIVE" && !match.stale;
  const timer = useMatchClock(match);
  const clock = timer.label;
  return (
    <span
      title={timer.estimated ? `Segundos aproximados desde la recepción del minuto. ESPN confirma ${timer.source}.` : "Tiempo confirmado por la fuente; los segundos no informados aparecen como --."}
      className={`inline-flex gap-1.5 items-center text-[10px] font-semibold rounded px-2 py-1 whitespace-nowrap ${live ? "bg-led text-ink-950" : match.stale && match.status === "LIVE" ? "bg-amber/10 text-amber" : "bg-ink-950/5 text-mute"}`}
    >
      {live && <span className="w-1 h-1 rounded-full bg-ink-950" />}
      {live
        ? `${clock || ""}${timer.estimated ? " ≈" : ""} EN VIVO`
        : match.status === "LIVE"
          ? "Sin confirmación reciente"
          : match.status_label || match.status}
    </span>
  );
}
