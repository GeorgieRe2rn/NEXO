import test from "node:test";
import assert from "node:assert/strict";
import { verifiedTracker } from "../src/utils/verifiedTrackers.js";
const match = {status:"LIVE",league:{code:"SPL"},home:{name:"Al Faisaly"},away:{name:"Al Nassr"},kickoff:"2026-10-23T13:30:00Z"};
const now = Date.parse("2026-10-23T14:00:00Z");
test("El piloto solo enlaza equipos, liga, fecha y estado verificados", () => {
  assert.match(verifiedTracker(match, now), /al-nassr-fc-vs-al-faisaly-harmah/);
  for (const change of [{league:{code:"SA"}},{home:match.away,away:match.home},{kickoff:"2026-10-24T13:30:00Z"},{status:"FINISHED"}]) assert.equal(verifiedTracker({...match,...change},now),null);
  assert.equal(verifiedTracker(match,now+24*3600000),null);
});
