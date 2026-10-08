import { describe, expect, it, vi } from "vitest";
import {
  checkForLatestRelease,
  compareVersions,
  downloadAndInstallUpdate,
  isTauriRuntime,
} from "./updateCheck";

describe("compareVersions", () => {
  it("compares stable and four-part release versions", () => {
    expect(compareVersions("0.13.12", "0.13.11")).toBeGreaterThan(0);
    expect(compareVersions("0.13.11.1", "0.13.11")).toBeGreaterThan(0);
    expect(compareVersions("v0.13.11", "0.13.11.0")).toBe(0);
  });

  it("orders stable releases after prereleases", () => {
    expect(compareVersions("0.14.0", "0.14.0-rc.1")).toBeGreaterThan(0);
    expect(compareVersions("0.14.0-beta.2", "0.14.0-beta.10")).toBeLessThan(0);
  });

  it("rejects malformed versions", () => {
    expect(() => compareVersions("latest", "0.13.11")).toThrow(
      "Invalid release version",
    );
  });
});

describe("checkForLatestRelease", () => {
  it("reports a newer GitHub release and constructs its release URL", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ tag_name: "v0.13.12" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(checkForLatestRelease("0.13.11", fetchMock)).resolves.toEqual({
      currentVersion: "0.13.11",
      latestVersion: "0.13.12",
      releaseUrl: "https://github.com/gyuminlee-repo/kuma/releases/tag/v0.13.12",
      updateAvailable: true,
    });
  });

  it("does not recommend the installed release", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ tag_name: "v0.13.11" }), { status: 200 }),
    );

    const result = await checkForLatestRelease("0.13.11", fetchMock);
    expect(result.updateAvailable).toBe(false);
  });

  it("surfaces GitHub API failures", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(new Response(null, { status: 403 }));

    await expect(checkForLatestRelease("0.13.11", fetchMock)).rejects.toThrow(
      "GitHub returned HTTP 403",
    );
  });
});

describe("auto-update runtime gating", () => {
  it("reports non-Tauri runtime in the test/browser environment", () => {
    // jsdom has no __TAURI_INTERNALS__, so the packaged-app updater path is off.
    expect(isTauriRuntime()).toBe(false);
  });

  it("returns false (no install) outside the Tauri runtime, without throwing", async () => {
    // Callers rely on `false` to fall back to the release page; it must never
    // throw or attempt a plugin import in the browser/dev context.
    const progress = vi.fn();
    await expect(downloadAndInstallUpdate(progress)).resolves.toBe(false);
    expect(progress).not.toHaveBeenCalled();
  });
});
