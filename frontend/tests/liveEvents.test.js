import test from "node:test";
import assert from "node:assert/strict";
import { actionKind, liveState, newLiveActions } from "../src/utils/liveEvents.js";
const match=()=>({id:1,status:"LIVE",stale:false,home:{name:"Necaxa"},away:{name:"Atlas"},home_goals:0,away_goals:0,verified_at:"2026-10-17T01:00:00Z",live:{clock:"54'",details_at:"2026-10-17T01:00:00Z",events:[{id:"c1",type:"corner-awarded",seconds:2300,minute:"39'",team:"Necaxa"}],stats:{home:{corners:3,yellows:0},away:{corners:2,yellows:1}}}});

test("Al abrir o refrescar no se anuncian eventos antiguos",()=>{
  const m=match();assert.deepEqual(newLiveActions(null,m),[]);
  assert.deepEqual(newLiveActions(liveState(m),m),[]);
});
test("Gol solo con aumento confirmado; una reducción es corrección",()=>{
  const m=match(),previous=liveState(m);m.away_goals=1;
  assert.equal(newLiveActions(previous,m)[0].kind,"goal");
  assert.equal(newLiveActions(previous,m)[0].team,"Atlas");
  const after=liveState(m);m.away_goals=0;
  assert.equal(newLiveActions(after,m)[0].kind,"correction");
});
test("No se anuncia un gol pendiente y se conserva el último marcador confirmado",()=>{
  const m=match(),previous=liveState(m);m.away_goals=1;m.live.score_pending_confirmation=true;
  assert.deepEqual(newLiveActions(previous,m),[]);
  const pending=liveState(m,previous);assert.equal(pending.away,0);
  m.live.score_pending_confirmation=false;
  assert.equal(newLiveActions(pending,m)[0].kind,"goal");
});
test("Nuevas tarjetas y córners se anuncian una sola vez",()=>{
  const m=match(),previous=liveState(m);
  m.live.events.unshift({id:"y1",type:"yellow-card",seconds:3200,minute:"54'",team:"Atlas"});
  assert.equal(newLiveActions(previous,m)[0].kind,"yellow");
  assert.deepEqual(newLiveActions(liveState(m),m),[]);
});
test("Los contadores reales permiten avisar sin inventar el minuto del evento",()=>{
  const m=match(),previous=liveState(m);
  m.live.stats={...m.live.stats,home:{corners:4,yellows:0}};
  const updates=newLiveActions(previous,m);
  assert.equal(updates[0].kind,"corner");assert.equal(updates[0].minute,undefined);
});
test("No se interpreta como cero una estadística ausente ni se reanima tras una desconexión",()=>{
  const m=match();m.live.stats={};const previous=liveState(m);
  m.live.stats={home:{corners:4}};assert.deepEqual(newLiveActions(previous,m),[]);
  m.home_goals=1;m.stale=true;assert.deepEqual(newLiveActions(previous,m),[]);
  m.stale=false;m.verified_at="2026-10-17T01:10:00Z";assert.deepEqual(newLiveActions(previous,m),[]);
});
test("Goles anulados y saques de meta no son goles; segunda amarilla se distingue",()=>{
  assert.equal(actionKind("goal-disallowed"),null);assert.equal(actionKind("goal-kick"),null);
  assert.equal(actionKind("second-yellow-card"),"red");
  assert.equal(actionKind("foul-committed"),"foul");
});

test("Un comentario antiguo incorporado tarde no se anuncia como acción nueva",()=>{
  const m=match(),previous=liveState(m);
  m.live.events.unshift({id:"old",type:"foul-committed",seconds:2700,minute:"45'"});
  assert.deepEqual(newLiveActions(previous,m),[]);
});
