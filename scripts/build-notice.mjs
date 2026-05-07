#!/usr/bin/env node
/**
 * build-notice.mjs
 *
 * Merges NOTICE-rust.md, NOTICE-node.md, and NOTICE-python.md into a single
 * NOTICE.md and copies it into src-tauri/resources/ so Tauri bundles it.
 *
 * Called from the CI build job after all three partial-notice files exist.
 *
 * Exit 1 if any required input is missing (silent skip disabled).
 */

import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

const INPUTS = [
  { label: "Rust / Cargo dependencies", path: resolve(ROOT, "NOTICE-rust.md") },
  { label: "Node / pnpm dependencies", path: resolve(ROOT, "NOTICE-node.md") },
  { label: "Python dependencies", path: resolve(ROOT, "NOTICE-python.md") },
];

const OUTPUT = resolve(ROOT, "NOTICE.md");
const TAURI_RESOURCE_DIR = resolve(ROOT, "src-tauri", "resources");
const TAURI_RESOURCE_TARGET = resolve(TAURI_RESOURCE_DIR, "NOTICE.md");

// --- Validate inputs ---
let missing = false;
for (const { label, path } of INPUTS) {
  if (!existsSync(path)) {
    console.error(`[build-notice] Missing required input for ${label}: ${path}`);
    missing = true;
  }
}
if (missing) {
  console.error("[build-notice] One or more NOTICE source files are missing. Aborting.");
  process.exit(1);
}

// --- Assemble ---
const header = `# NOTICE — Third-Party Software Licenses

This distribution includes third-party software with the licenses listed below.
The full license text for each component is included in the relevant section.

`;

const sections = INPUTS.map(({ path }) => readFileSync(path, "utf-8").trim()).join(
  "\n\n---\n\n"
);

const full = header + sections + "\n";
writeFileSync(OUTPUT, full, "utf-8");
console.log(`[build-notice] Wrote ${OUTPUT}`);

// --- Copy to Tauri resources ---
mkdirSync(TAURI_RESOURCE_DIR, { recursive: true });
copyFileSync(OUTPUT, TAURI_RESOURCE_TARGET);
console.log(`[build-notice] Copied to ${TAURI_RESOURCE_TARGET}`);
