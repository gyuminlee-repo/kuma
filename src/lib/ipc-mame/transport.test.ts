import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const host = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: host.invoke }));

import { killSidecar, sendRequest } from "./index";

const restored = { restored: true, verdict_count: 1, replicate_count: 1 };

describe("MAME host-owned RPC deadline", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("__TAURI_INTERNALS__", {});
    host.invoke.mockReset();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it.each([60_000, 200])(
    "allows cold startup plus execution within the host's %ims budget",
    async (budget) => {
      let cold = true;
      host.invoke.mockImplementation(async () => {
        if (cold) {
          cold = false;
          await new Promise<void>((resolve) => setTimeout(resolve, budget * 0.75));
        }
        await new Promise<void>((resolve) => setTimeout(resolve, budget * 0.5));
        return restored;
      });
      const request = sendRequest("load_analyze_result", {}, budget);
      const checked = Promise.allSettled([expect(request).resolves.toEqual(restored)]);
      await vi.advanceTimersByTimeAsync(budget * 1.25);
      expect((await checked).map(({ status }) => status)).toEqual(["fulfilled"]);
      expect(host.invoke).toHaveBeenCalledExactlyOnceWith("sidecar_rpc", {
        kind: "mame", method: "load_analyze_result", params: {}, timeoutMs: budget,
      });

      const warm = sendRequest("load_analyze_result", {}, budget);
      await vi.advanceTimersByTimeAsync(budget * 0.5);
      await expect(warm).resolves.toEqual(restored);
      expect(host.invoke).toHaveBeenCalledTimes(2);
    },
  );

  it("preserves the default host budget", async () => {
    host.invoke.mockResolvedValue(restored);
    await sendRequest("load_analyze_result", {});
    expect(host.invoke).toHaveBeenCalledWith("sidecar_rpc", {
      kind: "mame", method: "load_analyze_result", params: {}, timeoutMs: 60_000,
    });
  });

  it("propagates a host timeout without retrying a state change", async () => {
    const error = new Error("RPC timeout: load_analyze_result after 200ms");
    host.invoke.mockImplementation(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 150));
      await new Promise<void>((resolve) => setTimeout(resolve, 200));
      throw error;
    });
    const request = sendRequest("load_analyze_result", {}, 200);
    const checked = Promise.allSettled([expect(request).rejects.toBe(error)]);
    await vi.advanceTimersByTimeAsync(350);
    expect((await checked).map(({ status }) => status)).toEqual(["fulfilled"]);
    expect(host.invoke).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("propagates a spawn failure without retrying", async () => {
    const error = new Error("Sidecar integrity check failed");
    host.invoke.mockRejectedValue(error);
    await expect(sendRequest("load_analyze_result", {})).rejects.toBe(error);
    expect(host.invoke).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("lets host cancellation reject a pending request", async () => {
    const error = new Error("Sidecar killed");
    let cancel: () => void = () => { throw new Error("No pending request"); };
    host.invoke.mockImplementation((command: string) => {
      if (command === "sidecar_kill") {
        cancel();
        return Promise.resolve();
      }
      return new Promise<never>((_, reject) => { cancel = () => reject(error); });
    });
    const checked = expect(sendRequest("load_analyze_result", {})).rejects.toBe(error);
    await killSidecar();
    await checked;
    expect(host.invoke).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("still rejects a malformed response", async () => {
    host.invoke.mockResolvedValue({ restored: true });
    await expect(sendRequest("load_analyze_result", {})).rejects.toThrow();
  });
});
