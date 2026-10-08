#!/usr/bin/env node
// Validate resource path values; the vendored files_exist check owns existence and globs.
import { readFileSync } from "node:fs";

try {
  const manifest = "src-tauri/tauri.conf.json";
  const resources = JSON.parse(readFileSync(manifest, "utf8")).bundle?.resources;
  const paths = Array.isArray(resources)
    ? resources
    : resources !== null && typeof resources === "object"
      ? Object.keys(resources)
      : [];
  if (paths.length === 0) {
    throw new Error(`${manifest}: bundle.resources must contain source paths`);
  }
  for (const [index, value] of paths.entries()) {
    if (typeof value !== "string" || value.trim().length === 0) {
      throw new Error(
        `${manifest}: bundle.resources source[${index}] must be a non-empty path string; got ${JSON.stringify(value)}`,
      );
    }
  }
  console.log(`[resource-paths] OK: ${paths.length} source paths validated`);
} catch (error) {
  console.error(`[resource-paths] FAIL: ${error.message}`);
  process.exitCode = 1;
}
