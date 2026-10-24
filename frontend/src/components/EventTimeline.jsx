import { Flag, Goal, ArrowLeftRight, Square, Hand } from "lucide-react";
import { ACTIONS, actionKind } from "../utils/liveEvents";
const label = (type) => /goal.*disallow|disallow.*goal/i.test(type) ? "Gol anulado" : actionKind(type)==="goal" ? "Gol" : ACTIONS[actionKind(type)]?.label || "Evento";
export default function EventTimeline({ events = [], compact = false }) {
  if (!events.length)
    return (
      <div className="py-8 text-sm text-mute text-center">
        La fuente aún no reporta eventos para este encuentro.
      </div>
    );
  return (
    <ol className="divide-y divide-ink-950/5">
      {events.slice(0, compact ? 4 : 80).map((e, i) => {
        const type = label(e.type);
        const Icon =
          actionKind(e.type) === "corner"
            ? Flag
            : type === "Gol"
              ? Goal
              : type === "Cambio"
                ? ArrowLeftRight
                : type === "Falta" ? Hand : Square;
        return (
          <li
            key={e.id}
            className={`flex gap-3 py-3 ${i === 0 ? "text-paper" : "text-mute"}`}
          >
            <span className="text-xs stat-num w-8 shrink-0 pt-0.5 text-led">
              {e.minute}
            </span>
            <Icon
              size={14}
              className={`shrink-0 mt-0.5 ${/amarilla/.test(type) ? "text-amber" : /roja/.test(type) ? "text-rust-400" : "text-led"}`}
            />
            <div className="min-w-0">
              <p className="text-xs font-medium">
                {type}
                {e.player ? ` · ${e.player}` : e.team ? ` · ${e.team}` : ""}
              </p>
              {!compact && e.text && (
                <p className="text-[11px] mt-1 text-mute leading-relaxed">
                  {e.text}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
