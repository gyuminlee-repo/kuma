#!/usr/bin/env node
/**
 * i18n-parity — Verify en.json and ko.json have identical key structure.
 *
 * Exit codes:
 *   0  pass
 *   1  fail (key mismatch or empty values)
 */
import { readFileSync } from "node:fs";

const ROOT = new URL("..", import.meta.url).pathname;
const en = JSON.parse(readFileSync(`${ROOT}src/locales/en.json`, "utf8"));
const ko = JSON.parse(readFileSync(`${ROOT}src/locales/ko.json`, "utf8"));

function flatten(obj, prefix = "") {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object") Object.assign(out, flatten(v, key));
    else out[key] = v;
  }
  return out;
}

const fe = flatten(en);
const fk = flatten(ko);
const keysE = new Set(Object.keys(fe));
const keysK = new Set(Object.keys(fk));

const enOnly = [...keysE].filter((k) => !keysK.has(k));
const koOnly = [...keysK].filter((k) => !keysE.has(k));
const emptyEn = Object.entries(fe).filter(([, v]) => v === "").map(([k]) => k);
const emptyKo = Object.entries(fk).filter(([, v]) => v === "").map(([k]) => k);

console.log(`en keys: ${keysE.size}`);
console.log(`ko keys: ${keysK.size}`);

let ok = true;
if (enOnly.length) {
  ok = false;
  console.error(`\nen-only keys (${enOnly.length}):`);
  for (const k of enOnly.slice(0, 20)) console.error("  " + k);
  if (enOnly.length > 20) console.error(`  ... +${enOnly.length - 20} more`);
}
if (koOnly.length) {
  ok = false;
  console.error(`\nko-only keys (${koOnly.length}):`);
  for (const k of koOnly.slice(0, 20)) console.error("  " + k);
  if (koOnly.length > 20) console.error(`  ... +${koOnly.length - 20} more`);
}
if (emptyEn.length) {
  ok = false;
  console.error(`\nempty en values (${emptyEn.length}):`);
  for (const k of emptyEn.slice(0, 10)) console.error("  " + k);
}
if (emptyKo.length) {
  ok = false;
  console.error(`\nempty ko values (${emptyKo.length}):`);
  for (const k of emptyKo.slice(0, 10)) console.error("  " + k);
}

if (ok) {
  console.log("i18n-parity: ok");
  process.exit(0);
}
console.error("\ni18n-parity: failed. Sync en.json and ko.json.");
process.exit(1);
