/**
 * sidecar-hash-postbuild.mjs
 *
 * Shape A post-bundle integrity manifest injection.
 *
 * Why this exists:
 *   `pnpm run sidecar:hash` hashes the *unsigned* PyInstaller output in
 *   `src-tauri/binaries/`. Tauri then runs ad-hoc signing during `tauri build`
 *   which mutates the binary bytes inside the produced .app bundle. The
 *   result: the Rust runtime integrity check compares the recorded hash
 *   against the bundled binary and always fails.
 *
 *   This script runs *after* `tauri build` and:
 *     1. Locates the produced kuma.app bundle.
 *     2. Re-signs each sidecar with `codesign --force --sign -` (no
 *        `--options runtime`) to strip the hardened runtime flag that
 *        `tauri build` applied. This is required because hardened runtime
 *        with ad-hoc signing enforces library validation, which rejects
 *        the differently-signed `libpython3.11.dylib` that PyInstaller
 *        unpacks at runtime ("non-platform have different Team IDs" error).
 *        Since the project does not notarize (signingIdentity = "-"),
 *        hardened runtime serves no purpose and only breaks the sidecar.
 *     3. Computes SHA-256 of the now-finalized sidecar binaries inside
 *        `kuma.app/Contents/MacOS/`.
 *     4. Writes the manifest into
 *        `kuma.app/Contents/Resources/sidecar-hashes.json` in the same
 *        schema as the unsigned manifest.
 *     5. Re-seals the .app top-level signature (NOT --deep) so the bundle
 *        validates again.
 *     6. Regenerates the DMG so the shipped artifact matches the patched
 *        .app.
 *
 *   On Linux/Windows where there is no codesign step inside `tauri build`,
 *   the bundled binaries match `src-tauri/binaries/` exactly, so this
 *   script is a no-op on those platforms (still writes the manifest, still
 *   safe).
 *
 *   Schema (matches `scripts/sidecar-hash.mjs`):
 *     {
 *       "kuro-sidecar-<triple>[.exe]": "<sha256-hex>",
 *       "kuro-sidecar":                "<sha256-hex>",
 *       "mame-sidecar-<triple>[.exe]": "<sha256-hex>",
 *       "mame-sidecar":                "<sha256-hex>"
 *     }
 */

import { createHash } from "node:crypto";
import {
  createReadStream,
  existsSync,
  readdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
// Merge-mode manifest helpers: cross-platform safety so writing the manifest
// from one host (e.g. macOS post-build) does not erase the Windows/Linux
// hashes recorded in src-tauri/sidecar-hashes.json by previous builds.
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { pipeline } from "node:stream/promises";
import process from "node:process";
import os from "node:os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");

const PLATFORM = process.platform;
const PLATFORM_SUFFIX =
  PLATFORM === "win32" ? "win" : PLATFORM; // matches scripts/run-tauri.mjs

const CARGO_TARGET_DIR =
  process.env.CARGO_TARGET_DIR ||
  resolve(REPO_ROOT, "src-tauri", `target-${PLATFORM_SUFFIX}`);

const PRODUCT_NAME = "kuma";

const TRIPLE = (() => {
  const arch = os.arch() === "arm64" ? "aarch64" : "x86_64";
  if (PLATFORM === "darwin") return `${arch}-apple-darwin`;
  if (PLATFORM === "win32") return `${arch}-pc-windows-msvc`;
  return `${arch}-unknown-linux-gnu`;
})();

const EXE = PLATFORM === "win32" ? ".exe" : "";

/** Compute SHA-256 of a file, returns hex string. */
async function sha256File(filePath) {
  const hash = createHash("sha256");
  await pipeline(createReadStream(filePath), hash);
  return hash.digest("hex");
}

function log(...args) {
  console.log("[sidecar-hash-postbuild]", ...args);
}

function fail(msg) {
  console.error("[sidecar-hash-postbuild] FATAL:", msg);
  process.exit(1);
}

function run(cmd, args, options = {}) {
  log(`$ ${cmd} ${args.join(" ")}`);
  const r = spawnSync(cmd, args, { stdio: "inherit", ...options });
  if (r.status !== 0) {
    fail(`${cmd} exited with code ${r.status}`);
  }
}

/**
 * Locate the produced .app bundle (macOS) or fall back to platform-specific
 * paths. Returns { kind, paths } where kind is one of "macos-app", "linux",
 * "windows".
 */
