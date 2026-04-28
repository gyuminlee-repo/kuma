import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { useSidecar } from "./useSidecar";

vi.mock("../lib/ipc-kuro", () => ({
  spawnSidecar: vi.fn().mockResolvedValue(undefined),
  killSidecar: vi.fn().mockResolvedValue(undefined),
  isSidecarRunning: vi.fn().mockReturnValue(false),
}));

import { killSidecar, spawnSidecar } from "../lib/ipc-kuro";

describe("useSidecar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps the kuro sidecar alive across unmount", async () => {
    const { result, unmount } = renderHook(() => useSidecar());

    await waitFor(() => {
      expect(result.current.status).toBe("ready");
    });
    expect(spawnSidecar).toHaveBeenCalledTimes(1);

    unmount();

    expect(killSidecar).not.toHaveBeenCalled();
  });
});
