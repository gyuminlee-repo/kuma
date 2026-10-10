// @vitest-environment node
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Reuse the YAML parser required by our existing, lockfile-pinned schema tooling.
// Resolve from its package instead of depending on pnpm's transitive hoisting.
const require = createRequire(import.meta.url);
const schemaRequire = createRequire(require.resolve("json-schema-to-typescript"));
const yaml = schemaRequire("js-yaml") as { load(text: string): unknown };
const command = "python -m pip install --disable-pip-version-check --only-binary=:all: psutil==7.2.2";
const block = `        run: |\n          ${command}`;

for (const file of ["merizo-platform-smoke.yml", "merizo-windows-smoke.yml"]) {
  describe(file, () => {
    const source = readFileSync(resolve(".github/workflows", file), "utf8");
    it("parses the whole workflow and preserves the exact dependency command", () => {
      const document = yaml.load(source) as { jobs: Record<string, { steps: Array<{ name?: string; run?: string }> }> };
      const steps = Object.values(document.jobs).flatMap((job) => job.steps);
      const matching = steps.filter((step) => step.name === "Install pinned host process identity dependency (probe only)");
      expect(matching).toHaveLength(1);
      expect(matching[0].run?.trim()).toBe(command);
    });
    it("rejects the original colon-space plain-scalar regression", () => {
      expect(source.split(block)).toHaveLength(2);
      const original = source.replace(block, `        run: ${command}`);
      expect(() => yaml.load(original)).toThrow();
    });
  });
}
