#!/usr/bin/env node
/**
 * collect-node-licenses.mjs
 *
 * Reads pnpm-licenses.json (produced by `pnpm licenses list --json --prod`)
 * and writes NOTICE-node.md.
 *
 * pnpm v10 output shape:
 *   { "<SPDX-ID>": [{ name, versions: string[], paths, license, author, homepage, description }] }
 *
 * Usage (called from build-notice.mjs, not directly):
 *   node scripts/collect-node-licenses.mjs <input-json> <output-md>
 *
 * Exit 1 if the input file is missing or unparsable (silent skip disabled).
 */

import { readFileSync, writeFileSync } from "fs";
import { resolve } from "path";

const [, , inputPath, outputPath] = process.argv;

if (!inputPath || !outputPath) {
  console.error("Usage: collect-node-licenses.mjs <input.json> <output.md>");
  process.exit(1);
}

const absInput = resolve(inputPath);
const absOutput = resolve(outputPath);

let raw;
try {
  raw = readFileSync(absInput, "utf-8");
} catch (err) {
  console.error(`[collect-node-licenses] Cannot read ${absInput}: ${err.message}`);
  process.exit(1);
}

let data;
try {
  data = JSON.parse(raw);
} catch (err) {
  console.error(`[collect-node-licenses] JSON parse error in ${absInput}: ${err.message}`);
  process.exit(1);
}

// pnpm licenses list --json (v10) produces an object keyed by SPDX identifier.
// Each value is an array of { name, versions: string[], paths, license, author, homepage, description }.
const lines = ["# Node / pnpm dependency licenses\n"];

for (const [spdxId, packages] of Object.entries(data)) {
  lines.push(`## ${spdxId}\n`);
  for (const pkg of packages) {
    const name = pkg.name ?? "(unknown)";
    // pnpm v10 uses `versions` (array); older pnpm used `version` (string)
    const version = Array.isArray(pkg.versions)
      ? pkg.versions.join(", ")
      : (pkg.version ?? "");
    const homepage = pkg.homepage ?? pkg.url ?? "";
    lines.push(`### ${name} ${version}`);
    lines.push(`- **License**: ${spdxId}`);
    if (homepage) lines.push(`- **Homepage**: ${homepage}`);
    lines.push("");
    lines.push("---");
    lines.push("");
  }
}

writeFileSync(absOutput, lines.join("\n"), "utf-8");
console.log(`[collect-node-licenses] Wrote ${absOutput}`);
