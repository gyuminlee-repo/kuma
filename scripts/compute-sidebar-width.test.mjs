// Tests for compute-sidebar-width.mjs
// Run: node --test scripts/compute-sidebar-width.test.mjs
import { computeMaxLabelWidth } from "./compute-sidebar-width.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";

test("computes max label width with padding", () => {
  const labels = ["short", "a much longer label here"];
  const w = computeMaxLabelWidth(labels, { fontSize: 14, padding: 44 });
  assert.ok(w > 200 && w < 400, `Expected 200-400, got ${w}`);
});

test("returns fallback for empty list", () => {
  assert.equal(
    computeMaxLabelWidth([], { fontSize: 14, padding: 44, fallback: 240 }),
    240,
  );
});

test("longer label produces larger width", () => {
  // Use labels long enough to exceed the 180 px minimum clamp.
  const short = computeMaxLabelWidth(
    ["Workspace save"],
    { fontSize: 14, padding: 44 },
  );
  const long = computeMaxLabelWidth(
    ["Pool Filters & Run longer text here"],
    { fontSize: 14, padding: 44 },
  );
  assert.ok(long > short, `Expected long (${long}) > short (${short})`);
});
