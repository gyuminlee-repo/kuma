#!/usr/bin/env node
/**
 * sync-check-janus-defaults.mjs, MAME Janus export defaults, TS vs Python.
 *
 * `DEFAULT_JANUS_SETTINGS` (src/lib/mame/janusSettings.ts) is a hand-written
 * copy of the constants behind `JanusSettings`
 * (kuma_core/mame/export/janus_mapping.py): DEFAULT_VOLUME_UL,
 * DEFAULT_SAMPLE_TYPE, DEFAULT_LIQUID_CLASS, DEFAULT_SOURCE_RACKS,
 * DEFAULT_DEST_RACK, DEFAULT_INCLUDE_VERDICTS, DEST_LAYOUT_COMPACT and
 * SCHEMA_DEVICE9. The TS comment said "mirroring JanusSettings" and nothing
 * enforced it, so one side could move and the operator would approve a plate in
 * the dialog that the sidecar does not write.
 *
 * What is compared is the *wire payload*, not the two literals: the TS defaults
 * are pushed through the same camelCase -> snake_case mapping `toRpcParams`
 * uses, and the result must equal `JanusSettings().to_payload()`. That covers
 * the mapping as well as the values, which is the shape the sidecar actually
 * receives.
 *
 * Wired into CI through `.cross-layer-sync.json` `checks[]` as a `command`
 * check, so `node scripts/sync-check-all.mjs` (pnpm sync:check) runs it.
 *
 * Usage: node scripts/sync-check-janus-defaults.mjs
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TS_FILE = "src/lib/mame/janusSettings.ts";
const PY_FILE = "kuma_core/mame/export/janus_mapping.py";

/**
 * TS field -> RPC key. Duplicated from `toRpcParams` on purpose: a check that
 * imported the mapping could not notice the mapping itself going wrong, so the
 * table is restated here and `toRpcParams` is verified against it below.
 */
const FIELD_TO_RPC_KEY = {
  destLayout: "dest_layout",
  includeVerdicts: "include_verdicts",
  includeFallback: "include_fallback",
  outputSchema: "output_schema",
  volume: "volume",
  sampleType: "sample_type",
  liquidClass: "liquid_class",
  sourceRacks: "source_racks",
  destRack: "dest_rack",
};

const problems = [];

function pythonBin() {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  // Local dev keeps the project in a 3.11 venv (PyInstaller/biopython wheels);
  // CI installs into the job interpreter and has no .venv.
  const venv = path.join(ROOT, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  if (fs.existsSync(venv)) return venv;
  return process.platform === "win32" ? "python" : "python3";
}

/** Default payload as the sidecar itself computes it. */
function pythonDefaults() {
  const code = [
    "import json",
    "from kuma_core.mame.export.janus_mapping import JanusSettings",
    "p = JanusSettings().to_payload()",
    // `columns` is the header the schema implies, not a settable default.
    "p.pop('columns', None)",
    "print(json.dumps(p, sort_keys=True))",
  ].join("\n");
  const res = spawnSync(pythonBin(), ["-c", code], { cwd: ROOT, encoding: "utf-8" });
  if (res.status !== 0) {
    throw new Error(
      `python could not report the Janus defaults (${pythonBin()}): ` +
        (res.stderr || res.error?.message || "unknown error").trim(),
    );
  }
  return JSON.parse(res.stdout);
}

/**
 * Read the `DEFAULT_JANUS_SETTINGS` object literal out of the TS source.
 *
 * Evaluated rather than type-checked: the literal is plain data, and running
 * the TS module would need a transpiler this repo cannot install from WSL.
 */
function tsDefaults() {
  const src = fs.readFileSync(path.join(ROOT, TS_FILE), "utf-8");
  const marker = "export const DEFAULT_JANUS_SETTINGS";
  const start = src.indexOf(marker);
  if (start === -1) throw new Error(`${TS_FILE}: DEFAULT_JANUS_SETTINGS not found`);
  const open = src.indexOf("{", start);
  let depth = 0;
  let end = -1;
  for (let i = open; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) { end = i; break; }
    }
  }
  if (end === -1) throw new Error(`${TS_FILE}: unterminated DEFAULT_JANUS_SETTINGS literal`);
  const literal = src.slice(open, end + 1);
  return new Function(`return (${literal});`)();
}

/** Assert `toRpcParams` still maps every field the way this check assumes. */
function checkRpcMapping() {
  const src = fs.readFileSync(path.join(ROOT, TS_FILE), "utf-8");
  const body = src.slice(src.indexOf("export function toRpcParams"));
  for (const [field, key] of Object.entries(FIELD_TO_RPC_KEY)) {
    if (!new RegExp(`\\b${key}:\\s*settings\\.${field}\\b`).test(body)) {
      problems.push(`toRpcParams does not map ${field} -> ${key} (${TS_FILE})`);
    }
  }
}

function normalize(value) {
  return JSON.stringify(value === undefined ? null : value);
}

function main() {
  const py = pythonDefaults();
  const ts = tsDefaults();

  const tsFields = Object.keys(ts).sort();
  const knownFields = Object.keys(FIELD_TO_RPC_KEY).sort();
  if (tsFields.join(",") !== knownFields.join(",")) {
    problems.push(
      `DEFAULT_JANUS_SETTINGS fields [${tsFields}] differ from the known set ` +
        `[${knownFields}]. Extend FIELD_TO_RPC_KEY in this script together with ` +
        `${TS_FILE} and ${PY_FILE}.`,
    );
  }

  const mapped = {};
  for (const [field, key] of Object.entries(FIELD_TO_RPC_KEY)) {
    if (field in ts) mapped[key] = ts[field];
  }

  const pyKeys = Object.keys(py).sort();
  const mappedKeys = Object.keys(mapped).sort();
  for (const key of pyKeys) {
    if (!mappedKeys.includes(key)) {
      problems.push(`${PY_FILE} default "${key}" has no counterpart in ${TS_FILE}`);
    }
  }
  for (const key of mappedKeys) {
    if (!pyKeys.includes(key)) {
      problems.push(`${TS_FILE} default "${key}" has no counterpart in ${PY_FILE}`);
      continue;
    }
    if (normalize(py[key]) !== normalize(mapped[key])) {
      problems.push(
        `"${key}" drift: python=${normalize(py[key])} ts=${normalize(mapped[key])}`,
      );
    }
  }

  checkRpcMapping();

  if (problems.length > 0) {
    console.error("[janus-defaults] FAIL: MAME Janus defaults are out of sync");
    for (const p of problems) console.error(`  - ${p}`);
    console.error(
      `  Fix by editing ${TS_FILE} and ${PY_FILE} together; the Python ` +
        "constants are the instrument-facing side.",
    );
    process.exit(1);
  }

  console.log(
    `[janus-defaults] OK: ${mappedKeys.length} defaults aligned between ${TS_FILE} and ${PY_FILE}`,
  );
}

try {
  main();
} catch (err) {
  console.error(`[janus-defaults] FAIL: ${err.message}`);
  process.exit(1);
}
