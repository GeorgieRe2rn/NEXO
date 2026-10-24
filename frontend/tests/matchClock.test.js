import test from "node:test";
import assert from "node:assert/strict";
import { matchClock } from "../src/utils/matchClock.js";
const anchor=Date.parse("2026-10-17T01:00:00Z");
const live=()=>({status:"LIVE",stale:false,live:{clock:"61'",clock_reported_at:new Date(anchor).toISOString(),clock_running:true}});
test("Los segundos interpolados se marcan aproximados y no cambian de minuto sin fuente",()=>{
  assert.equal(matchClock(live(),anchor+7000).label,"61:07");
  assert.equal(matchClock(live(),anchor+7000).estimated,true);
  assert.equal(matchClock(live(),anchor+70000).label,"61:59");
  assert.equal(matchClock(live(),anchor+70000).waiting,true);
});
test("Descansos, datos antiguos y ausencia de ancla no inventan segundos",()=>{
  const m=live();m.stale=true;assert.equal(matchClock(m,anchor+5000).label,"61:--");
  m.stale=false;m.live.clock_running=false;assert.equal(matchClock(m,anchor+5000).label,"61:--");
  m.live.clock="HT";assert.equal(matchClock(m,anchor+5000).label,"HT");
});
test("Tiempo añadido y segundos exactos publicados se conservan",()=>{
  const m=live();m.live.clock="90+3'";assert.equal(matchClock(m,anchor+9000).label,"90+3:09");
  m.live.clock="90'+3";assert.equal(matchClock(m,anchor+9000).label,"90+3:09");
  m.live.clock="63:21";assert.deepEqual(matchClock(m,anchor+9000),{label:"63:21",estimated:false,source:"63:21"});
});
