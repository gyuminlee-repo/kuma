import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactRef } from "@/lib/workspace/types";
import type { DetectedPaths } from "@/lib/mame/detectProjectFiles";

const boundaries = vi.hoisted(() => ({
  detect: vi.fn<() => Promise<DetectedPaths>>(),
  latest: vi.fn<() => Promise<ArtifactRef | null>>(),
}));
vi.mock("@/lib/mame/detectProjectFiles", () => ({
  detectProjectFiles: boundaries.detect,
  detectFromInputDir: vi.fn(async () => ({})),
}));
vi.mock("@/lib/workspace", () => ({
  getLatestArtifact: boundaries.latest,
  getActiveWorkspace: vi.fn(() => null),
  openWorkspace: vi.fn(),
  clearWorkspace: vi.fn(),
}));
vi.mock("@/lib/ipc-kuro", () => ({ setProgressHandler: vi.fn(), sendRequest: vi.fn() }));
vi.mock("@/lib/ipc-mame", () => ({ sendRequest: vi.fn(), isSidecarRunning: () => false }));

import { applyMameAutoDetect } from "./useAutosaveHydration";
import { useMameAppStore } from "@/store/mame/mameAppStore";

const artifact: ArtifactRef = {
  id: "old-primer", app: "kuro", step: "output", type: "sdm_primer_xlsx",
  path: "/old-project/primers.xlsx", producedAt: "2026-09-17T00:00:00Z",
  mtime: "2026-09-17T00:00:00Z", sizeBytes: 128, stale: false,
};

describe("FH-01: artifact lookup ownership", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    boundaries.detect.mockResolvedValue({});
    boundaries.latest.mockResolvedValue(artifact);
    useMameAppStore.setState({ expectedPath: "", inputDir: "" });
  });

  it("applies an artifact and completion while current", async () => {
    const completed = vi.fn();
    await applyMameAutoDetect("/old-project", completed, () => true);
    expect(useMameAppStore.getState().expectedPath).toBe(artifact.path);
    expect(completed).toHaveBeenCalledOnce();
  });

  it.each(["artifact", "empty", "error"])("ignores cancelled %s lookup and its completion", async (outcome) => {
    let current = true;
    let settle: () => void = () => { throw new Error("lookup not entered"); };
    let entered: () => void = () => {};
    const started = new Promise<void>((resolve) => { entered = resolve; });
    boundaries.latest.mockImplementation(() => new Promise((resolve, reject) => {
      settle = () => outcome === "error" ? reject(new Error("lookup failed"))
        : resolve(outcome === "artifact" ? artifact : null);
      entered();
    }));
    const completed = vi.fn();
    const run = applyMameAutoDetect("/old-project", completed, () => current);
    await started;
    current = false;
    useMameAppStore.setState({ expectedPath: "", inputDir: "/new-project/run" });
    settle();
    await run;
    expect(useMameAppStore.getState().expectedPath).toBe("");
    expect(completed).not.toHaveBeenCalled();
  });
});
