import { beforeEach, describe, expect, it, vi } from "vitest";

const files = new Map<string, string>();
vi.mock("@tauri-apps/plugin-fs", () => ({
  exists: async (path: string) => files.has(path),
  readTextFile: async (path: string) => files.get(path) ?? "",
  rename: vi.fn(),
}));
vi.mock("@/lib/autosave", () => ({
  ensureAutosaveDir: vi.fn(),
  atomicWriteJson: async (path: string, value: unknown) => {
    files.set(path, JSON.stringify(value));
  },
}));
vi.mock("@/lib/mame/resultContract", () => ({ RESULT_CONTRACT: 1 }));
vi.mock("@/types/mame/runQualityValidator", () => ({ hasValidRunQuality: () => true }));

import { mameResultPath, updateMameResultSelection } from "./resultSnapshot";
import type { JanusAutosaveResult, ReplicateResult } from "@/types/mame/models";

function replicate(plate: string): ReplicateResult {
  return {
    mutant_id: "M1",
    selected_plate: plate,
    selection_reason: "",
    failed: false,
    plate_keys: [],
    plate_verdicts: {},
    is_fallback: false,
    fallback_reason: null,
  };
}

function stored(): { saved_at: string; input_identity: string; result: Record<string, unknown> } {
  return JSON.parse(files.get(mameResultPath("/proj")) ?? "{}");
}

describe("updateMameResultSelection", () => {
  beforeEach(() => {
    files.clear();
    files.set(
      mameResultPath("/proj"),
      JSON.stringify({
        schema: 1,
        saved_at: "2026-10-20T00:00:00.000Z",
        kuma_version: "x",
        input_identity: "id-1",
        result: { replicates: [replicate("NB07")], summary: { total: 1 }, janus_autosave: null },
      }),
    );
  });

  it("replaces the replicates and keeps everything else in the file", async () => {
    const picks = { status: "saved" } as JanusAutosaveResult;

    await updateMameResultSelection("/proj", [replicate("NB08")], picks);

    const after = stored();
    expect(after.result.replicates).toEqual([replicate("NB08")]);
    expect(after.result.janus_autosave).toEqual(picks);
    expect(after.result.summary).toEqual({ total: 1 });
    expect([after.saved_at, after.input_identity]).toEqual(["2026-10-20T00:00:00.000Z", "id-1"]);
  });

  it("writes nothing for a scratch project or when no result file exists", async () => {
    await updateMameResultSelection(null, [replicate("NB08")], null);
    files.clear();
    await updateMameResultSelection("/proj", [replicate("NB08")], null);

    expect(files.size).toBe(0);
  });
});
