import { useEffect, useState } from "react";
import { matchClock } from "../utils/matchClock";
export default function useMatchClock(match) {
  const [now,setNow]=useState(Date.now);
  const active=match.status==="LIVE" && !match.stale && match.live?.clock_running!==false;
  useEffect(()=>{
    setNow(Date.now());
    if (!active) return;
    const timer=setInterval(()=>setNow(Date.now()),1000);
    return ()=>clearInterval(timer);
  },[active,match.live?.clock,match.live?.clock_reported_at]);
  return matchClock(match,now);
}
