/**
 * The artifact registry remembers one project folder (`activeDir`, mirrored to
 * localStorage so a restart can reopen it). A scratch session has no project
 * folder, so entering one has to forget the previous project's folder.
 * Otherwise three things reach back into that project from scratch: the
 * EVOLVEpro field auto-loads its table, an export registers itself in its
 * manifest, and Clear All removes its KURO entries.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WorkspaceManifest } from "./types";

const fsState = vi.hoisted(() => ({
  manifests: new Map<string, WorkspaceManifest>(),
  writes: [] as string[],
}));

vi.mock("@tauri-apps/api/path", () => ({
  isAbsolute: vi.fn(async (p: string) => p.startsWith("/")),
  resolve: vi.fn(async (dir: string, p: string) => (p.startsWith("/") ? p : `${dir}/${p}`)),
}));

vi.mock("@tauri-apps/plugin-fs", () => ({
  exists: vi.fn(async () => true),
  stat: vi.fn(async () => ({ size: 10, mtime: new Date("2026-09-29T00:00:00Z") })),
}));

vi.mock("./manifest", () => ({
  readManifest: vi.fn(async (dir: string) => fsState.manifests.get(dir) ?? null),
  writeManifest: vi.fn(async (dir: string, m: WorkspaceManifest) => {
    fsState.writes.push(dir);
    fsState.manifests.set(dir, structuredClone(m));
  }),
  createEmptyManifest: vi.fn(
    (): WorkspaceManifest => ({
      schemaVersion: 1,
      workspaceId: "w",
      createdAt: "2026-09-29T00:00:00Z",
      updatedAt: "2026-09-29T00:00:00Z",
      artifacts: [],
    }),
  ),
}));

import {
  closeWorkspace,
  ensureWorkspaceFromExportPath,
  getActiveWorkspace,
  openWorkspace,
  registerArtifacts,
  restorePersistedWorkspace,
  _resetWorkspaceForTest,
} from "./api";
import { useArtifact } from "./useArtifact";
import { useAppStore } from "@/store/appStore";

const LS_KEY = "kuma:artifact-registry:active";
const PROJECT = "/projects/A";

function projectManifest(): WorkspaceManifest {
  return {
    schemaVersion: 1,
    workspaceId: "A",
    createdAt: "2026-09-29T00:00:00Z",
    updatedAt: "2026-09-29T00:00:00Z",
    artifacts: [
      {
        id: "e1",
        app: "kuro",
        step: "input",
        type: "evolvepro_csv",
        path: "evolvepro.csv",
        producedAt: "2026-09-29T00:00:00Z",
        mtime: "2026-09-29T00:00:00.000Z",
        sizeBytes: 10,
      },
    ],
  };
}

beforeEach(() => {
  _resetWorkspaceForTest();
  localStorage.clear();
  fsState.manifests.clear();
  fsState.manifests.set(PROJECT, projectManifest());
  fsState.writes.length = 0;
});

afterEach(() => {
  _resetWorkspaceForTest();
  localStorage.clear();
});

describe("closeWorkspace", () => {
  it("forgets the project folder in memory and in localStorage", async () => {
    await openWorkspace(PROJECT);
    expect(localStorage.getItem(LS_KEY)).toBe(PROJECT);

    closeWorkspace();

    expect(getActiveWorkspace()).toBeNull();
    expect(localStorage.getItem(LS_KEY)).toBeNull();
  });

  it("stops offering the previous project's EVOLVEpro table to the auto-fill", async () => {
    await openWorkspace(PROJECT);
    const { result } = renderHook(() => useArtifact("evolvepro_csv"));
    await waitFor(() => expect(result.current?.path).toBe(`${PROJECT}/evolvepro.csv`));

    act(() => {
      closeWorkspace();
    });

    await waitFor(() => expect(result.current).toBeNull());
  });

  it("lets a scratch export open its own folder instead of the previous project's manifest", async () => {
    await openWorkspace(PROJECT);
    closeWorkspace();
    fsState.writes.length = 0;

    await ensureWorkspaceFromExportPath("/scratch/out/run_primers.xlsx");
    await registerArtifacts([
      { app: "kuro", step: "export", type: "sdm_primer_xlsx", absolutePath: "/scratch/out/run_primers.xlsx" },
    ]);

    expect(getActiveWorkspace()).toBe("/scratch/out");
    expect(fsState.writes).not.toContain(PROJECT);
    expect(fsState.manifests.get(PROJECT)).toEqual(projectManifest());
  });

  it("keeps Clear All in scratch away from the previous project's manifest", async () => {
    await openWorkspace(PROJECT);
    closeWorkspace();
    fsState.writes.length = 0;

    useAppStore.getState().resetAll();
    // resetAll clears the manifest through a dynamic import; let it settle.
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    expect(fsState.writes).not.toContain(PROJECT);
    expect(fsState.manifests.get(PROJECT)?.artifacts).toHaveLength(1);
  });

  it("control: without closing, Clear All does reach the project manifest", async () => {
    await openWorkspace(PROJECT);
    fsState.writes.length = 0;

    useAppStore.getState().resetAll();
    await waitFor(() => expect(fsState.writes).toContain(PROJECT));
    expect(fsState.manifests.get(PROJECT)?.artifacts).toHaveLength(0);
  });

  it("wins over a boot-time restore that resolves after it", async () => {
    localStorage.setItem(LS_KEY, PROJECT);
    const pending = restorePersistedWorkspace();
    closeWorkspace();
    await pending;

    expect(getActiveWorkspace()).toBeNull();
    expect(localStorage.getItem(LS_KEY)).toBeNull();
  });
});
