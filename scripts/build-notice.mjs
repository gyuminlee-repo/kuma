#!/usr/bin/env node
/** Merge generated legal evidence and the unchanged project license.
 * Run after the three dependency collectors. Missing/empty inputs stop release.
 */
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export function buildNotice(root) {
  const inputs = ["LICENSE", "NOTICE-rust.md", "NOTICE-node.md", "NOTICE-python.md", "NOTICE-bundled.md"];
  const parts = inputs.map((name) => {
    const text = readFileSync(resolve(root, name), "utf8");
    const body = text.split("\n").filter((line) => line.trim() && !/^\s*#/.test(line)).join("\n");
    if (!body.trim() || /placeholder; real content generated/i.test(text)) {
      throw new Error(`Empty or placeholder license evidence: ${name}`);
    }
    return name === "LICENSE" ? `## KUMA project license\n\n${text.trim()}` : text.trim();
  });
  const full = "# NOTICE — Project and Third-Party Software Licenses\n\n" +
    "The project license is reproduced unchanged. Dependency sections contain installed-package legal texts and attribution evidence.\n" +
    "Collection is not approval of license compatibility, source-distribution obligations, asset rights, or commercial deployment.\n" +
    "See docs/en/license-compliance.md (한국어: docs/ko/license-compliance.md) in the source repository for the release review checklist.\n\n" +
    parts.join("\n\n---\n\n") + "\n";
  const output = resolve(root, "NOTICE.md");
  const target = resolve(root, "src-tauri/resources/NOTICE.md");
  // Do not replace the bundled notice unless every input has been validated.
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(output, full, "utf8");
  copyFileSync(output, target);
  return output;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    console.log(`[build-notice] Wrote ${buildNotice(resolve(dirname(fileURLToPath(import.meta.url)), ".."))}`);
  } catch (error) {
    console.error(`[build-notice] ${error.message}`);
    process.exitCode = 1;
  }
}
