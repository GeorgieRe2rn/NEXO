import SportScoreTracker from "./SportScoreTracker";
import { verifiedTracker } from "../utils/verifiedTrackers";
export default function MatchTracker({match}) {
  const source = verifiedTracker(match);
  return source ? <SportScoreTracker source={source} matchLabel={`${match.home.name} · ${match.away.name}`} /> : null;
}
