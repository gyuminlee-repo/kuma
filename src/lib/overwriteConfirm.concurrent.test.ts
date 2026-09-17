import { describe, expect, it, vi } from "vitest";
vi.mock("@tauri-apps/plugin-fs", () => ({ exists: vi.fn() }));
import {
  getPendingOverwritePath, getPendingOverwriteMessage,
  requestOverwriteConfirm, resolveOverwriteConfirm,
} from "./overwriteConfirm";

describe("FD01 overlapping confirmations", () => {
  it("cancels the displaced caller and resolves the visible request", async () => {
    const firstDone = vi.fn();
    const first = requestOverwriteConfirm("first.xlsx").then(firstDone);
    const second = requestOverwriteConfirm("second.xlsx", "second message");
    await Promise.resolve();
    expect(firstDone).toHaveBeenCalledWith("cancel");
    expect(getPendingOverwritePath()).toBe("second.xlsx");
    expect(getPendingOverwriteMessage()).toBe("second message");
    resolveOverwriteConfirm("overwrite");
    await expect(second).resolves.toBe("overwrite");
    await first;
    expect(getPendingOverwritePath()).toBeNull();
  });
});
