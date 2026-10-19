/**
 * A `.kuro.json` picked on Home is what the session restores.
 *
 * The scratch session used to ignore the picked file and restore the app-data
 * scratch snapshot instead. It now restores the file, and the automatic
 * redesign a workspace can ask for starts after the restore overlay is down
 * instead of holding it up for the length of a design. A file that can no
 * longer be read closes the session with the reason on Home: an open session
 * on an empty workspace would save over the file.
 */
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  load: vi.fn(),
  readScratch: vi.fn(),
  endHydration: vi.fn(),
  block: vi.fn(),
}));
vi.mock("@/lib/workspaceFile", () => ({ loadWorkspaceFile: mocks.load }));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
vi.mock("@/lib/ipc-mame", () => ({ sendRequest: vi.fn(), isSidecarRunning: () => false, cancelAndRespawn: vi.fn() }));
vi.mock("@/lib/autosave", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/autosave")>()),
  readScratchAutosave: mocks.readScratch,
  beginHydration: vi.fn(),
  endHydration: mocks.endHydration,
  blockAutosaveWrites: mocks.block,
}));
vi.mock("@/lib/workspace", () => ({
  openWorkspace: vi.fn(),
  closeWorkspace: vi.fn(),
  getLatestArtifact: vi.fn(async () => null),
  getActiveWorkspace: () => null,
  clearWorkspace: vi.fn(),
}));

import { ProjectProvider } from "@/state/projectContext";
import { useAppStore } from "@/store/appStore";
import { useAutosaveHydration } from "./useAutosaveHydration";

const FILE = "/shared/plan.kuro.json";
const WORKSPACE = { schema_version: "0.3", inputs: { mutationText: "A1V" } };
const originalRestore = useAppStore.getState().restoreWorkspace;

function Harness() {
  useAutosaveHydration(() => {});
  return null;
}
function open() {
  render(
    <ProjectProvider value={{ path: FILE, name: "plan", scratch: true, workspaceFile: FILE }}>
      <Harness />
    </ProjectProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => {
  cleanup();
  useAppStore.setState({ restoreWorkspace: originalRestore });
});

describe("a session opened from a workspace file", () => {
  it("restores the file, not the scratch snapshot, and redesigns after the overlay", async () => {
    mocks.load.mockResolvedValue(WORKSPACE);
    const redesign = vi.fn(async () => undefined);
    const restore = vi.fn(async () => redesign);
    useAppStore.setState({ restoreWorkspace: restore });

    open();
    await waitFor(() => expect(redesign).toHaveBeenCalledTimes(1));
    expect(mocks.load).toHaveBeenCalledWith(FILE);
    expect(restore).toHaveBeenCalledWith(WORKSPACE, expect.objectContaining({ deferRedesign: true }));
    expect(mocks.readScratch).not.toHaveBeenCalled();
    expect(mocks.endHydration.mock.invocationCallOrder[0]).toBeLessThan(redesign.mock.invocationCallOrder[0]);
  });

  it("returns to Home with the reason when the file cannot be read any more", async () => {
    mocks.load.mockRejectedValue(new Error("File not found: /shared/plan.kuro.json"));
    const restore = vi.fn(async () => null);
    useAppStore.setState({ restoreWorkspace: restore });
    const returned = vi.fn();
    const onReturn = (event: Event) => returned((event as CustomEvent<{ error?: string }>).detail?.error);
    window.addEventListener("kuma:return-to-home", onReturn);
    try {
      open();
      await waitFor(() => expect(returned).toHaveBeenCalledWith(expect.stringContaining("File not found")));
      expect(restore).not.toHaveBeenCalled();
      expect(mocks.block).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("kuma:return-to-home", onReturn);
    }
  });
});
