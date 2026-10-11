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
    it("scopes the existing read-only metadata token to preparation only", () => {
      const document = yaml.load(source) as {
        permissions: Record<string, string>;
        jobs: Record<string, { steps: Array<{ name?: string; env?: Record<string, string> }> }>;
      };
      expect(document.permissions).toEqual({ contents: "read" });
      const steps = Object.values(document.jobs).flatMap((job) => job.steps);
      const scoped = steps.filter((step) => step.env?.KUMA_GITHUB_METADATA_TOKEN);
      expect(scoped).toHaveLength(1);
      expect(scoped[0].name).toBe("Prepare candidate archive input evidence (no distribution)");
      expect(scoped[0].env?.KUMA_GITHUB_METADATA_TOKEN).toBe("${{ github.token }}");
      expect(source.split("${{ github.token }}")).toHaveLength(2);
    });
    it("retains only named JSON evidence and watches the real service inputs", () => {
      const document = yaml.load(source) as {
        on: { pull_request: { paths: string[] } };
        jobs: Record<string, { steps: Array<{ name?: string; with?: { path?: string } }> }>;
      };
      const steps = Object.values(document.jobs).flatMap((job) => job.steps);
      const artifacts = steps.filter((step) => step.name === "Preserve small result only (never models or runtime)");
      expect(artifacts).toHaveLength(1);
      const paths = artifacts[0].with?.path?.trim().split(/\r?\n/).map((path) => path.trim()) ?? [];
      expect(paths).toHaveLength(12);
      expect(new Set(paths).size).toBe(12);
      expect(paths).toContain("merizo-smoke-results/archive-public-1ubq-execution.json");
      expect(paths).toContain("merizo-smoke-results/archive-synthetic-af3-execution.json");
      expect(paths.every((path) => path.startsWith("merizo-smoke-results/") && path.endsWith(".json") && !path.includes("*"))).toBe(true);
      for (const path of ["kuma_core/kuro/domain_jobs.py", "kuma_core/kuro/domain_af3.py", "kuma_core/kuro/prediction_bundle.py"]) {
        expect(document.on.pull_request.paths).toContain(path);
      }
    });
    it("rejects the original colon-space plain-scalar regression", () => {
      expect(source.split(block)).toHaveLength(2);
      const original = source.replace(block, `        run: ${command}`);
      expect(() => yaml.load(original)).toThrow();
    });
    it("limits the OS DLL omission experiment to the Windows archive controller", () => {
      const document = yaml.load(source) as {
        jobs: Record<string, { steps: Array<{ name?: string; run?: string }> }>;
      };
      const steps = Object.values(document.jobs).flatMap((job) => job.steps);
      const optedIn = steps.filter((step) => step.run?.includes("--windows-os-dll-policy"));
      if (file === "merizo-windows-smoke.yml") {
        expect(optedIn).toHaveLength(1);
        expect(optedIn[0].name).toBe("Run direct archive build controller and installed CPU entry");
        expect(optedIn[0].run).toContain("-m scripts.merizo_runtime_archive.build");
      } else {
        expect(optedIn).toHaveLength(0);
      }
    });
  });
}

it("gates heavy Windows model work on the exact small venv probe", () => {
  const source = readFileSync(resolve(".github/workflows/merizo-windows-smoke.yml"), "utf8");
  const document = yaml.load(source) as { jobs: Record<string, {
    needs?: string; "timeout-minutes": number;
    steps: Array<{ name?: string; uses?: string; if?: string; run?: string; with?: Record<string, unknown> }>;
  }> };
  const probe = document.jobs["windows-venv-domain-contract"];
  expect(probe["timeout-minutes"]).toBe(5);
  expect(document.jobs["native-windows-cpu"].needs).toBe("windows-venv-domain-contract");
  expect(probe.steps.find((step) => step.uses === "actions/setup-python@v6")?.with?.["python-version"]).toBe("3.11.9");
  const commands = probe.steps.map((step) => step.run ?? "").join("\n");
  expect(commands).toContain("psutil==7.2.2");
  expect(commands).toContain("windows_venv_probe.py --report");
  expect(commands).not.toMatch(/Merizo|torch|weights|requirements\.txt/);
  const artifact = probe.steps.find((step) => step.uses === "actions/upload-artifact@v4");
  expect(artifact?.if).toBe("always()");
  expect(artifact?.with?.path).toBe("merizo-smoke-results/windows-venv-domain-contract.json");
  const cleanup = probe.steps.find((step) => step.name === "Remove only owned probe venv");
  expect(cleanup?.if).toBe("always()");
  expect(cleanup?.run).toContain("Probe ownership mismatch");
  expect(cleanup?.run).toContain("cleanup_verified -is [bool]");
  expect(cleanup?.run).toContain("Probe cleanup not verified; preserve venv");
  expect(cleanup?.run).toContain("Length -gt 16384");
  expect(cleanup?.run).toContain("Invalid probe root; preserve directory");
  expect(cleanup?.run?.indexOf("cleanup_verified")).toBeLessThan(cleanup?.run?.indexOf("Remove-Item") ?? -1);
  expect(cleanup?.run).toContain("-LiteralPath $venv");
});
