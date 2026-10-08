/**
 * KuroTab is a lazy() chunk in MainShell, and every MainShell test
 * (MainShell.test.tsx, MainShell.integration.test.tsx,
 * MainShell.contracts.test.tsx) replaces it with `vi.mock("./KuroTab", ...)`,
 * so a broken KuroTab module has no CI test that statically imports it.
 */

import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "@/store/appStore";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(async (method: string) => {
    if (method === "health_info") throw new Error("No sidecar in load test");
    return undefined;
  }),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(async () => {}),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

vi.mock("@/hooks/useSidecar", () => ({
  useSidecar: () => ({ status: "ready", retry: vi.fn() }),
}));

import { KuroTab } from "./KuroTab";

const initialState = useAppStore.getState();

describe("KuroTab: module load", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useAppStore.setState({
      loadSettings: vi.fn(async () => {}),
      loadPolymerases: vi.fn(async () => {}),
      loadNetworkConsentSettings: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    useAppStore.setState(initialState, true);
    localStorage.clear();
  });

  it("renders without crashing", () => {
    render(<KuroTab />);
    expect(screen.getByRole("tabpanel")).toBeInTheDocument();
  });
});
