export function matchClock(match, now = Date.now()) {
  const source=match.live?.clock || "";
  const normalized=source.replace(/[′'’\s]/g, "");
  const exact=normalized.match(/^(\d+(?:\+\d+)?):(\d{2})$/);
  if (exact) return {label:source,estimated:false,source};
  const minutes=normalized.match(/^(\d+(?:\+\d+)?)$/);
  if (!minutes) return {label:source,estimated:false,source};
  const anchor=Date.parse(match.live?.clock_reported_at || match.live?.details_at || match.verified_at);
  const running=match.status==="LIVE" && !match.stale && match.live?.clock_running!==false;
  if (!Number.isFinite(anchor) || !running) return {label:`${minutes[1]}:--`,estimated:false,source};
  const elapsed=Math.max(0,Math.floor((now-anchor)/1000));
  // Nunca avanzar a otro minuto sin confirmación del proveedor.
  return {label:`${minutes[1]}:${String(Math.min(59,elapsed)).padStart(2,"0")}`,estimated:true,waiting:elapsed>=60,source};
}
