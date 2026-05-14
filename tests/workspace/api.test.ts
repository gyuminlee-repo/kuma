import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  openWorkspace,
  registerArtifacts,
  listArtifacts,
  getLatestArtifact,
  clearWorkspace,
  _resetWorkspaceForTest,
} from "@/lib/workspace/api";
import { _resetListenersForTest, subscribe } from "@/lib/workspace/events";
import { readManifest, createEmptyManifest, writeManifest } from "@/lib/workspace/manifest";

describe("workspace api", () => {
  let dir: string;

  beforeEach(async () => {
    dir = mkdtempSync(join(tmpdir(), "ws-api-"));
    _resetWorkspaceForTest();
    _resetListenersForTest();
    await openWorkspace(dir);
  });

  afterEach(() => {
    _resetWorkspaceForTest();
    _resetListenersForTest();
  });

  it("creates manifest on openWorkspace", async () => {
    const m = await readManifest(dir);
    expect(m).not.toBeNull();
    expect(m!.schemaVersion).toBe(1);
    expect(m!.artifacts).toHaveLength(0);
  });

  it("registers and lists artifacts", async () => {
    const file = join(dir, "out.csv");
    writeFileSync(file, "a,b\n");
    await registerArtifacts([
      { app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: file },
    ]);
    const list = await listArtifacts({ type: "evolvepro_csv" });
    expect(list).toHaveLength(1);
    expect(list[0].path).toBe(file);
    expect(list[0].stale).toBe(false);
  });

  it("upserts same (app,step,type) keeping only latest", async () => {
    const f1 = join(dir, "a.csv");
    const f2 = join(dir, "b.csv");
    writeFileSync(f1, "1");
    writeFileSync(f2, "2");
    await registerArtifacts([
      { app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f1 },
    ]);
    await registerArtifacts([
      { app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f2 },
    ]);
    const list = await listArtifacts();
    expect(list).toHaveLength(1);
    expect(list[0].path).toBe(f2);
  });

  it("keeps independent (app,step,type) entries", async () => {
    const f1 = join(dir, "kuro.xlsx");
    const f2 = join(dir, "mame.fa");
    writeFileSync(f1, "x");
    writeFileSync(f2, "y");
    await registerArtifacts([
      { app: "kuro", step: "design", type: "sdm_primer_xlsx", absolutePath: f1 },
      { app: "mame", step: "analysis", type: "mame_consensus_fasta", absolutePath: f2 },
    ]);
    const list = await listArtifacts();
    expect(list).toHaveLength(2);
  });

  it("getLatestArtifact returns null when none", async () => {
    expect(await getLatestArtifact("evolvepro_csv")).toBeNull();
  });

  it("marks stale when mtime changed since register", async () => {
    const f = join(dir, "c.csv");
    writeFileSync(f, "x");
    await registerArtifacts([
      { app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f },
    ]);
    await new Promise((r) => setTimeout(r, 30));
    writeFileSync(f, "y-modified");
    const latest = await getLatestArtifact("evolvepro_csv");
    expect(latest?.stale).toBe(true);
  });

  it("removes artifact when file missing", async () => {
    const f = join(dir, "d.csv");
    writeFileSync(f, "x");
    await registerArtifacts([
      { app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f },
    ]);
    unlinkSync(f);
    expect(await listArtifacts()).toHaveLength(0);
  });

  it("clearWorkspace removes only specified app artifacts", async () => {
    const f1 = join(dir, "kuro.xlsx");
    const f2 = join(dir, "mame.fa");
    writeFileSync(f1, "x");
    writeFileSync(f2, "y");
    await registerArtifacts([
      { app: "kuro", step: "design", type: "sdm_primer_xlsx", absolutePath: f1 },
      { app: "mame", step: "analysis", type: "mame_consensus_fasta", absolutePath: f2 },
    ]);
    await clearWorkspace("kuro");
    const remaining = await listArtifacts();
    expect(remaining).toHaveLength(1);
    expect(remaining[0].app).toBe("mame");
  });

  it("emits workspace:updated on register and clear", async () => {
    let count = 0;
    const off = subscribe("workspace:updated", () => count++);
    const f = join(dir, "e.csv");
    writeFileSync(f, "x");
    await registerArtifacts([
      { app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f },
    ]);
    await clearWorkspace("kuro");
    off();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  it("rejects relative workspace paths", async () => {
    _resetWorkspaceForTest();
    await expect(openWorkspace("relative/path")).rejects.toThrow(/absolute/);
  });

  it("throws when registering without open workspace", async () => {
    _resetWorkspaceForTest();
    await expect(
      registerArtifacts([
        { app: "kuro", step: "x", type: "evolvepro_csv", absolutePath: "/tmp/nope" },
      ]),
    ).rejects.toThrow(/not opened/);
  });

  it("recovers from corrupt manifest by treating as missing", async () => {
    const m = createEmptyManifest();
    await writeManifest(dir, m);
    // Now corrupt it
    writeFileSync(join(dir, ".kuma-workspace.json"), "{ not json");
    const f = join(dir, "f.csv");
    writeFileSync(f, "x");
    // registerArtifacts should not throw; corrupt manifest is treated as fresh
    await registerArtifacts([
      { app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f },
    ]);
    const list = await listArtifacts();
    expect(list).toHaveLength(1);
  });
});
