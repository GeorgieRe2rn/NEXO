import test from "node:test";
import assert from "node:assert/strict";
import { isUpcoming, normalizeSearch } from "../src/utils/matchFilters.js";

test("La búsqueda encuentra América, Querétaro y Atlético sin acentos", () => {
  assert.ok(normalizeSearch("América vs Querétaro").includes(normalizeSearch(" america ")));
  assert.ok(normalizeSearch("Atlético Madrid").includes(normalizeSearch("ATLETICO")));
});

test("Próximos excluye horas vencidas aunque la fuente aún diga programado", () => {
  const now = "2026-10-16T07:00:00Z";
  assert.equal(isUpcoming({status:"SCHEDULED",kickoff:"2026-10-16T06:59:00Z"},now),false);
  assert.equal(isUpcoming({status:"SCHEDULED",kickoff:now},now),false);
  assert.equal(isUpcoming({status:"SCHEDULED",kickoff:"2026-10-16T08:00:00Z"},now),true);
  assert.equal(isUpcoming({status:"FINISHED",kickoff:"2026-10-16T08:00:00Z"},now),false);
});