function locateBundles() {
  if (PLATFORM === "darwin") {
    const appPath = join(
      CARGO_TARGET_DIR,
      "release",
      "bundle",
      "macos",
      `${PRODUCT_NAME}.app`,
    );
    if (!existsSync(appPath)) {
      fail(
        `Expected ${PRODUCT_NAME}.app at ${appPath}. Run \`tauri build\` first.`,
      );
    }
    const dmgDir = join(CARGO_TARGET_DIR, "release", "bundle", "dmg");
    return { kind: "macos-app", appPath, dmgDir };
  }

  if (PLATFORM === "win32") {
    const exeBase = join(CARGO_TARGET_DIR, "release");
    return { kind: "windows", exeBase };
  }

  // Linux: .deb / .AppImage carry the sidecars unsigned, so the unsigned
  // manifest is already correct. Treat this as a no-op writer for
  // consistency with the legacy `sidecar:hash` step.
  return { kind: "linux" };
}

/**
 * Re-sign each sidecar inside the .app *without* the hardened runtime flag.
 * `tauri build` applies `--options runtime` during bundling, which together
 * with ad-hoc signing enforces library validation and rejects the
 * differently-signed libpython3.11.dylib that PyInstaller unpacks at
 * runtime. Re-signing with bare `--force --sign -` clears the runtime flag
 * (flags 0x10002 → 0x2). Since the project does not notarize, hardened
 * runtime is not needed.
 *
 * This must run BEFORE hashing because re-signing changes binary bytes.
 */
function stripHardenedRuntimeFromSidecars(appPath) {
  const macosDir = join(appPath, "Contents", "MacOS");
  for (const base of ["kuro-sidecar", "mame-sidecar"]) {
    const filePath = join(macosDir, base);
    if (!existsSync(filePath)) {
      fail(`Expected sidecar inside bundle: ${filePath}`);
    }
    log(`re-signing ${base} without hardened runtime`);
    // --force overwrites the existing signature; no --options runtime; no
    // --deep (sidecar is single-file PyInstaller --onefile output, the
    // embedded libpython is unpacked at runtime, not nested inside the
    // signed binary).
    run("codesign", ["--force", "--sign", "-", filePath]);
  }
}

/**
 * Triple-suffixed key shape (e.g. "kuro-sidecar-aarch64-apple-darwin").
 * Bare "kuro-sidecar"/"mame-sidecar" base-name keys are platform-ambiguous
 * and intentionally dropped on rewrite.
 */
function isTripleSuffixedKey(key) {
  if (key === "kuro-sidecar" || key === "mame-sidecar") return false;
  return key.startsWith("kuro-sidecar-") || key.startsWith("mame-sidecar-");
}

/**
 * Read existing manifest as an object, fail-fast on malformed JSON to avoid
 * silently dropping other-platform hashes.
 */
function readExistingManifest(path) {
  if (!existsSync(path)) return {};
  const text = readFileSync(path, "utf8");
  const parsed = JSON.parse(text);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    fail(
      `Existing manifest at ${path} is not a JSON object (got ${
        Array.isArray(parsed) ? "array" : typeof parsed
      }).`,
    );
  }
  return parsed;
}

/** Merge `additions` into existing triple-suffixed entries, drop base-name keys. */
function mergeManifest(existing, additions) {
  const merged = {};
  for (const [k, v] of Object.entries(existing)) {
    if (isTripleSuffixedKey(k) && typeof v === "string") merged[k] = v;
  }
  for (const [k, v] of Object.entries(additions)) {
    merged[k] = v;
  }
  const sorted = {};
  for (const key of Object.keys(merged).sort()) sorted[key] = merged[key];
  return sorted;
}

/**
 * Hash both sidecars under <appPath>/Contents/MacOS. Returns ONLY the entries
 * for this build (caller merges with the existing manifest).
 */
async function hashMacosSidecars(appPath) {
  const macosDir = join(appPath, "Contents", "MacOS");
  if (!existsSync(macosDir)) fail(`MacOS dir missing: ${macosDir}`);

  const additions = {};
  for (const base of ["kuro-sidecar", "mame-sidecar"]) {
    const filePath = join(macosDir, base);
    if (!existsSync(filePath)) {
      fail(`Expected sidecar inside bundle: ${filePath}`);
    }
    const h = await sha256File(filePath);
    additions[`${base}-${TRIPLE}`] = h;
    log(`hashed ${filePath} = ${h.slice(0, 16)}...`);
  }
  return additions;
}

/**
 * Write the manifest JSON into the .app's Resources directory using the
 * same schema as `scripts/sidecar-hash.mjs`.
 */
function writeManifest(targetPath, manifest) {
  const json = JSON.stringify(manifest, null, 2) + "\n";
  writeFileSync(targetPath, json, "utf8");
  log(`wrote manifest → ${targetPath}`);
}

