import { Navigate, useSearchParams } from "react-router-dom";
import { useFeed } from "../components/FeedContext";
import LeagueFilter from "../components/LeagueFilter";
import SelectionsHistory from "../components/SelectionsHistory";
export default function MyForecasts() {
  const { account } = useFeed();
  const [params, setParams] = useSearchParams();
  const league = params.get("liga") || "ALL";
  if (!account) return <p className="text-xs text-mute">Comprobando sesión…</p>;
  if (!account.authenticated)
    return <Navigate to="/admin/login?volver=%2Fmis-pronosticos" replace />;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <h1 className="page-title">Apuestas automáticas del modelo.</h1>
        <LeagueFilter
          value={league}
          onChange={(v) => setParams(v === "ALL" ? {} : { liga: v })}
        />
      </div>
      <SelectionsHistory league={league} technical={false} />
    </div>
  );
}
