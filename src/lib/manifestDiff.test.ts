/**
 * manifestDiff.test.ts — §12 Reproducibility: diffManifests 단위 테스트
 *
 * @tauri-apps/plugin-fs 는 사용하지 않으므로 mock 불필요.
 */

import { describe, it, expect } from "vitest";
import { diffManifests, type DiffEntry } from "./manifestDiff";
import type { RunManifest } from "./runManifest";

// ── 픽스처 헬퍼 ───────────────────────────────────────────────────────────────

function baseManifest(overrides: Partial<RunManifest> = {}): RunManifest {
  return {
    schema_version: "1.0",
    method: "design_sdm_primers",
    kuma_version: "0.5.0",
    kuro_module_version: "0.3.0",
    python_version: "3.11.9",
    platform: "linux",
    started_at: "2026-01-01T00:00:00Z",
    finished_at: "2026-01-01T00:00:10Z",
    duration_seconds: 10,
    inputs: {
      reference_fasta: {
        path: "/data/seq.fasta",
        sha256: "abc123",
        size_bytes: 1024,
      },
    },
    params: {
      tol_max: 3,
      overlap_tm: 60.0,
    },
    seed: 42,
    ...overrides,
  };
}

function findEntry(entries: DiffEntry[], path: string): DiffEntry | undefined {
  return entries.find((e) => e.path === path);
}

// ── 테스트 ─────────────────────────────────────────────────────────────────────

describe("diffManifests", () => {
  // ── 동일 manifest ────────────────────────────────────────────────────────

  it("동일 manifest → 모든 항목 'same'", () => {
    const a = baseManifest();
    const b = baseManifest();
    const result = diffManifests(a, b);

    const allEntries = [
      ...result.meta,
      ...result.inputs,
      ...result.params,
      ...result.timing,
    ];

    expect(allEntries.every((e) => e.status === "same")).toBe(true);
  });

  // ── params 차이 ──────────────────────────────────────────────────────────

  it("params.tol_max 만 다를 때 → 1개 'changed' 항목", () => {
    const a = baseManifest({ params: { tol_max: 3, overlap_tm: 60.0 } });
    const b = baseManifest({ params: { tol_max: 5, overlap_tm: 60.0 } });
    const result = diffManifests(a, b);

    const changedEntries = result.params.filter((e) => e.status === "changed");
    expect(changedEntries).toHaveLength(1);

    const entry = changedEntries[0];
    expect(entry.path).toBe("params.tol_max");
    expect(entry.left).toBe(3);
    expect(entry.right).toBe(5);
  });

  // ── inputs 추가 ──────────────────────────────────────────────────────────

  it("inputs 에 새 키 추가 → 해당 필드들 'added'", () => {
    const a = baseManifest();
    const b = baseManifest({
      inputs: {
        reference_fasta: {
          path: "/data/seq.fasta",
          sha256: "abc123",
          size_bytes: 1024,
        },
        mutations_csv: {
          path: "/data/mut.csv",
          sha256: "def456",
          size_bytes: 512,
        },
      },
    });
    const result = diffManifests(a, b);

    const addedEntries = result.inputs.filter((e) => e.status === "added");
    // mutations_csv.path, .sha256, .size_bytes → 3개 added
    expect(addedEntries).toHaveLength(3);
    expect(addedEntries.map((e) => e.path)).toContain("inputs.mutations_csv.path");
    expect(addedEntries.map((e) => e.path)).toContain("inputs.mutations_csv.sha256");
    expect(addedEntries.map((e) => e.path)).toContain("inputs.mutations_csv.size_bytes");
  });

  // ── inputs 제거 ──────────────────────────────────────────────────────────

  it("inputs 키 제거 → 해당 필드들 'removed'", () => {
    const a = baseManifest({
      inputs: {
        reference_fasta: {
          path: "/data/seq.fasta",
          sha256: "abc123",
          size_bytes: 1024,
        },
        mutations_csv: {
          path: "/data/mut.csv",
          sha256: "def456",
          size_bytes: 512,
        },
      },
    });
    const b = baseManifest();
    const result = diffManifests(a, b);

    const removedEntries = result.inputs.filter((e) => e.status === "removed");
    expect(removedEntries).toHaveLength(3);
    expect(removedEntries.map((e) => e.path)).toContain("inputs.mutations_csv.sha256");
  });

  // ── 중첩 객체 params ─────────────────────────────────────────────────────

  it("params.advanced.seed 차이 → 정확한 dot-notation path", () => {
    const a = baseManifest({
      params: {
        tol_max: 3,
        advanced: { seed: 42, extra: "x" },
      },
    });
    const b = baseManifest({
      params: {
        tol_max: 3,
        advanced: { seed: 99, extra: "x" },
      },
    });
    const result = diffManifests(a, b);

    const changedEntries = result.params.filter((e) => e.status === "changed");
    expect(changedEntries).toHaveLength(1);
    expect(changedEntries[0].path).toBe("params.advanced.seed");
    expect(changedEntries[0].left).toBe(42);
    expect(changedEntries[0].right).toBe(99);
  });

  // ── params 배열 인덱스 비교 ──────────────────────────────────────────────

  it("params 안 배열 인덱스 단위 비교", () => {
    const a = baseManifest({
      params: { ranges: [1, 2, 3] },
    });
    const b = baseManifest({
      params: { ranges: [1, 2, 99] },
    });
    const result = diffManifests(a, b);

    const changedEntries = result.params.filter((e) => e.status === "changed");
    expect(changedEntries).toHaveLength(1);
    expect(changedEntries[0].path).toBe("params.ranges[2]");
    expect(changedEntries[0].left).toBe(3);
    expect(changedEntries[0].right).toBe(99);
  });

  // ── meta / timing 섹션 ───────────────────────────────────────────────────

  it("kuma_version 다를 때 meta 섹션에 'changed' 1건", () => {
    const a = baseManifest({ kuma_version: "0.5.0" });
    const b = baseManifest({ kuma_version: "0.6.0" });
    const result = diffManifests(a, b);

    const entry = findEntry(result.meta, "kuma_version");
    expect(entry).toBeDefined();
    expect(entry!.status).toBe("changed");
    expect(entry!.left).toBe("0.5.0");
    expect(entry!.right).toBe("0.6.0");
  });

  it("timing: duration_seconds 다를 때 timing 섹션에 'changed' 1건", () => {
    const a = baseManifest({ duration_seconds: 10 });
    const b = baseManifest({ duration_seconds: 25 });
    const result = diffManifests(a, b);

    const entry = findEntry(result.timing, "duration_seconds");
    expect(entry).toBeDefined();
    expect(entry!.status).toBe("changed");
  });

  // ── seed null 처리 ───────────────────────────────────────────────────────

  it("seed null vs 42 → meta 섹션에 'changed'", () => {
    const a = baseManifest({ seed: null });
    const b = baseManifest({ seed: 42 });
    const result = diffManifests(a, b);

    const entry = findEntry(result.meta, "seed");
    expect(entry).toBeDefined();
    expect(entry!.status).toBe("changed");
    expect(entry!.left).toBeNull();
    expect(entry!.right).toBe(42);
  });
});