/**
 * Re-seal the .app top-level signature with the same ad-hoc identity tauri
 * used. Do NOT pass --deep: that would re-walk nested executables, replace
 * sidecar signatures, and (more importantly) is unnecessary because we
 * only changed a resource file, not the executables.
 */
function resealMacosApp(appPath) {
  run("codesign", ["--force", "--sign", "-", appPath]);
  run("codesign", ["--verify", "--verbose=2", appPath]);
}

/**
 * Regenerate the DMG with the patched .app inside. We use hdiutil directly
 * (instead of re-running `tauri bundle`) because the bundle step has been
 * known to re-sign and undo our manifest patch. hdiutil is the same tool
 * tauri eventually calls.
 *
 * The original DMG name is preserved by reading version from package.json.
 */
function regenerateDmg(appPath, dmgDir) {
  const pkgJsonPath = join(REPO_ROOT, "package.json");
  const pkg = JSON.parse(readFileSync(pkgJsonPath, "utf8"));
  const version = pkg.version;
  if (!version) fail("Could not read version from package.json");

  const arch = os.arch() === "arm64" ? "aarch64" : "x86_64";
  const dmgName = `${PRODUCT_NAME}_${version}_${arch}.dmg`;
  const dmgPath = join(dmgDir, dmgName);

  // Remove old dmg if present so hdiutil doesn't fail with "exists".
  if (existsSync(dmgPath)) {
    run("rm", ["-f", dmgPath]);
  }

  run("hdiutil", [
    "create",
    "-volname",
    PRODUCT_NAME,
    "-srcfolder",
    appPath,
    "-ov",
    "-format",
    "UDZO",
    dmgPath,
  ]);

  log(`regenerated DMG → ${dmgPath}`);
}

/**
 * Hash the unsigned binaries under src-tauri/binaries/ (Linux/Windows path)
 * and MERGE the result into `src-tauri/sidecar-hashes.json`. Other-platform
 * entries already in the manifest are preserved; base-name keys are dropped.
 */
async function writeLegacyManifest() {
  const binariesDir = join(REPO_ROOT, "src-tauri", "binaries");
  if (!existsSync(binariesDir)) return;
  const out = join(REPO_ROOT, "src-tauri", "sidecar-hashes.json");
  const existing = readExistingManifest(out);

  const additions = {};
  const files = readdirSync(binariesDir).filter(
    (f) => f.startsWith("kuro-sidecar") || f.startsWith("mame-sidecar"),
  );
  for (const file of files.sort()) {
    const full = join(binariesDir, file);
    if (!statSync(full).isFile()) continue;
    additions[file] = await sha256File(full);
  }

  const merged = mergeManifest(existing, additions);
  writeFileSync(out, JSON.stringify(merged, null, 2) + "\n", "utf8");
  log(`wrote legacy manifest → ${out}`);
}

async function main() {
  log(`platform=${PLATFORM} triple=${TRIPLE} CARGO_TARGET_DIR=${CARGO_TARGET_DIR}`);

  // Always keep the legacy manifest in src-tauri/ in sync (covers Linux/
  // Windows runtimes and Tauri's resource-bundling pickup at next build).
  await writeLegacyManifest();

  const bundle = locateBundles();

  if (bundle.kind !== "macos-app") {
    log(`Non-macOS platform (${PLATFORM}); legacy manifest is authoritative.`);
    return;
  }

  // macOS Shape A flow.
  // 1. Strip hardened-runtime flag from sidecars (re-sign, no --options
  //    runtime). Must precede hashing because re-signing mutates bytes.
  stripHardenedRuntimeFromSidecars(bundle.appPath);

  // 2. Hash post-re-sign sidecars. additions only; merge against any
  //    existing in-bundle manifest so cross-platform entries are preserved.
  const additions = await hashMacosSidecars(bundle.appPath);
  const targetManifest = join(
    bundle.appPath,
    "Contents",
    "Resources",
    "sidecar-hashes.json",
  );
  const existingInBundle = readExistingManifest(targetManifest);
  const manifest = mergeManifest(existingInBundle, additions);

  // 3. Write manifest into bundle.
  writeManifest(targetManifest, manifest);

  // 4. Re-seal top-level .app signature so the manifest write does not
  //    invalidate the bundle.
  resealMacosApp(bundle.appPath);

  // 5. Regenerate DMG with patched .app contents.
  regenerateDmg(bundle.appPath, bundle.dmgDir);

  log("done.");
}

main().catch((err) => {
  fail(err?.stack || String(err));
});
