#!/usr/bin/env node
// VENDORED from cross-layer-sync skill - DO NOT EDIT.
// Refresh: <dotfiles>/skills/cross-layer-sync/init.mjs --force
// cross-layer-sync/gen-models.mjs — generic Pydantic -> TS generator.
//
// Reads `.cross-layer-sync.json` `genModels` section:
//   {
//     "genModels": [
//       {
//         "module": "sidecar_kuro.models",
//         "pythonPath": "python-core",
//         "output": "src/types/models.generated.ts"
//       }
//     ]
//   }
//
// Each entry runs:
//   PYTHONPATH=<pythonPath> python3 <gen_schema.py> <module>
//   | json-schema-to-typescript
//   -> <output>
//
// --check exits 1 if any output differs from regeneration. Used by sync-check.

import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.cwd();
const argv = process.argv.slice(2);
const isCheck = argv.includes("--check");

const configPath = path.join(ROOT, ".cross-layer-sync.json");
if (!fs.existsSync(configPath)) {
  console.error(`[gen-models] no .cross-layer-sync.json at ${ROOT}`);
  process.exit(2);
}
const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
const entries = config.genModels || [];
if (entries.length === 0) {
  console.log(`[gen-models] no genModels entries — skipping`);
  process.exit(0);
}

const PYTHON_BIN = process.env.PYTHON_BIN || (process.platform === "win32" ? "python" : "python3");
const SCHEMA_SCRIPT = path.join(HERE, "gen_models_schema.py");
const JSON2TS = locateJson2ts();

function locateJson2ts() {
  // Resolve the CLI the way Node resolves a dependency, walking up from ROOT,
  // and run it with this node. The node_modules/.bin shim this used to look
  // for exists only where the install ran, so a worktree nested inside the
  // checkout (or a checkout whose install wrote no .bin) failed the check
  // with "json2ts exited with status null" while the models were current.
  try {
    const pkgFile = createRequire(path.join(ROOT, "package.json")).resolve("json-schema-to-typescript/package.json");
    const bin = JSON.parse(fs.readFileSync(pkgFile, "utf-8")).bin;
    const rel = typeof bin === "string" ? bin : bin?.json2ts;
    if (rel) return { cmd: process.execPath, args: [path.join(path.dirname(pkgFile), rel)], shell: false };
  } catch {
    // not installed where Node can find it: fall back to PATH below
  }
  // The PATH shim has no extension, so on Windows it must run through the
  // shell to resolve json2ts.CMD. Without this spawnSync returns status null.
  return { cmd: "json2ts", args: [], shell: process.platform === "win32" };
}

function bannerFor(entry) {
  return `/* eslint-disable */
/**
 * AUTO-GENERATED — do not edit by hand.
 * Regenerate via: pnpm gen:models
 * Source: ${entry.module} (PYTHONPATH=${entry.pythonPath})
 */
`;
}

function dumpSchema(entry) {
  const env = {
    ...process.env,
    PYTHONPATH: path.resolve(ROOT, entry.pythonPath || "."),
  };
  return execFileSync(PYTHON_BIN, [SCHEMA_SCRIPT, entry.module], {
    env,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
  });
}

function schemaToTs(schemaJson) {
  const res = spawnSync(JSON2TS.cmd, JSON2TS.args, {
    input: schemaJson,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
    shell: JSON2TS.shell,
  });
  if (res.status !== 0) {
    process.stderr.write(res.stderr || "");
    throw new Error(`json2ts exited with status ${res.status}`);
  }
  return res.stdout;
}

let drift = 0;
for (const entry of entries) {
  const ts = bannerFor(entry) + schemaToTs(dumpSchema(entry)).trimStart();
  const outAbs = path.resolve(ROOT, entry.output);
  if (isCheck) {
    const current = fs.existsSync(outAbs) ? fs.readFileSync(outAbs, "utf-8") : "";
    if (current !== ts) {
      console.error(`[gen-models] drift: ${entry.output} is stale (module=${entry.module})`);
      drift++;
    } else {
      console.log(`[gen-models] up to date: ${entry.output}`);
    }
  } else {
    fs.mkdirSync(path.dirname(outAbs), { recursive: true });
    fs.writeFileSync(outAbs, ts, "utf-8");
    console.log(`[gen-models] wrote ${entry.output} (${ts.length} bytes)`);
  }
}

process.exit(drift > 0 ? 1 : 0);
