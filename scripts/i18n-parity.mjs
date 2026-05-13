#!/usr/bin/env node
/**
 * i18n-parity — Verify all locale files have identical key structure as en.json.
 *
 * Exit codes:
 *   0  pass
 *   1  fail (key mismatch or empty values)
 */
import { readFileSync, readdirSync } from "node:fs";

const ROOT = new URL("..", import.meta.url).pathname;
const LOCALES_DIR = `${ROOT}src/locales/`;
const en = JSON.parse(readFileSync(`${LOCALES_DIR}en.json`, "utf8"));

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
const keysE = new Set(Object.keys(fe));
console.log(`en keys: ${keysE.size}`);

let ok = true;
const localeFiles = readdirSync(LOCALES_DIR)
  .filter((f) => f.endsWith(".json") && f !== "en.json")
  .sort();

for (const file of localeFiles) {
  const lang = file.replace(/\.json$/, "");
  const data = JSON.parse(readFileSync(`${LOCALES_DIR}${file}`, "utf8"));
  const fl = flatten(data);
  const keysL = new Set(Object.keys(fl));
  const onlyEn = [...keysE].filter((k) => !keysL.has(k));
  const onlyL = [...keysL].filter((k) => !keysE.has(k));
  const empty = Object.entries(fl).filter(([, v]) => v === "").map(([k]) => k);
  console.log(`${lang} keys: ${keysL.size}`);
  if (onlyEn.length) {
    ok = false;
    console.error(`  en-only (missing in ${lang}): ${onlyEn.length}`);
    onlyEn.slice(0, 5).forEach((k) => console.error(`    - ${k}`));
  }
  if (onlyL.length) {
    ok = false;
    console.error(`  ${lang}-only (extra): ${onlyL.length}`);
    onlyL.slice(0, 5).forEach((k) => console.error(`    - ${k}`));
  }
  if (empty.length) {
    ok = false;
    console.error(`  ${lang} empty values: ${empty.length}`);
    empty.slice(0, 5).forEach((k) => console.error(`    - ${k}`));
  }
}

console.log(ok ? "i18n-parity: ok" : "i18n-parity: FAIL");
process.exit(ok ? 0 : 1);
