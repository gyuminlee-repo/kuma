import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { runQualityFixture } from "@/test-utils/runQualityFixture";

const native = vi.hoisted(() => ({ rpc: vi.fn(), read: vi.fn() }));
vi.mock("@/lib/ipc", () => ({ rawSidecarRpc: native.rpc, killSidecar: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", async (importOriginal) => ({
  ...await importOriginal<typeof import("@tauri-apps/plugin-fs")>(),
  exists: async (path: string) => path.endsWith("mame-result.json"),
  readTextFile: native.read,
}));
vi.mock("@/lib/autosave", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/autosave")>(),
  readAutosave: async () => ({ status: "missing" }),
  readScratchAutosave: async () => ({ status: "missing" }),
}));
vi.mock("@/lib/workspace", () => ({
  openWorkspace: vi.fn(), getLatestArtifact: async () => null,
  getActiveWorkspace: () => null, clearWorkspace: vi.fn(),
}));
vi.mock("@/lib/mame/detectProjectFiles", () => ({
  detectProjectFiles: async () => ({}), detectFromInputDir: async () => ({}),
}));

import { useAutosaveHydration } from "./useAutosaveHydration";
import { useMameAppStore } from "@/store/mame/mameAppStore";

const onMessage = () => {};
function Harness() {
  const { hydrating } = useAutosaveHydration(onMessage);
  return <p role="status">{hydrating ? "loading" : "done"}</p>;
}
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it.each(["position_recurrence", "indel_recurrence", "read_length"])(
  "refuses malformed %s in real hydration before sidecar replay or store assignment", async (field) => {
    native.read.mockResolvedValue(JSON.stringify({ schema: 1, kuma_version: __APP_VERSION__,
      result: { run_quality: { ...runQualityFixture, [field]: null } },
    }));
    render(<ProjectProvider value={{ path: "/qa", name: "QA", scratch: false }}><Harness /></ProjectProvider>);
    await waitFor(() => expect(native.read).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("done"));
    expect(native.rpc).not.toHaveBeenCalled();
    expect(useMameAppStore.getState().runQuality).toBeNull();
    expect(useMameAppStore.getState().currentMameSubStep).not.toBe("analyze.review");
  },
);
