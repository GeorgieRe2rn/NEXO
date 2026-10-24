import test from "node:test";
import assert from "node:assert/strict";
import { localDay, localTime, kickoffLabel, pct } from "../src/api/client.js";

test("La medianoche UTC no adelanta el día de Hermosillo", () => {
  assert.equal(localDay("2026-10-15T02:00:00Z"), "2026-10-14");
  assert.equal(localTime("2026-10-15T02:00:00Z"), "19:00");
});
test("Conversión del horario verificado de Everton contra Chelsea", () => {
  assert.equal(localTime("2026-10-17T11:30:00Z"), "04:30");
  assert.equal(localDay("2026-10-17T11:30:00Z"), "2026-10-17");
  assert.match(kickoffLabel("2026-10-17T11:30:00Z"), /2026/);
});
test("Una probabilidad ausente no aparece como 0%", () => {
  assert.equal(pct(null), "—");
  assert.equal(pct(undefined), "—");
  assert.equal(pct(0), "0%");
  assert.equal(pct(.425), "43%");
});
