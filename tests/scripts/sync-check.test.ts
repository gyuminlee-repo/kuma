/**
 * scripts/sync-check.mjs: the runner behind .cross-layer-sync.json.
 *
 * Every case here is a check that used to report PASS while measuring nothing:
 * an extractor whose pattern matched no line, a manifest key that had been
 * removed, a TS anchor that had been renamed, a key shape the pattern could not
 * see, and the symbol scan that ran on blocking groups only. A checker that
 * reports success without looking at anything is worse than no checker, because
 * the 70 contracts in .cross-layer-sync.json are trusted on its word.
 *
 * The runner reads .cross-layer-sync.json from its working directory, so each
 * case builds a throwaway repo (see ./script-fixture) and runs the real script
 * there, never against this repository's config.
 *
 * Those cases are all child processes and never touch a DOM, so this file opts
 * out of the project-wide jsdom environment and skips booting it.
 *
 * @vitest-environment node
 */
import { afterEach, describe, expect, it } from "vitest";
import { createFixtureRepo, type FixtureRepo, type ScriptRun } from "./script-fixture";

let repo: FixtureRepo | undefined;

afterEach(() => {
  repo?.cleanup();
  repo = undefined;
});

/** Run the checker over a config and a set of project files. */
function check(config: unknown, files: Record<string, string> = {}): ScriptRun {
  const created = createFixtureRepo();
  repo = created;
  for (const [rel, body] of Object.entries(files)) created.write(rel, body);
  created.writeJson(".cross-layer-sync.json", config);
  return created.run("sync-check.mjs");
}

describe("version_sync", () => {
  it("fails when every extractor matches nothing", () => {
    // new Set([null, null]).size === 1, so this printed "PASS aligned: null".
    const run = check(
      {
        checks: [
          {
            id: "version-sync",
            type: "version_sync",
            files: [
              { path: "a.toml", extract: 'regex:^version\\s*=\\s*"([^"]+)"' },
              { path: "b.toml", extract: 'regex:^version\\s*=\\s*"([^"]+)"' },
            ],
          },
        ],
      },
      { "a.toml": "release = '1.0.0'\n", "b.toml": "release = '1.0.0'\n" },
    );

    expect(run.status).toBe(1);
    expect(run.output).toContain("FAIL [version-sync]");
    expect(run.output).not.toContain("aligned: null");
    // The reader has to learn which extractor went blind and in which file.
    expect(run.output).toContain("a.toml");
    expect(run.output).toContain("b.toml");
  });

  it("fails when one JSON key is absent", () => {
    const run = check(
      {
        checks: [
          {
            id: "version-sync",
            type: "version_sync",
            files: [
              { path: "pkg.json", extract: "json:version" },
              { path: "other.json", extract: "json:version" },
            ],
          },
        ],
      },
      { "pkg.json": '{"version":"1.0.0"}', "other.json": '{"name":"x"}' },
    );

    expect(run.status).toBe(1);
    expect(run.output).toContain("FAIL [version-sync]");
    expect(run.output).toContain("other.json");
  });

  it("still passes when the extractors resolve and agree", () => {
    const run = check(
      {
        checks: [
          {
            id: "version-sync",
            type: "version_sync",
            files: [
              { path: "pkg.json", extract: "json:version" },
              { path: "a.toml", extract: 'regex:^version\\s*=\\s*"([^"]+)"' },
            ],
          },
        ],
      },
      { "pkg.json": '{"version":"1.0.0"}', "a.toml": 'version = "1.0.0"\n' },
    );

    expect(run.status).toBe(0);
    expect(run.output).toContain("PASS [version-sync] aligned: 1.0.0");
  });
});

describe("files_exist", () => {
  const config = {
    checks: [
      {
        id: "tauri-resources",
        type: "files_exist",
        manifest: "conf.json",
        extract: "json:bundle.resources",
      },
    ],
  };

  it("fails when the manifest key is gone", () => {
    // This is the check that guards every bundled sample shipping, and an
    // absent key made it report "0 entries present" and pass.
    const run = check(config, { "conf.json": '{"bundle":{}}' });

    expect(run.status).toBe(1);
    expect(run.output).toContain("FAIL [tauri-resources]");
    expect(run.output).not.toContain("0 entries present");
    expect(run.output).toContain("conf.json");
  });

  it("fails on an empty list rather than reporting nothing missing", () => {
    const run = check(config, { "conf.json": '{"bundle":{"resources":[]}}' });

    expect(run.status).toBe(1);
    expect(run.output).toContain("FAIL [tauri-resources]");
    expect(run.output).toContain("empty");
  });

  it("passes when the listed paths are on disk", () => {
    const run = check(config, {
      "conf.json": '{"bundle":{"resources":["res/a.txt"]}}',
      "res/a.txt": "a\n",
    });

    expect(run.status).toBe(0);
    expect(run.output).toContain("PASS [tauri-resources] 1 entries present");
  });
});

