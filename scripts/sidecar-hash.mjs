/**
 * sidecar-hash.mjs
 *
 * Build-time script: computes SHA-256 for each sidecar binary in
 * src-tauri/binaries/ and merges the result into
 * src-tauri/sidecar-hashes.json.
 *
 * Key format: full filename WITH platform triple suffix (and .exe on Windows).
 *   e.g. "kuro-sidecar-aarch64-apple-darwin"
 *        "mame-sidecar-x86_64-pc-windows-msvc.exe"
 *
 * Merge semantics (cross-platform safety):
 *   - The existing manifest is read first (treated as `{}` if missing).
 *   - Entries for binaries present in this build run are overwritten.
 *   - Entries for OTHER platforms (not built in this run) are PRESERVED.
 *   - Base-name keys (e.g. "kuro-sidecar") are no longer written. Any
 *     legacy base-name keys found in the existing manifest are dropped on
 *     rewrite to avoid platform-ambiguous lookups.
 *
 * Environment variable overrides (used by tests):
 *   SIDECAR_HASH_BINARIES_DIR  override default src-tauri/binaries path
 *   SIDECAR_HASH_OUTPUT_PATH   override default src-tauri/sidecar-hashes.json path
 */

import { createHash } from "crypto";
import {
  createReadStream,
  existsSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from "fs";
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
 * Decide whether a manifest key looks like a triple-suffixed full filename
 * (e.g. "kuro-sidecar-aarch64-apple-darwin"), as opposed to a legacy bare
 * base name ("kuro-sidecar", "mame-sidecar"). Triple-suffix keys are kept
 * for cross-platform safety; base-name keys are dropped on rewrite.
 */
function isTripleSuffixedKey(key) {
  if (
    key === "kuro-sidecar" ||
    key === "mame-sidecar" ||
    key === "evolvepro-sidecar"
  )
    return false;
  return (
    key.startsWith("kuro-sidecar-") ||
    key.startsWith("mame-sidecar-") ||
    key.startsWith("evolvepro-sidecar-")
  );
}

/**
 * Read existing manifest as object.
 *
 * Returns `{}` if the file does not exist (first-ever run).
 * Throws for malformed JSON or wrong shape: silently starting fresh would
 * destroy hashes for unbuilt platforms and ship a broken bundle, which is
 * exactly the failure mode merge mode exists to prevent. Fail-fast so the
 * user fixes the manifest by hand.
 */
function readExistingManifest(path) {
  if (!existsSync(path)) return {};
  const text = readFileSync(path, "utf8");
  const parsed = JSON.parse(text); // throws SyntaxError on malformed JSON
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new TypeError(
      `Existing manifest at ${path} is not a JSON object (got ${
        Array.isArray(parsed) ? "array" : typeof parsed
      }).`,
    );
  }
  return parsed;
}

async function main() {
  if (!existsSync(BINARIES_DIR)) {
    console.error(`[sidecar-hash] binaries dir not found: ${BINARIES_DIR}`);
    console.error(
      "[sidecar-hash] Run `pnpm run sidecar:build` first to produce binaries.",
    );
    process.exit(1);
  }

  const files = readdirSync(BINARIES_DIR).filter(
    (f) =>
      f.startsWith("kuro-sidecar") ||
      f.startsWith("mame-sidecar") ||
      f.startsWith("evolvepro-sidecar"),
  );

  if (files.length === 0) {
    console.error(
      "[sidecar-hash] No sidecar binaries found. Run `pnpm run sidecar:build` first.",
    );
    process.exit(1);
  }

  // Start from existing manifest so other platforms' hashes survive.
  const existing = readExistingManifest(OUTPUT_PATH);

  // Drop legacy base-name keys; keep only triple-suffixed entries.
  /** @type {Record<string, string>} */
  const hashes = {};
  for (const [k, v] of Object.entries(existing)) {
    if (isTripleSuffixedKey(k) && typeof v === "string") {
      hashes[k] = v;
    }
  }

  for (const file of files.sort()) {
    const fullPath = resolve(BINARIES_DIR, file);
    process.stdout.write(`[sidecar-hash] Hashing ${file} ... `);
    const hash = await sha256File(fullPath);
    hashes[file] = hash;
    console.log("ok");
  }

  // Deterministic key sort, 2-space indent, trailing newline.
  const sorted = {};
  for (const key of Object.keys(hashes).sort()) {
    sorted[key] = hashes[key];
  }
  const json = JSON.stringify(sorted, null, 2) + "\n";
  writeFileSync(OUTPUT_PATH, json, "utf8");
  console.log(`[sidecar-hash] Written: ${OUTPUT_PATH}`);
  console.log(`[sidecar-hash] Entries: ${Object.keys(sorted).join(", ")}`);
}

main().catch((err) => {
  console.error("[sidecar-hash] Fatal:", err);
  process.exit(1);
});
