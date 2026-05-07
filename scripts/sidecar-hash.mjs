/**
 * sidecar-hash.mjs
 *
 * Build-time script: computes SHA-256 for each sidecar binary in
 * src-tauri/binaries/ and writes src-tauri/sidecar-hashes.json.
 *
 * Key format uses base names (no platform suffix) so the Rust verifier can
 * look up hashes by platform-independent name at runtime:
 *   "kuro-sidecar" -> hash of kuro-sidecar-<current-triple>[.exe]
 *   "mame-sidecar" -> hash of mame-sidecar-<current-triple>[.exe]
 *
 * All found binaries are included; the runtime picks the entry matching the
 * current platform at startup.
 *
 * Environment variable overrides (used by tests):
 *   SIDECAR_HASH_BINARIES_DIR  override default src-tauri/binaries path
 *   SIDECAR_HASH_OUTPUT_PATH   override default src-tauri/sidecar-hashes.json path
 */

import { createHash } from "crypto";
import { createReadStream, existsSync, readdirSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { pipeline } from "stream/promises";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");

const BINARIES_DIR =
  process.env.SIDECAR_HASH_BINARIES_DIR ||
  resolve(REPO_ROOT, "src-tauri", "binaries");

const OUTPUT_PATH =
  process.env.SIDECAR_HASH_OUTPUT_PATH ||
  resolve(REPO_ROOT, "src-tauri", "sidecar-hashes.json");

/** Compute SHA-256 of a file, returns hex string. */
async function sha256File(filePath) {
  const hash = createHash("sha256");
  await pipeline(createReadStream(filePath), hash);
  return hash.digest("hex");
}

/**
 * Strip the target-triple suffix (and optional .exe) to get the base name.
 * e.g. "kuro-sidecar-x86_64-unknown-linux-gnu"  -> "kuro-sidecar"
 *      "mame-sidecar-x86_64-pc-windows-msvc.exe" -> "mame-sidecar"
 */
function baseName(filename) {
  // Remove .exe suffix first
  const noExt = filename.replace(/\.exe$/, "");
  // Match known sidecar base names: "kuro-sidecar" or "mame-sidecar".
  const match = noExt.match(/^((?:kuro|mame)-sidecar)/);
  return match ? match[1] : noExt;
}

async function main() {
  if (!existsSync(BINARIES_DIR)) {
    console.error(`[sidecar-hash] binaries dir not found: ${BINARIES_DIR}`);
    console.error(
      "[sidecar-hash] Run `pnpm run sidecar:build` first to produce binaries."
    );
    process.exit(1);
  }

  const files = readdirSync(BINARIES_DIR).filter(
    (f) => f.startsWith("kuro-sidecar") || f.startsWith("mame-sidecar")
  );

  if (files.length === 0) {
    console.error(
      "[sidecar-hash] No sidecar binaries found. Run `pnpm run sidecar:build` first."
    );
    process.exit(1);
  }

  /** @type {Record<string, string>} */
  const hashes = {};

  for (const file of files.sort()) {
    const fullPath = resolve(BINARIES_DIR, file);
    process.stdout.write(`[sidecar-hash] Hashing ${file} ... `);
    const hash = await sha256File(fullPath);
    // Store under both the full filename (for precise lookup) and the base name
    // (for platform-independent lookup when Tauri strips the triple suffix).
    hashes[file] = hash;
    const base = baseName(file);
    // Base name entry: last one wins if multiple platforms are present on this
    // machine (cross-build scenario). Runtime always reads the entry matching
    // the actual binary it is about to spawn, so this is only a fallback.
    hashes[base] = hash;
    console.log("ok");
  }

  const json = JSON.stringify(hashes, null, 2) + "\n";
  writeFileSync(OUTPUT_PATH, json, "utf8");
  console.log(`[sidecar-hash] Written: ${OUTPUT_PATH}`);
  console.log(`[sidecar-hash] Entries: ${Object.keys(hashes).join(", ")}`);
}

main().catch((err) => {
  console.error("[sidecar-hash] Fatal:", err);
  process.exit(1);
});
