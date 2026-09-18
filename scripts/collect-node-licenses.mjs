#!/usr/bin/env node
/** Collect installed production packages and their actual legal texts.
 * Input: pnpm licenses list --json --prod
 * Usage: node scripts/collect-node-licenses.mjs input.json NOTICE-node.md
 * Also writes NOTICE-node.json. No license is inferred from an SPDX name.
 */
import { readFileSync, writeFileSync, readdirSync, realpathSync } from "node:fs";
import { resolve, relative, isAbsolute, dirname, basename } from "node:path";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const LEGAL = /^(licen[cs]e|copying|notice|copyright)([._-].*)?$/i;
const legalDir = /^(licen[cs]es|legal)$/i;
const sha256 = (data) => createHash("sha256").update(data).digest("hex");
const compare = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

function readLegalFiles(root) {
  const found = [];
  function walk(dir, inLegal = false) {
    for (const ent of readdirSync(dir, { withFileTypes: true }).sort((a, b) => compare(a.name, b.name))) {
      if (["node_modules", ".git"].includes(ent.name)) continue;
      const path = resolve(dir, ent.name);
      if (ent.isDirectory()) {
        walk(path, inLegal || legalDir.test(ent.name));
      } else if (LEGAL.test(ent.name) || inLegal) {
        const rel = relative(root, realpathSync(path));
        if (rel === ".." || rel.startsWith("../") || rel.startsWith("..\\") || isAbsolute(rel)) {
          throw new Error(`Legal file escapes package directory: ${path}`);
        }
        const bytes = readFileSync(path);
        const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
        if (!text.trim()) throw new Error(`Empty legal file: ${path}`);
        found.push({ path: relative(root, path).replaceAll("\\", "/"), sha256: sha256(bytes), text });
      }
    }
  }
  walk(root);
  return found;
}

// esbuild publishes its binary as an exact-version optional companion. Some
// platform tarballs omit LICENSE.md; retain the same-version parent package's
// real text, with its source named, rather than substituting a generic MIT text.
function companionLegalFiles(meta, data, baseDir) {
  if (!meta.name.startsWith("@esbuild/")) return [];
  for (const group of Object.values(data)) {
    if (!Array.isArray(group)) continue;
    for (const pkg of group) {
      if (pkg?.name !== "esbuild" || !Array.isArray(pkg.paths)) continue;
      for (const item of pkg.paths) {
        const root = realpathSync(resolve(baseDir, item));
        const parent = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
        if (parent.name !== "esbuild" || parent.version !== meta.version ||
            parent.optionalDependencies?.[meta.name] !== meta.version ||
            parent.license !== "MIT" || meta.license !== "MIT") continue;
        return readLegalFiles(root).map((file) => ({
          ...file, path: `esbuild@${parent.version}/${file.path}`,
          source_package: `esbuild@${parent.version}`,
        }));
      }
    }
  }
  return [];
}

export function collectNodeLicenses(data, baseDir = process.cwd()) {
  if (!data || Array.isArray(data) || typeof data !== "object" || !Object.keys(data).length) {
    throw new Error("Expected a non-empty pnpm license-group object");
  }
  const records = new Map();
  const missing = [];
  for (const [license, packages] of Object.entries(data)) {
    if (!license.trim() || !Array.isArray(packages) || !packages.length) {
      throw new Error(`Invalid or empty license group: ${license}`);
    }
    for (const pkg of packages) {
      if (!pkg || typeof pkg.name !== "string" || !pkg.name.trim() || !Array.isArray(pkg.paths) || !pkg.paths.length) {
        throw new Error("Each pnpm package needs a name and installed paths");
      }
      const versions = Array.isArray(pkg.versions) ? pkg.versions : [pkg.version];
      if (!versions.length || versions.some((v) => typeof v !== "string" || !v)) {
        throw new Error(`Missing version for ${pkg.name}`);
      }
      const seenVersions = new Set();
      for (const item of pkg.paths) {
        if (typeof item !== "string" || !item) throw new Error(`Invalid package path for ${pkg.name}`);
        const root = realpathSync(resolve(baseDir, item));
        const meta = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
        if (meta.name !== pkg.name || !versions.includes(meta.version)) {
          throw new Error(`Package identity mismatch at ${root}`);
        }
        let files = readLegalFiles(root);
        if (!files.length) files = companionLegalFiles(meta, data, baseDir);
        if (!files.length) missing.push(`${meta.name}@${meta.version} (${root})`);
        const record = { name: meta.name, version: meta.version, license, files };
        const key = `${meta.name}@${meta.version}`;
        const previous = records.get(key);
        if (previous && JSON.stringify(previous) !== JSON.stringify(record)) {
          throw new Error(`Conflicting legal evidence for ${key}`);
        }
        records.set(key, record);
        seenVersions.add(meta.version);
      }
      if (versions.some((v) => !seenVersions.has(v))) {
        throw new Error(`Missing installed path for a version of ${pkg.name}`);
      }
    }
  }
  if (missing.length) throw new Error(`No LICENSE text for:\n${missing.join("\n")}`);
  return [...records.values()].sort((a, b) => compare(`${a.name}@${a.version}`, `${b.name}@${b.version}`));
}

export function renderNodeNotice(records) {
  const lines = ["# Node / pnpm dependency licenses", "", "Installed production dependency inventory. Texts below come from those packages.",
    "This is license evidence, not a legal compatibility or commercial-use approval.", ""];
  for (const pkg of records) {
    lines.push(`## ${pkg.name} ${pkg.version}`, `Declared license: ${pkg.license}`, "");
    for (const file of pkg.files) {
      const fence = "`".repeat(Math.max(3, ...[...file.text.matchAll(/`+/g)].map((m) => m[0].length + 1)));
      lines.push(`### ${file.path}`, `SHA256: ${file.sha256}`, "", fence, file.text, fence, "");
    }
  }
  return `${lines.join("\n")}\n`;
}

export function main(args = process.argv.slice(2)) {
  if (args.length !== 2) throw new Error("Usage: collect-node-licenses.mjs input.json NOTICE-node.md");
  const input = resolve(args[0]);
  const output = resolve(args[1]);
  const records = collectNodeLicenses(JSON.parse(readFileSync(input, "utf8")), dirname(input));
  // Validate everything before writing either output. A failure must stop the build.
  const notice = renderNodeNotice(records);
  const inventory = { schema_version: 1, scope: "installed-production-packages", legal_clearance: false, packages: records };
  writeFileSync(output, notice, "utf8");
  writeFileSync(resolve(dirname(output), basename(output, ".md") + ".json"), JSON.stringify(inventory, null, 2) + "\n");
  console.log(`[collect-node-licenses] ${records.length} packages -> ${output}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { main(); } catch (error) {
    console.error(`[collect-node-licenses] ${error.message}`);
    process.exitCode = 1;
  }
}
