/**
 * Fixture repo helper for the release scripts under scripts/.
 *
 * scripts/gen-whatsnew.mjs and scripts/i18n-parity.mjs both resolve their ROOT
 * from their own file location (`<script>/..`) and then read and WRITE real
 * files: CHANGELOG.md, package.json, src/locales/*.json. Exercising them in
 * place would edit the repository from a test run, and stubbing their internals
 * would test something other than what the release gate runs.
 *
 * So each case builds a throwaway repo in the OS temp directory, copies the
 * script under test into `<tmp>/scripts/`, and runs it as a child process from
 * there. The copy is what makes the temp directory the script's ROOT, with no
 * argument or environment hook added to the script for the test's benefit. The
 * exit code is part of the contract those scripts publish (sync-version.sh
 * distinguishes 2 from 1), so it is read from the child rather than inferred.
 */
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Anchored to this file rather than to cwd, so the source scripts are found by
// the same path whichever directory the run was started from.
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

export interface ScriptRun {
  /** Child exit code; -1 if the child was killed without one. */
  status: number;
  stdout: string;
  stderr: string;
  /** stdout + stderr, for asserting on a message without caring which stream. */
  output: string;
}

export interface FixtureRepo {
  /** Absolute path of the throwaway repo root. */
  dir: string;
  write(relPath: string, contents: string): void;
  writeJson(relPath: string, value: unknown): void;
  readJson<T>(relPath: string): T;
  /** Copy `scripts/<name>` from the real repo into the fixture and run it. */
  run(name: string, args?: string[]): ScriptRun;
  cleanup(): void;
}

export function createFixtureRepo(): FixtureRepo {
  const dir = mkdtempSync(join(tmpdir(), "kuma-script-fixture-"));

  const write = (relPath: string, contents: string) => {
    const full = join(dir, relPath);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, contents, "utf-8");
  };

  return {
    dir,
    write,
    writeJson: (relPath, value) => write(relPath, `${JSON.stringify(value, null, 2)}\n`),
    readJson: <T>(relPath: string) => JSON.parse(readFileSync(join(dir, relPath), "utf-8")) as T,
    run(name, args = []) {
      const source = join(REPO_ROOT, "scripts", name);
      if (!existsSync(source)) {
        throw new Error(`script under test not found: ${source} (repo root ${REPO_ROOT})`);
      }
      const target = join(dir, "scripts", name);
      mkdirSync(dirname(target), { recursive: true });
      copyFileSync(source, target);
      const result = spawnSync(process.execPath, [target, ...args], {
        cwd: dir,
        encoding: "utf-8",
      });
      const stdout = result.stdout ?? "";
      const stderr = result.stderr ?? "";
      return { status: result.status ?? -1, stdout, stderr, output: stdout + stderr };
    },
    cleanup() {
      rmSync(dir, { recursive: true, force: true });
    },
  };
}
