import { createContext, useContext, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import usePolling from "../hooks/usePolling";

const Context = createContext(null);
export function FeedProvider({ children }) {
  const feed = usePolling(api.feed, "feed");
  const leagueResource = usePolling(api.leagues, "leagues", 60000);
  const accountResource = usePolling(api.me, "account", 30000);
  const [accountHidden, setAccountHidden] = useState(false);
  const leagues = leagueResource.data?.items || [];
  const [notice, setNotice] = useState(null);
  const previous = useRef(null);
  useEffect(() => {
    if (!feed.data) return;
    const scores = new Map();
    for (const m of feed.data.items) {
      const score = `${m.home_goals}-${m.away_goals}`;
      scores.set(m.id, score);
      if (
        m.status === "LIVE" &&
        !m.stale &&
        previous.current?.has(m.id) &&
        previous.current.get(m.id) !== score
      ) {
        setNotice({
          id: m.id,
          text: `Marcador actualizado · ${m.home.short_name} ${m.home_goals} – ${m.away_goals} ${m.away.short_name}`,
        });
      }
    }
    previous.current = scores;
  }, [feed.data]);
  useEffect(() => {
    if (notice) {
      const t = setTimeout(() => setNotice(null), 9000);
      return () => clearTimeout(t);
    }
  }, [notice]);
  const items = (feed.data?.items || []).map((m) => ({
    ...m,
    stale: m.stale || !!feed.error,
    status_label:
      feed.error && m.status === "LIVE"
        ? "Sin confirmación reciente"
        : m.status_label,
  }));
  return (
    <Context.Provider
      value={{
        ...feed,
        account:
          accountHidden || accountResource.error ? null : accountResource.data,
        clearAccount: () => setAccountHidden(true),
        reloadAccount: () => {
          setAccountHidden(false);
          accountResource.reload();
        },
        reload: () => {
          feed.reload();
          leagueResource.reload();
        },
        items,
        meta: feed.data?.meta,
        leagues,
        notice,
        dismissNotice: () => setNotice(null),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export const useFeed = () => useContext(Context);
