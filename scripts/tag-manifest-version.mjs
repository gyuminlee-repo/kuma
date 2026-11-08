// tag-manifest-version.mjs
//
// One rule for the release scripts: a tag's first three components must be
// the version the app manifests carry. The binary embeds the tauri.conf.json
// version, so a tag that names anything else makes the updater advertise a
// version its installer does not contain, and the update is offered again
// after every install. A fourth tag component labels a rebuild of the same
// binary and is not compared.
//
// Manifests are read from the checkout this file lives in, not the cwd.

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const MANIFESTS = ["package.json", "src-tauri/tauri.conf.json"];

/** Returns null when every manifest says `threePart`, else the reason. */
export function tagManifestMismatch(threePart, root = ROOT) {
  const wrong = [];
  for (const rel of MANIFESTS) {
    let version;
    try {
      version = JSON.parse(readFileSync(resolve(root, rel), "utf8")).version;
    } catch (err) {
      return `cannot read ${rel}: ${err.message}`;
    }
    if (version !== threePart) wrong.push(`${rel} is ${JSON.stringify(version)}`);
  }
  if (wrong.length === 0) return null;
  return (
    `tag names ${threePart} but ${wrong.join(", ")}. ` +
    `Tag the commit whose manifests carry this version.`
  );
}
