const tone = {
  V: "bg-led text-ink-950",
  W: "bg-led text-ink-950",
  E: "bg-ink-950/15 text-paper",
  D: "bg-rust-500 text-paper",
  L: "bg-rust-500 text-paper",
};

export default function FormPills({ form = "—", size = "md" }) {
  const parts = (form || "—").split("-").filter(Boolean);
  const cls = size === "sm" ? "h-5 w-5 text-[10px]" : "h-7 w-7 text-xs";
  return (
    <div className="flex items-center gap-1">
      {parts.map((r, i) => (
        <span key={`${r}-${i}`} className={`${cls} ${tone[r] || "bg-ink-950/10"} rounded font-semibold grid place-items-center`}>
          {r}
        </span>
      ))}
    </div>
  );
}
