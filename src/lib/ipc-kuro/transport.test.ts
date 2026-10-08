import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const host = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: host.invoke }));

import { killSidecar, sendRequest } from "./index";

const csv = {
  variants: ["Q232A"],
  y_preds: [1],
  total_count: 1,
  selected_count: 1,
};

describe("KURO host-owned RPC deadline", () => {
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
    "allows cold startup plus a CSV response inside the host's %ims budget",
    async (budget) => {
      // Model ensure_spawned before the host starts its post-write RPC timer.
      // Cold startup takes 3/4 of the budget; CSV execution takes another 1/2.
      let cold = true;
      host.invoke.mockImplementation(async () => {
        if (cold) {
          cold = false;
          await new Promise<void>((resolve) => setTimeout(resolve, budget * 0.75));
        }
        await new Promise<void>((resolve) => setTimeout(resolve, budget * 0.5));
        return csv;
      });
      const first = sendRequest("load_evolvepro_csv", { filepath: "input.csv" }, budget);
      const firstCheck = expect(first).resolves.toEqual(csv);
      // Attach the check before advancing the clock, including in the red run.
      const checked = Promise.allSettled([firstCheck]);
      await vi.advanceTimersByTimeAsync(budget * 1.25);
      expect((await checked).map(({ status }) => status)).toEqual(["fulfilled"]);
      expect(host.invoke).toHaveBeenCalledTimes(1);
      expect(host.invoke).toHaveBeenLastCalledWith("sidecar_rpc", {
        kind: "kuro", method: "load_evolvepro_csv",
        params: { filepath: "input.csv" }, timeoutMs: budget,
      });

      const warm = sendRequest("load_evolvepro_csv", { filepath: "input.csv" }, budget);
      await vi.advanceTimersByTimeAsync(budget * 0.5);
      await expect(warm).resolves.toEqual(csv);
      expect(host.invoke).toHaveBeenCalledTimes(2);
    },
  );

  it("preserves the default host budget", async () => {
    host.invoke.mockResolvedValue(csv);
    await sendRequest("load_evolvepro_csv", {});
    expect(host.invoke).toHaveBeenCalledWith("sidecar_rpc", {
      kind: "kuro", method: "load_evolvepro_csv", params: {}, timeoutMs: 60_000,
    });
  });

  it("surfaces a host deadline after startup without retrying a mutation", async () => {
    const timeout = new Error("RPC timeout: swap_primer after 200ms");
    host.invoke.mockImplementation(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 150));
      await new Promise<void>((resolve) => setTimeout(resolve, 200));
      throw timeout;
    });
    const request = sendRequest("swap_primer", {
      mutation: "Q232A", candidate_idx: 0, swap_type: "both",
    }, 200);
    const checked = Promise.allSettled([expect(request).rejects.toBe(timeout)]);
    await vi.advanceTimersByTimeAsync(350);
    expect((await checked).map(({ status }) => status)).toEqual(["fulfilled"]);
    expect(host.invoke).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("propagates spawn failure without retrying", async () => {
    const error = new Error("Sidecar integrity check failed");
    host.invoke.mockRejectedValue(error);
    await expect(sendRequest("load_evolvepro_csv", {})).rejects.toBe(error);
    expect(host.invoke).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("lets host cancellation reject the pending request", async () => {
    const error = new Error("Sidecar killed");
    let cancel: () => void = () => { throw new Error("No pending request"); };
    host.invoke.mockImplementation((command: string) => {
      if (command === "sidecar_kill") {
        cancel();
        return Promise.resolve();
      }
      return new Promise<never>((_, reject) => { cancel = () => reject(error); });
    });
    const request = sendRequest("load_evolvepro_csv", {});
    const checked = expect(request).rejects.toBe(error);
    await killSidecar();
    await checked;
    expect(host.invoke).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("still rejects an invalid CSV response", async () => {
    host.invoke.mockResolvedValue({ variants: [] });
    await expect(sendRequest("load_evolvepro_csv", {})).rejects.toThrow();
  });
});
