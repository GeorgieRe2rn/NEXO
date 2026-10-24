import { useFeed } from "./FeedContext";
export default function LeagueFilter({
  value = "ALL",
  onChange,
  label = "Filtrar por liga",
}) {
  const { leagues } = useFeed();
  return (
    <label className="flex items-center gap-2 text-[11px] text-mute">
      <span className="shrink-0">Liga</span>
      <select
        aria-label={label}
        className="field min-w-[160px] max-w-[230px]"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="ALL">Todas las ligas</option>
        {leagues.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name}
          </option>
        ))}
      </select>
    </label>
  );
}
