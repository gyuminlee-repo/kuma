/**
 * A table dropped onto the window is the operator's choice just like one
 * picked with Browse, so it sets the same store flag that keeps the manifest
 * auto-fill (MutationInput) from replacing it.
 */

import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const drop = vi.hoisted(() => ({
  handler: null as null | ((event: { payload: { type: string; paths?: string[] } }) => void),
}));

// The webview and window modules alias to one stub file in vitest.config.ts,
// so the rest of the stub is kept and only the drop listener is captured.
vi.mock("@tauri-apps/api/webview", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@tauri-apps/api/webview")),
  getCurrentWebview: () => ({
    onDragDropEvent: async (handler: typeof drop.handler) => {
      drop.handler = handler;
      return () => {};
    },
  }),
}));

vi.mock("@/lib/reRun", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("@/lib/reRun");
  return {
    ...actual,
    tryHandleManifestDrop: vi.fn(async () => ({ handled: false })),
    tryHandleTwoManifestsDrop: vi.fn(async () => ({ handled: false })),
  };
});

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn((method: string) =>
    method === "health_info"
      ? Promise.reject(new Error("sidecar unavailable in test"))
      : Promise.resolve(undefined),
  ),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(() => Promise.resolve()),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

import { AppLayout } from "./AppLayout";
import { useAppStore } from "../../store/appStore";

const originalLoad = useAppStore.getState().loadEvolveproCsv;

afterEach(() => {
  useAppStore.setState({ loadEvolveproCsv: originalLoad });
  useAppStore.getState().resetAll();
});

describe("AppLayout CSV drop", () => {
  it("loads a dropped table and records it as the operator's pick", async () => {
    const loadSpy = vi.fn(async () => {});
    useAppStore.setState({ loadEvolveproCsv: loadSpy as unknown as typeof originalLoad });
    render(<AppLayout />);
    await waitFor(() => expect(drop.handler).not.toBeNull());

    drop.handler!({ payload: { type: "drop", paths: ["/elsewhere/dropped.csv"] } });

    await waitFor(() => expect(loadSpy).toHaveBeenCalledWith("/elsewhere/dropped.csv"));
    expect(useAppStore.getState().evolveproCsvUserPicked).toBe(true);
  });
});
