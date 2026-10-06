import test from "node:test";
import assert from "node:assert/strict";
import {quantityValue,grossProceeds,proceeds} from "../src/lib/decision.ts";

test("gross proceeds use full forecast precision and fractional quantities", () => {
  const totals = proceeds("10", "1500", "1428.571429");
  assert.equal(totals.observed, 15000);
  assert.ok(Math.abs(totals.estimated - 14285.71429) < 1e-8);
  assert.ok(Math.abs(totals.difference + 714.28571) < 1e-8);
  assert.equal(grossProceeds("2.5", "100"), 250);
  assert.equal(proceeds("1", "100", "100").difference, 0);
});

test("invalid, missing and overflow values remain unavailable", () => {
  for (const value of ["", " ", "0", "-1", "NaN", "Infinity", "1e309", "0x10", "abc"]) {
    assert.equal(quantityValue(value), null);
    assert.equal(grossProceeds(value, "100"), null);
  }
  assert.equal(grossProceeds("1", null), null);
  assert.equal(grossProceeds("1", "0"), null);
  assert.equal(grossProceeds("9".repeat(308), "100"), null);
  assert.equal(proceeds("10", null, "100").difference, null);
});
