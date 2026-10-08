import { beforeEach, describe, expect, it, vi } from "vitest";

const mockExists = vi.hoisted(() => vi.fn());
const mockReadTextFile = vi.hoisted(() => vi.fn());
const mockRename = vi.hoisted(() => vi.fn());

vi.mock("@tauri-apps/plugin-fs", () => ({
  exists: mockExists,
  readTextFile: mockReadTextFile,
  rename: mockRename,
  writeTextFile: vi.fn(),
  readDir: vi.fn(),
}));
vi.mock("@tauri-apps/api/path", () => ({ join: (...parts: string[]) => Promise.resolve(parts.join("/")) }));

import { readManifest } from "./manifest";

beforeEach(() => {
  vi.clearAllMocks();
  mockExists.mockResolvedValue(true);
  mockRename.mockResolvedValue(undefined);
});

describe("readManifest", () => {
  it("returns null only when the manifest is genuinely absent", async () => {
    mockExists.mockResolvedValue(false);
    await expect(readManifest("/project")).resolves.toBeNull();
  });

  it("does not turn an unreadable manifest into a new empty workspace", async () => {
    mockReadTextFile.mockRejectedValue(new Error("EACCES"));
    await expect(readManifest("/project")).rejects.toThrow("could not be read");
  });

  it("preserves an invalid manifest then reports the parse failure", async () => {
    mockReadTextFile.mockResolvedValue("not json");
    await expect(readManifest("/project")).rejects.toThrow("invalid");
    expect(mockRename).toHaveBeenCalledWith(
      "/project/.kuma-workspace.json",
      expect.stringMatching(/\.kuma-workspace\.json\.bak-/),
    );
  });
});
