/**
 * Every name the app imports from an aliased @tauri-apps module must be
 * exported by its MOCK_MODE stub, or `MOCK_MODE` builds fail with
 * `"<name>" is not exported by "scripts/stubs/<file>.ts"` before any screen
 * renders (copyFile, imported by analysisSlice.ts, went missing this way).
 * The aliases are read from vite.config.ts so a new alias is covered too.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..");

function aliases(): Map<string, string> {
  const config = readFileSync(join(ROOT, "vite.config.ts"), "utf-8");
  const found = new Map<string, string>();
  const pattern = /"(@tauri-apps\/[^"]+)":\s*resolve\(\s*__dirname,\s*"([^"]+)"/g;
  for (const match of config.matchAll(pattern)) found.set(match[1], match[2]);
  return found;
}

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "__tests__" ? [] : sources(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

function namesOf(list: string): string[] {
  return list
    .split(",")
    .map((name) => name.trim())
    .filter((name) => name && !name.startsWith("type "))
    .map((name) => name.split(/\s+as\s+|:/)[0].trim());
}

function used(): Map<string, Map<string, string>> {
  const byModule = new Map<string, Map<string, string>>();
  const add = (module: string, names: string[], file: string) => {
    const entry = byModule.get(module) ?? new Map<string, string>();
    for (const name of names) entry.set(name, file);
    byModule.set(module, entry);
  };
  for (const file of sources(join(ROOT, "src"))) {
    const text = readFileSync(file, "utf-8");
    const where = relative(ROOT, file);
    for (const m of text.matchAll(/import\s+(type\s+)?\{([^}]*)\}\s+from\s+["'](@tauri-apps\/[^"']+)["']/g)) {
      if (!m[1]) add(m[3], namesOf(m[2]), where);
    }
    for (const m of text.matchAll(/const\s+\{([^}]*)\}\s*=\s*await\s+import\(\s*["'](@tauri-apps\/[^"']+)["']\s*\)/g)) {
      add(m[2], namesOf(m[1]), where);
    }
  }
  return byModule;
}

function exportsOf(stub: string): Set<string> {
  const text = readFileSync(join(ROOT, stub), "utf-8");
  const names = new Set<string>();
  for (const m of text.matchAll(/export\s+(?:async\s+)?(?:function|const|let|class|type|interface|enum)\s+(\w+)/g)) names.add(m[1]);
  for (const m of text.matchAll(/export\s*\{([^}]*)\}/g)) {
    for (const name of m[1].split(",")) if (name.trim()) names.add(name.split(/\s+as\s+/).pop()!.trim());
  }
  return names;
}

describe("MOCK_MODE tauri stubs", () => {
  it("reads the aliases it checks", () => {
    expect(aliases().get("@tauri-apps/plugin-fs")).toBe("scripts/stubs/fs.ts");
  });

  it("export every name the app imports from an aliased module", () => {
    const stubs = aliases();
    const missing: string[] = [];
    for (const [module, names] of used()) {
      const stub = stubs.get(module);
      if (!stub) continue;
      const exported = exportsOf(stub);
      for (const [name, file] of names) {
        if (!exported.has(name)) missing.push(`${module}.${name} (${file}) is not exported by ${stub}`);
      }
    }
    expect(missing).toEqual([]);
  });
});
