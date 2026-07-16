#!/usr/bin/env node
// gen-latest-json.mjs
//
// Build the Tauri updater manifest (`latest.json`) from the signed bundle
// artifacts produced by `tauri build` (each updater-capable installer ships a
// sibling `<file>.sig` minisign signature). Runs in the CI `release` job after
// download-artifact, before the GitHub release is created.
//
// The manifest points each platform at its release-download URL and embeds the
// matching `.sig` payload. The Tauri updater plugin fetches this file from
//   https://github.com/<owner>/<repo>/releases/latest/download/latest.json
// verifies the signature against the pubkey in tauri.conf.json, then installs.
//
// Platform keys (Tauri updater target triples):
//   windows-x86_64  -> NSIS   *-setup.exe        (.exe.sig)
//   linux-x86_64    -> AppImage *.AppImage       (.AppImage.sig)
//   darwin-aarch64  -> macOS  *.app.tar.gz       (.app.tar.gz.sig)
//
// .deb has no updater artifact by design; those users fall back to the release
// page (handled in the frontend). We only emit platforms whose .sig exists;
// a missing expected platform is a hard error so a broken manifest never ships.
//
// Usage: node scripts/gen-latest-json.mjs <tag> <artifacts-dir> <out-file>
//   e.g. node scripts/gen-latest-json.mjs v0.13.16 artifacts latest.json

import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const REPO = "gyuminlee-repo/kuma";

function fail(msg) {
  console.error(`[gen-latest-json] ERROR: ${msg}`);
  process.exit(1);
}

const [tagArg, artifactsDir, outFile] = process.argv.slice(2);
if (!tagArg) fail("missing tag argument");
if (!artifactsDir) fail("missing artifacts dir argument");
if (!outFile) fail("missing output file argument");

const tagMatch = tagArg.match(/^v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$/);
if (!tagMatch) fail(`tag '${tagArg}' is not v<A>.<B>.<C>[.<D>]`);
const version = tagArg.replace(/^v/, "");

function walk(dir, acc = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, acc);
    else acc.push(full);
  }
  return acc;
}

const files = walk(artifactsDir);

// Match each platform's updater artifact by the sibling `.sig`. The download
// URL uses the artifact's basename under the release's /download/ path.
const platformRules = [
  { key: "windows-x86_64", sigSuffix: "-setup.exe.sig" },
  { key: "linux-x86_64", sigSuffix: ".AppImage.sig" },
  { key: "darwin-aarch64", sigSuffix: ".app.tar.gz.sig" },
];

const platforms = {};
for (const { key, sigSuffix } of platformRules) {
  const sigPath = files.find((f) => f.endsWith(sigSuffix));
  if (!sigPath) {
    fail(
      `no signed updater artifact found for '${key}' ` +
        `(expected a *${sigSuffix} file under ${artifactsDir}). ` +
        `Did 'tauri build' run with TAURI_SIGNING_PRIVATE_KEY set?`,
    );
  }
  const signature = readFileSync(sigPath, "utf8").trim();
  if (!signature) fail(`signature file is empty: ${sigPath}`);

  // The uploaded asset name is the .sig file's basename minus ".sig".
  const assetName = sigPath.slice(0, -".sig".length).split(/[\\/]/).pop();
  platforms[key] = {
    signature,
    url: `https://github.com/${REPO}/releases/download/${tagArg}/${encodeURIComponent(assetName)}`,
  };
}

const manifest = {
  version,
  notes: `See the release notes for v${version}.`,
  pub_date: new Date().toISOString(),
  platforms,
};

writeFileSync(outFile, JSON.stringify(manifest, null, 2) + "\n");
console.log(
  `[gen-latest-json] wrote ${outFile} for v${version} with platforms: ` +
    Object.keys(platforms).join(", "),
);
