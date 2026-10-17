/**
 * The KURO progress channel carries two shapes: stage progress and the memory
 * warning `kuma_core/shared/dispatcher_runtime.py` builds. The listener used to
 * drop every memory warning because the guard knew only the first shape. A
 * memory warning must still not count as progress for the stall detector.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

type Payload = { payload: { kind: string; params: unknown } };
const events = vi.hoisted(() => ({ listener: null as null | ((event: Payload) => void) }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async (_name: string, callback: (event: Payload) => void) => {
    events.listener = callback;
    return () => { events.listener = null; };
  }),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => ({})) }));

import { getLastProgressAt, setProgressHandler, spawnSidecar } from "./index";
import { isProgressNotificationParams } from "@/types/validators";

const WARNING = { type: "memory_warning", ratio: 0.91, rss_mb: 812.4, level: "block" };

afterEach(() => {
  setProgressHandler(null);
  vi.unstubAllGlobals();
});

describe("KURO progress listener", () => {
  it("forwards a producer-shaped memory warning without counting it as progress", async () => {
    vi.stubGlobal("__TAURI_INTERNALS__", {});
    const handler = vi.fn();
    setProgressHandler(handler);
    await spawnSidecar();
    const before = getLastProgressAt();

    events.listener?.({ payload: { kind: "kuro", params: WARNING } });

    expect(handler).toHaveBeenCalledExactlyOnceWith(WARNING);
    expect(getLastProgressAt()).toBe(before);
  });

  it("forwards stage progress and records it for the stall detector", async () => {
    vi.stubGlobal("__TAURI_INTERNALS__", {});
    const handler = vi.fn();
    setProgressHandler(handler);
    await spawnSidecar();

    events.listener?.({ payload: { kind: "kuro", params: { value: 0.5, message: "Designing" } } });

    expect(handler).toHaveBeenCalledExactlyOnceWith({ value: 0.5, message: "Designing" });
    expect(getLastProgressAt()).not.toBeNull();
  });
});

describe("isProgressNotificationParams", () => {
  it.each(["warn", "block"])("accepts a %s memory warning", (level) => {
    expect(isProgressNotificationParams({ ...WARNING, level })).toBe(true);
  });

  it.each([
    { ...WARNING, level: "panic" },
    { ...WARNING, ratio: Number.NaN },
    { ...WARNING, rss_mb: -1 },
    { type: "memory_warning", value: 1, message: "x" },
    { type: "other", value: 1, message: "x" },
  ])("refuses %j", (payload) => {
    expect(isProgressNotificationParams(payload)).toBe(false);
  });
});
