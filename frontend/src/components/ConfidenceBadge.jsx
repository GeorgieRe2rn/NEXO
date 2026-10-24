const map = {
  ALTA: "text-paper border-rust-500/40 bg-rust-500/15",
  MEDIA: "text-paper border-ink-950/15 bg-ink-950/5",
  BAJA: "text-mute border-ink-950/10 bg-transparent",
};

export default function ConfidenceBadge({ label = "MEDIA", score }) {
  return (
    <span className={`inline-flex items-center gap-2 rounded-md border px-2 py-0.5 text-[11px] ${map[label] || map.MEDIA}`}>
      {label === "ALTA" ? "Alta" : label === "MEDIA" ? "Media" : label === "BAJA" ? "Baja" : label}
      {typeof score === "number" && <span className="stat-num text-mute">{Math.round(score * 100)}</span>}
    </span>
  );
}

// Este es un cambio de la rama dev