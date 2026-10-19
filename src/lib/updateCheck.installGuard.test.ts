/**
 * Installing an update kills both sidecars and relaunches. It used to do that
 * whatever was running and with whatever was unsaved. The open workspace now
 * refuses it while a design, analysis or export runs, asked before the
 * download and again before the kill, and saves before anything is killed. A
 * failed save stops the install. Home registers nothing and installs as before.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const host = vi.hoisted(() => ({
  download: vi.fn(async () => undefined),
  install: vi.fn(async () => undefined),
  relaunch: vi.fn(async () => undefined),
  kill: vi.fn(async () => undefined),
}));
vi.mock("@tauri-apps/plugin-updater", () => ({
  check: vi.fn(async () => ({ download: host.download, install: host.install })),
}));
vi.mock("@tauri-apps/plugin-process", () => ({ relaunch: host.relaunch }));
vi.mock("./ipc", () => ({ killSidecar: host.kill }));

import { downloadAndInstallUpdate, registerUpdateInstallGuard } from "./updateCheck";

let unregister: (() => void) | undefined;
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("__TAURI_INTERNALS__", {});
});
afterEach(() => {
  unregister?.();
  unregister = undefined;
  vi.unstubAllGlobals();
});

describe("update install guard", () => {
  it("refuses before downloading while a job runs", async () => {
    unregister = registerUpdateInstallGuard({ busy: () => true, save: vi.fn(async () => undefined) });
    await expect(downloadAndInstallUpdate()).rejects.toThrow();
    expect(host.download).not.toHaveBeenCalled();
    expect(host.kill).not.toHaveBeenCalled();
  });

  it("refuses before killing when a job started during the download", async () => {
    let running = false;
    host.download.mockImplementationOnce(async () => { running = true; });
    unregister = registerUpdateInstallGuard({ busy: () => running, save: vi.fn(async () => undefined) });
    await expect(downloadAndInstallUpdate()).rejects.toThrow();
    expect(host.kill).not.toHaveBeenCalled();
    expect(host.install).not.toHaveBeenCalled();
  });

  it("saves before killing, then installs", async () => {
    const save = vi.fn(async () => undefined);
    unregister = registerUpdateInstallGuard({ busy: () => false, save });
    await expect(downloadAndInstallUpdate()).resolves.toBe(true);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.invocationCallOrder[0]).toBeLessThan(host.kill.mock.invocationCallOrder[0]);
    expect(host.install).toHaveBeenCalledTimes(1);
  });

  it("stops when the save fails", async () => {
    unregister = registerUpdateInstallGuard({ busy: () => false, save: async () => { throw new Error("disk full"); } });
    await expect(downloadAndInstallUpdate()).rejects.toThrow("disk full");
    expect(host.kill).not.toHaveBeenCalled();
    expect(host.install).not.toHaveBeenCalled();
  });

  it("installs from Home, where nothing is registered", async () => {
    await expect(downloadAndInstallUpdate()).resolves.toBe(true);
    expect(host.download).toHaveBeenCalledTimes(1);
    expect(host.install).toHaveBeenCalledTimes(1);
  });
});
