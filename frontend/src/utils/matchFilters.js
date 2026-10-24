export function normalizeSearch(value = "") {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

export function isUpcoming(match, now) {
  return match.status === "SCHEDULED" && new Date(match.kickoff).getTime() > new Date(now).getTime();
}
