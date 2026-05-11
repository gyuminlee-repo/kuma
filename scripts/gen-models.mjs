#!/usr/bin/env node
// gen-models.mjs — Phase 2 Pydantic -> TS generator.
//
// Pipeline:
//   1) PYTHONPATH=python-core python3 scripts/gen_models_schema.py
//      -> combined JSON schema (definitions of every BaseModel subclass)
//   2) json-schema-to-typescript
//      -> typed interfaces
//   3) Prepend a "DO NOT EDIT" banner; write to src/types/models.generated.ts.
//
// Side-effect free in --check mode: only diffs against the on-disk artifact
// and exits 1 on drift. Used by sync-check.mjs.

import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SCHEMA_SCRIPT = path.join(ROOT, "scripts/gen_models_schema.py");
const OUTPUT = path.join(ROOT, "src/types/models.generated.ts");
const JSON2TS = path.join(ROOT, "node_modules/.bin/json2ts");

const BANNER = `/* eslint-disable */
/**
 * AUTO-GENERATED — do not edit by hand.
 * Regenerate via: pnpm gen:models
 * Source: python-core/sidecar_kuro/models.py
 */
`;

const PYTHON_BIN = process.env.PYTHON_BIN || (process.platform === "win32" ? "python" : "python3");

function dumpSchema() {
  const env = { ...process.env, PYTHONPATH: path.join(ROOT, "python-core") };
  return execFileSync(PYTHON_BIN, [SCHEMA_SCRIPT], { env, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
}

function schemaToTs(schemaJson) {
  const res = spawnSync(JSON2TS, [], {
    input: schemaJson,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (res.status !== 0) {
    process.stderr.write(res.stderr || "");
    throw new Error(`json2ts exited with status ${res.status}`);
  }
  return res.stdout;
}

function build() {
  const schema = dumpSchema();
  const ts = schemaToTs(schema);
  return BANNER + ts.trimStart();
}

function isCheck() {
  return process.argv.includes("--check");
}

const generated = build();

if (isCheck()) {
  const current = fs.existsSync(OUTPUT) ? fs.readFileSync(OUTPUT, "utf-8") : "";
  if (current !== generated) {
    console.error(`[gen-models] drift: ${path.relative(ROOT, OUTPUT)} is stale. Run \`pnpm gen:models\`.`);
    process.exit(1);
  }
  console.log(`[gen-models] up to date`);
  process.exit(0);
}

fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });
fs.writeFileSync(OUTPUT, generated, "utf-8");
console.log(`[gen-models] wrote ${path.relative(ROOT, OUTPUT)} (${generated.length} bytes)`);
