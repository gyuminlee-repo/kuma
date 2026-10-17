/**
 * registerArtifacts records into the registry it is told to, not into whichever
 * project is active when it runs. An export started in project A finishes
 * after the user opened project B; its files belong to A's manifest.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkspaceManifest } from "./types";

const fsState = vi.hoisted(() => ({ manifests: new Map<string, WorkspaceManifest>() }));

vi.mock("@tauri-apps/api/path", () => ({
  isAbsolute: vi.fn(async (p: string) => p.startsWith("/")),
  resolve: vi.fn(async (dir: string, p: string) => (p.startsWith("/") ? p : `${dir}/${p}`)),
}));
vi.mock("@tauri-apps/plugin-fs", () => ({
  exists: vi.fn(async () => true),
  stat: vi.fn(async () => ({ size: 10, mtime: new Date("2026-10-17T00:00:00Z") })),
}));
vi.mock("./manifest", () => ({
  readManifest: vi.fn(async (dir: string) => fsState.manifests.get(dir) ?? null),
  writeManifest: vi.fn(async (dir: string, m: WorkspaceManifest) => {
    fsState.manifests.set(dir, structuredClone(m));
  }),
  createEmptyManifest: vi.fn((): WorkspaceManifest => ({
    schemaVersion: 1,
    workspaceId: "w",
    createdAt: "2026-10-17T00:00:00Z",
    updatedAt: "2026-10-17T00:00:00Z",
    artifacts: [],
  })),
}));

import { openWorkspace, registerArtifacts, _resetWorkspaceForTest } from "./api";

const ECHO = { app: "kuro" as const, step: "export", type: "kuro_echo_csv" as const };

afterEach(() => {
  fsState.manifests.clear();
  _resetWorkspaceForTest();
});

describe("registerArtifacts target", () => {
  it("writes the named registry even when another project is active", async () => {
    await openWorkspace("/projects/B");
    await registerArtifacts([{ ...ECHO, absolutePath: "/projects/A/design/run_echo.csv" }], "/projects/A");

    expect(fsState.manifests.get("/projects/A")?.artifacts.map((a) => a.path)).toEqual(["design/run_echo.csv"]);
    expect(fsState.manifests.get("/projects/B")?.artifacts).toEqual([]);
  });

  it("still defaults to the active registry", async () => {
    await openWorkspace("/projects/B");
    await registerArtifacts([{ ...ECHO, absolutePath: "/projects/B/design/run_echo.csv" }]);

    expect(fsState.manifests.get("/projects/B")?.artifacts.map((a) => a.path)).toEqual(["design/run_echo.csv"]);
  });
});
