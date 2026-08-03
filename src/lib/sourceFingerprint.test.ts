import { describe, expect, it, vi } from "vitest";

const hooks = vi.hoisted(() => ({
  stat: vi.fn(),
}));

vi.mock("@tauri-apps/plugin-fs", () => ({
  stat: hooks.stat,
}));

import { fingerprintSource, fingerprintsEqual } from "./sourceFingerprint";

describe("fingerprintSource", () => {
  it("빈 경로는 stat 없이 null을 돌려준다", async () => {
    const result = await fingerprintSource("");
    expect(result).toBeNull();
    expect(hooks.stat).not.toHaveBeenCalled();
  });

  it("stat 응답에서 size/mtimeMs를 뽑아낸다", async () => {
    hooks.stat.mockResolvedValue({ size: 42, mtime: new Date(1700000000000) });
    const result = await fingerprintSource("/proj/input.fasta");
    expect(result).toEqual({ size: 42, mtimeMs: 1700000000000 });
  });

  it("mtime이 없으면 0으로 채운다", async () => {
    hooks.stat.mockResolvedValue({ size: 10, mtime: null });
    const result = await fingerprintSource("/proj/input.fasta");
    expect(result).toEqual({ size: 10, mtimeMs: 0 });
  });

  it("stat 실패(파일 없음 등)는 null로 삼킨다", async () => {
    hooks.stat.mockRejectedValue(new Error("ENOENT"));
    const result = await fingerprintSource("/proj/missing.fasta");
    expect(result).toBeNull();
  });
});

describe("fingerprintsEqual", () => {
  it("size와 mtimeMs가 둘 다 같으면 true", () => {
    expect(fingerprintsEqual({ size: 1, mtimeMs: 2 }, { size: 1, mtimeMs: 2 })).toBe(true);
  });

  it("어느 한쪽이라도 다르면 false", () => {
    expect(fingerprintsEqual({ size: 1, mtimeMs: 2 }, { size: 1, mtimeMs: 3 })).toBe(false);
    expect(fingerprintsEqual({ size: 1, mtimeMs: 2 }, { size: 2, mtimeMs: 2 })).toBe(false);
  });

  it("어느 한쪽이라도 null/undefined면 false (지문 없음은 '모른다')", () => {
    expect(fingerprintsEqual(null, { size: 1, mtimeMs: 2 })).toBe(false);
    expect(fingerprintsEqual({ size: 1, mtimeMs: 2 }, undefined)).toBe(false);
    expect(fingerprintsEqual(null, null)).toBe(false);
  });
});
