import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const root = fileURLToPath(new URL("../../", import.meta.url));
const config = JSON.parse(readFileSync(join(root, ".cross-layer-sync.json"), "utf8"));
const checks = config.checks.filter(({ id }) =>
  ["tauri-resources", "tauri-resource-paths"].includes(id));

function run(resources, genericOnly = false) {
  const dir = mkdtempSync(join(tmpdir(), "kuma-scr03-"));
  try {
    mkdirSync(join(dir, "scripts"));
    mkdirSync(join(dir, "src-tauri"));
    for (const name of ["sync-check.mjs", "sync-check-resources.mjs"]) {
      const source = join(root, "scripts", name);
      if (existsSync(source)) copyFileSync(source, join(dir, "scripts", name));
    }
    writeFileSync(join(dir, ".cross-layer-sync.json"), JSON.stringify({
      checks: genericOnly ? checks.filter(({ id }) => id === "tauri-resources") : checks,
    }));
    writeFileSync(join(dir, "src-tauri", "tauri.conf.json"), JSON.stringify({ bundle: { resources } }));
    writeFileSync(join(dir, "src-tauri", "asset.txt"), "resource\n");
    const result = spawnSync(process.execPath, ["scripts/sync-check.mjs"], {
      cwd: dir, encoding: "utf8", timeout: 10000,
    });
    assert.ifError(result.error);
    return { status: result.status, output: result.stdout + result.stderr };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

for (const [name, resources] of [
  ["number", [123]],
  ["null", [null]],
  ["object", [{}]],
  ["boolean", [false]],
  ["empty source", [""]],
  ["blank source", ["   "]],
  ["mixed sources", ["asset.txt", null]],
  ["empty map source", { "": "target.txt" }],
]) {
  test(`generic files_exist without local extension rejects ${name}`, () => {
    const result = run(resources, true);
    assert.equal(result.status, 1, result.output);
    assert.match(result.output, /FAIL \[tauri-resources\] invalid source path:/);
    assert.doesNotMatch(result.output, /tauri-resource-paths/);
    assert.doesNotMatch(result.output, /PASS \[tauri-resources\]/);
  });
}

test("generic files_exist preserves source paths and ignores destination existence", () => {
  const result = run({ "asset.txt": "absent-destination.txt" }, true);
  assert.equal(result.status, 0, result.output);
  assert.match(result.output, /PASS \[tauri-resources\] 1 entries present/);
});

for (const [name, resources] of [
  ["numeric entry", [123]],
  ["null entry", [null]],
  ["object entry", [{}]],
  ["boolean entry", [false]],
  ["empty path", [""]],
  ["blank path", ["   "]],
  ["mixed valid and invalid entries", ["asset.txt", null]],
  ["empty object-map source", { "": "target.txt" }],
]) {
  test(`files_exist CLI rejects ${name}`, () => {
    const result = run(resources);
    assert.equal(result.status, 1, result.output);
    assert.match(result.output, /FAIL \[tauri-resource-paths\]/);
    assert.match(result.output, /non-empty path string/);
  });
}

for (const [name, resources] of [
  ["valid array", ["asset.txt"]],
  ["valid object map", { "asset.txt": "different-target.txt" }],
]) {
  test(`files_exist CLI accepts ${name}`, () => {
    const result = run(resources);
    assert.equal(result.status, 0, result.output);
    assert.match(result.output, /PASS \[tauri-resources\] 1 entries present/);
  });
}

for (const [name, resources] of [
  ["missing file", ["missing.txt"]],
  ["glob", ["*.txt"]],
  ["empty array", []],
  ["empty map", {}],
  ["null manifest value", null],
  ["scalar manifest value", 123],
]) {
  test(`existing files_exist gate still rejects ${name}`, () => {
    const result = run(resources);
    assert.equal(result.status, 1, result.output);
    assert.match(result.output, /FAIL \[tauri-resources\]/);
  });
}
