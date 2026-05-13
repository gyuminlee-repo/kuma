import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const HOOK = resolve("scripts/kuma-deps-notify.mjs");

function runHook(stdin, cwd = process.cwd()) {
  return spawnSync("node", [HOOK], {
    input: JSON.stringify(stdin),
    encoding: "utf8",
    cwd,
  });
}

test("non-edit tool: silent exit 0", () => {
  const r = runHook({ tool_name: "Read", tool_input: { file_path: "src/types/models.ts" } });
  assert.equal(r.status, 0);
  assert.equal(r.stdout, "");
});

test("Edit on unrelated file: silent exit 0", () => {
  const dir = mkdtempSync(join(tmpdir(), "kuma-deps-"));
  writeFileSync(join(dir, ".cross-layer-sync.json"), JSON.stringify({
    checks: [], genModels: [], groups: []
  }));
  const r = runHook({ tool_name: "Edit", tool_input: { file_path: "README.md" } }, dir);
  rmSync(dir, { recursive: true, force: true });
  assert.equal(r.status, 0);
  assert.equal(r.stdout, "");
});

test("Edit on matched file: stdout shows group info", () => {
  const dir = mkdtempSync(join(tmpdir(), "kuma-deps-"));
  writeFileSync(join(dir, ".cross-layer-sync.json"), JSON.stringify({
    checks: [], genModels: [],
    groups: [{
      id: "test-group",
      files: ["src/types/models.ts", "python-core/models.py"],
      symbols: ["Foo"],
      note: "test note",
      severity: "blocking"
    }]
  }));
  const r = runHook({ tool_name: "Edit", tool_input: { file_path: "src/types/models.ts" } }, dir);
  rmSync(dir, { recursive: true, force: true });
  assert.equal(r.status, 0);
  assert.match(r.stdout, /\[kuma-deps\]/);
  assert.match(r.stdout, /test-group/);
  assert.match(r.stdout, /test note/);
});

test("glob pattern: fixtures/*.csv matches new csv", () => {
  const dir = mkdtempSync(join(tmpdir(), "kuma-deps-"));
  writeFileSync(join(dir, ".cross-layer-sync.json"), JSON.stringify({
    checks: [], genModels: [],
    groups: [{ id: "csv-group", files: ["fixtures/*.csv", "kuma_core/x.py"], note: "n", severity: "warning" }]
  }));
  const r = runHook({ tool_name: "Write", tool_input: { file_path: "fixtures/sample.csv" } }, dir);
  rmSync(dir, { recursive: true, force: true });
  assert.equal(r.status, 0);
  assert.match(r.stdout, /csv-group/);
});

test("corrupt config: stderr warning, exit 0", () => {
  const dir = mkdtempSync(join(tmpdir(), "kuma-deps-"));
  writeFileSync(join(dir, ".cross-layer-sync.json"), "{ this is not json");
  const r = runHook({ tool_name: "Edit", tool_input: { file_path: "x.ts" } }, dir);
  rmSync(dir, { recursive: true, force: true });
  assert.equal(r.status, 0);
  assert.match(r.stderr, /config parse error/);
});

test("MultiEdit: extracts each edit file_path", () => {
  const dir = mkdtempSync(join(tmpdir(), "kuma-deps-"));
  writeFileSync(join(dir, ".cross-layer-sync.json"), JSON.stringify({
    checks: [], genModels: [],
    groups: [{ id: "g1", files: ["a.ts", "b.ts"], note: "n", severity: "blocking" }]
  }));
  const r = runHook({
    tool_name: "MultiEdit",
    tool_input: { edits: [{ file_path: "a.ts" }, { file_path: "z.ts" }] }
  }, dir);
  rmSync(dir, { recursive: true, force: true });
  assert.equal(r.status, 0);
  assert.match(r.stdout, /g1/);
});