describe("registry_match", () => {
  const PY = ['_METHODS = {', '    "ping": handle_ping,', '    "mame.run": handle_run,', '}', ''].join("\n");
  const TS = [
    "export interface RpcMethodMap {",
    "  ping: {",
    "    params: void;",
    "  };",
    '  "mame.run": {',
    "    params: void;",
    "  };",
    "}",
    "",
  ].join("\n");
  const config = {
    checks: [
      {
        id: "kuro-dispatcher",
        type: "registry_match",
        left: { path: "dispatcher.py", extract: "python_dict_keys:_METHODS" },
        right: { path: "models.ts", extract: "ts_interface_keys:RpcMethodMap" },
      },
    ],
  };

  it("sees quoted dotted TS keys", () => {
    const run = check(config, { "dispatcher.py": PY, "models.ts": TS });

    expect(run.status).toBe(0);
    // Two, not one. A dotted RPC method must be quoted to be a TS key, so the
    // unquoted-only pattern was blind to exactly the names MAME uses.
    expect(run.output).toContain("PASS [kuro-dispatcher] 2 entries aligned");
  });

  it("reports a dotted method that only one side declares", () => {
    const run = check(config, {
      "dispatcher.py": PY,
      "models.ts": TS.replace('  "mame.run": {\n    params: void;\n  };\n', ""),
    });

    expect(run.status).toBe(1);
    expect(run.output).toContain("mame.run");
  });

  it("fails when the TS anchor was renamed away", () => {
    const run = check(config, {
      "dispatcher.py": PY,
      "models.ts": TS.replace("export interface RpcMethodMap {", "export type RpcMethodMap = {"),
    });

    expect(run.status).toBe(1);
    expect(run.output).toContain("FAIL [kuro-dispatcher]");
    expect(run.output).not.toContain("entries aligned");
    expect(run.output).toContain("models.ts");
  });

  it("fails when the Python anchor was renamed away", () => {
    const run = check(config, {
      "dispatcher.py": PY.replace("_METHODS = {", "_HANDLERS = {"),
      "models.ts": TS,
    });

    expect(run.status).toBe(1);
    expect(run.output).toContain("FAIL [kuro-dispatcher]");
    expect(run.output).toContain("dispatcher.py");
  });

  it("fails when both sides yield no keys at all", () => {
    const run = check(config, {
      "dispatcher.py": "_METHODS = {\n}\n",
      "models.ts": "export interface RpcMethodMap {\n}\n",
    });

    expect(run.status).toBe(1);
    expect(run.output).toContain("FAIL [kuro-dispatcher]");
    expect(run.output).not.toContain("0 entries aligned");
  });
});

describe("groups[] symbols", () => {
  const files = { "a.ts": "export const kept = 1;\n" };

  it("fails a blocking group that is missing a symbol", () => {
    const run = check(
      { groups: [{ id: "g", files: ["a.ts"], symbols: ["gone"], severity: "blocking" }] },
      files,
    );

    expect(run.status).toBe(1);
    expect(run.output).toContain("FAIL [groups-validity]");
    expect(run.output).toContain("gone");
  });

  it("warns, rather than skipping, a warning group that is missing a symbol", () => {
    // severity picks how a miss is reported, not whether it is looked for. The
    // symbol scan used to run on blocking groups only, so the symbols of every
    // warning group went unread and could disappear without even a WARN.
    const run = check(
      { groups: [{ id: "g", files: ["a.ts"], symbols: ["gone"], severity: "warning" }] },
      files,
    );

    expect(run.status).toBe(0);
    expect(run.output).toContain("WARN [groups-validity]");
    expect(run.output).toContain("gone");
  });

  it("passes a warning group whose symbols all resolve", () => {
    const run = check(
      { groups: [{ id: "g", files: ["a.ts"], symbols: ["kept"], severity: "warning" }] },
      files,
    );

    expect(run.status).toBe(0);
    expect(run.output).toContain("PASS [groups-validity] g OK");
    expect(run.output).not.toContain("WARN");
  });
});
