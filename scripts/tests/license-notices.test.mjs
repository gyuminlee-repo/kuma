import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { collectNodeLicenses, renderNodeNotice, main } from "../collect-node-licenses.mjs";
import { buildNotice } from "../build-notice.mjs";

function fixture(t, version = "1.0.0") {
  const root = mkdtempSync(join(tmpdir(), "kuma-notice-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const pkg = join(root, "sample");
  mkdirSync(pkg);
  writeFileSync(join(pkg, "package.json"), JSON.stringify({ name: "sample", version }));
  writeFileSync(join(pkg, "LICENSE"), "Copyright Example\nPermission is hereby granted.\n");
  return { root, pkg, data: { MIT: [{ name: "sample", versions: [version], paths: [pkg] }] } };
}

test("collects actual license and NOTICE text and writes matching inventory", (t) => {
  const { root, pkg, data } = fixture(t);
  writeFileSync(join(pkg, "NOTICE.txt"), "Required upstream attribution\n");
  const records = collectNodeLicenses(data);
  assert.equal(records[0].files.length, 2);
  assert.match(renderNodeNotice(records), /Copyright Example/);
  assert.match(renderNodeNotice(records), /Required upstream attribution/);
  assert.match(records[0].files[0].sha256, /^[a-f0-9]{64}$/);
  writeFileSync(join(root, "input.json"), JSON.stringify(data));
  main([join(root, "input.json"), join(root, "NOTICE-node.md")]);
  assert.deepEqual(JSON.parse(readFileSync(join(root, "NOTICE-node.json"))).packages, records);
});

test("rejects empty, malformed and identifier-only evidence", (t) => {
  for (const invalid of [{}, [], null, { MIT: [] }, { MIT: [{}] }]) {
    assert.throws(() => collectNodeLicenses(invalid));
  }
  const { pkg, data } = fixture(t);
  rmSync(join(pkg, "LICENSE"));
  assert.throws(() => collectNodeLicenses(data), /No LICENSE/);
});

test("rejects a package/version mismatch and an unrepresented version", (t) => {
  const { data } = fixture(t);
  data.MIT[0].versions = ["2.0.0"];
  assert.throws(() => collectNodeLicenses(data), /identity mismatch/);
  data.MIT[0].versions = ["1.0.0", "2.0.0"];
  assert.throws(() => collectNodeLicenses(data), /Missing installed path/);
});

test("captures nonstandard names under licenses, excluding dependency folders", (t) => {
  const { pkg, data } = fixture(t);
  mkdirSync(join(pkg, "licenses"));
  writeFileSync(join(pkg, "licenses", "embedded-component.txt"), "Embedded attribution");
  mkdirSync(join(pkg, "node_modules"));
  writeFileSync(join(pkg, "node_modules", "LICENSE"), "Not this package");
  const records = collectNodeLicenses(data);
  assert.equal(records[0].files.length, 2);
  assert.match(renderNodeNotice(records), /Embedded attribution/);
  assert.doesNotMatch(renderNodeNotice(records), /Not this package/);
});

test("deduplicates identical installations without hiding conflicting evidence", (t) => {
  const { root, data } = fixture(t);
  data.MIT.push(data.MIT[0]);
  assert.equal(collectNodeLicenses(data).length, 1);
  const other = join(root, "other");
  mkdirSync(other);
  writeFileSync(join(other, "package.json"), JSON.stringify({ name: "sample", version: "1.0.0" }));
  writeFileSync(join(other, "LICENSE"), "Different grant");
  data.MIT.push({ name: "sample", versions: ["1.0.0"], paths: [other] });
  assert.throws(() => collectNodeLicenses(data), /Conflicting legal evidence/);
});

test("empty legal text fails", (t) => {
  const { pkg, data } = fixture(t);
  writeFileSync(join(pkg, "LICENSE"), "\n");
  assert.throws(() => collectNodeLicenses(data), /Empty legal file/);
});

test("merger preserves project license and rejects incomplete input without replacing output", (t) => {
  const { root } = fixture(t);
  for (const name of ["LICENSE", "NOTICE-rust.md", "NOTICE-node.md", "NOTICE-python.md", "NOTICE-bundled.md"]) {
    writeFileSync(join(root, name), "# Header\nOriginal legal text\n");
  }
  buildNotice(root);
  const target = join(root, "src-tauri/resources/NOTICE.md");
  const original = readFileSync(target, "utf8");
  assert.match(original, /KUMA project license/);
  assert.match(original, /Collection is not approval/);
  writeFileSync(join(root, "NOTICE-node.md"), "# Empty\n");
  assert.throws(() => buildNotice(root), /Empty or placeholder/);
  assert.equal(readFileSync(target, "utf8"), original);
  rmSync(join(root, "NOTICE-node.md"));
  assert.throws(() => buildNotice(root), /ENOENT/);
});
