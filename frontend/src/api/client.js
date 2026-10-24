const BASE = "/api/v1";

function csrfToken() {
  const row = document.cookie
    .split("; ")
    .find((c) => c.startsWith("velar_csrf="));
  return row ? decodeURIComponent(row.split("=").slice(1).join("=")) : "";
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"])
    headers["Content-Type"] = "application/json";
  const csrf = csrfToken();
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  health: () => request("/health"),
  oddsStatus: () => request("/odds/status"),
  syncOdds: () => request("/odds/sync", { method: "POST" }),
  matchOdds: (id) => request(`/matches/${encodeURIComponent(id)}/odds`),
  leagues: () => request("/leagues"),
  standings: (code) => request(`/leagues/${encodeURIComponent(code)}/standings`),
  matches: (league = "ALL") =>
    request(`/matches?league=${encodeURIComponent(league)}`),
  feed: () => request("/feed"),
  refreshFeed: () => request("/feed/refresh", { method: "POST" }),
  match: (id) => request(`/matches/${id}`),
  pipeline: () => request("/pipeline"),
  metrics: (league = "ALL") =>
    request(`/metrics?league=${encodeURIComponent(league)}`),
  catalog: (day, sport = "soccer") =>
    request(`/catalog?day=${encodeURIComponent(day)}&sport=${sport}`),
  diagnostics: (league = "ALL") =>
    request(`/selections/diagnostics?league=${encodeURIComponent(league)}`),
  learning: () => request("/learning"),
  modelAudit: () => request("/models/audit"),
  selections: (league = "ALL", page = 1, status = "ALL") =>
    request(
      `/selections?league=${encodeURIComponent(league)}&page=${page}&status=${status}`,
    ),
  selectForecast: (snapshot_id, market, pick, line = null) =>
    request("/selections", {
      method: "POST",
      body: JSON.stringify({ snapshot_id, market, pick, line }),
    }),
  runEtl: (source) =>
    request(`/etl/run${source ? `?source=${source}` : ""}`, { method: "POST" }),
  runRosters: () => request("/etl/rosters", { method: "POST" }),
  runEnrich: () => request("/etl/enrich", { method: "POST" }),
  runFotmob: () => request("/etl/fotmob", { method: "POST" }),
  leagueTeams: (code) => request(`/leagues/${encodeURIComponent(code)}/teams`),
  leaguePlayers: (code) =>
    request(`/leagues/${encodeURIComponent(code)}/players`),
  leagueLeaders: (code) =>
    request(`/leagues/${encodeURIComponent(code)}/leaders`),
  team: (id) => request(`/teams/${id}`),
  adminOverview: (league = "ALL") =>
    request(`/admin/overview?league=${encodeURIComponent(league)}`),
  csrf: () => request("/auth/csrf"),
  me: () => request("/auth/me"),
  login: (username, password) =>
    request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request("/auth/logout", { method: "POST" }),
};

export function pct(n) {
  return n == null || !Number.isFinite(n) ? "—" : `${Math.round(n * 100)}%`;
}

export function kickoffLabel(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-MX", {
    timeZone: "America/Hermosillo",
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export const POS = {
  FW: "Delantero",
  MF: "Mediocampista",
  DF: "Defensa",
  GK: "Portero",
};

export const TIMEZONE = "America/Hermosillo";
export function localDay(iso = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(iso));
}
export function localTime(iso) {
  return iso
    ? new Date(iso).toLocaleTimeString("es-MX", {
        timeZone: TIMEZONE,
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "—";
}
export function dateLabel(iso, options = {}) {
  return new Date(iso).toLocaleDateString("es-MX", {
    timeZone: TIMEZONE,
    day: "numeric",
    month: "short",
    ...options,
  });
}
