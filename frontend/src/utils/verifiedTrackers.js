// Verified pilots, not automatic discovery. Match identity and kickoff must agree.
const VERIFIED = [
  {league:"SPL", home:"Al Faisaly", away:"Al Nassr", kickoff:"2026-10-23T13:30:00Z", slug:"al-nassr-fc-vs-al-faisaly-harmah"},
  {league:"PL", home:"Ipswich Town", away:"Nottingham Forest", kickoff:"2026-10-23T19:00:00Z", slug:"ipswich-town-vs-nottingham-forest"},
];
export function verifiedTracker(match, now = Date.now()) {
  const kickoff = Date.parse(match.kickoff);
  if (match.status !== "LIVE" || now < kickoff || now - kickoff > 4 * 3600000) return null;
  const entry = VERIFIED.find(e => e.league === match.league?.code && e.home === match.home?.name && e.away === match.away?.name && Date.parse(e.kickoff) === kickoff);
  return entry ? `https://sportscore.com/embed/tracker/football/${entry.slug}/?theme=light` : null;
}
