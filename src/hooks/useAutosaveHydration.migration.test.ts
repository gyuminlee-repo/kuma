/**
 * useAutosaveHydration.migration.test.ts
 *
 * Verifies applyKuroSnapshot migrates legacy pre-merge autosaves
 * (evolvepro_mode: "others" + others_* column-mapping keys) onto the
 * unified evolveproMode: "topN" | "pipeline" store shape.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AutosaveSnapshot } from "@/lib/autosave";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn().mockRejectedValue(new Error("no sidecar in unit test")),
  setProgressHandler: vi.fn(),
}));

import { useAppStore } from "@/store/appStore";
import { applyKuroSnapshot } from "./useAutosaveHydration";

function legacySnapshot(): AutosaveSnapshot {
  return {
    schema: 1,
    saved_at: new Date().toISOString(),
    kuma_version: "0.0.0-test",
    input: {
      sequence_path: null,
      selected_cds: null,
      mutation_text: "",
      mutation_input_mode: "evolvepro",
      evolvepro_mode: "others",
      evolvepro_csv_path: null,
      evolvepro_variant_column: null,
      evolvepro_score_column: null,
      evolvepro_score_order: "desc",
      evolvepro_sheet_name: null,
      others_source_path: "/project/others.xlsx",
      others_variant_column: "mutation",
      others_score_column: "fitness",
      others_score_order: "asc",
      others_sheet_name: "Round 2",
      uniprot_accession: null,
      organism: "ecoli",
    },
    parameters: {},
    diversity: {},
  };
}

describe("applyKuroSnapshot: legacy others-mode migration", () => {
  beforeEach(() => {
    useAppStore.setState({
      evolveproMode: "topN",
      evolveproCsvPath: "",
      evolveproVariantColumn: null,
      evolveproScoreColumn: null,
      evolveproScoreOrder: "desc",
      evolveproSheetName: null,
    });
  });

  it("coerces evolvepro_mode 'others' to 'pipeline'", async () => {
    await applyKuroSnapshot(legacySnapshot());
    expect(useAppStore.getState().evolveproMode).toBe("pipeline");
  });

  it("migrates others_source_path onto evolveproCsvPath when evolvepro_csv_path is absent", async () => {
    await applyKuroSnapshot(legacySnapshot());
    expect(useAppStore.getState().evolveproCsvPath).toBe("/project/others.xlsx");
  });

  it("migrates others_* column mapping onto evolvepro* fields", async () => {
    await applyKuroSnapshot(legacySnapshot());
    const state = useAppStore.getState();
    expect(state.evolveproVariantColumn).toBe("mutation");
    expect(state.evolveproScoreColumn).toBe("fitness");
    expect(state.evolveproScoreOrder).toBe("asc");
    expect(state.evolveproSheetName).toBe("Round 2");
  });

  it("prefers evolvepro_csv_path over legacy others_source_path when both are present", async () => {
    const snapshot = legacySnapshot();
    (snapshot.input as Record<string, unknown>).evolvepro_csv_path = "/project/evolvepro.csv";
    (snapshot.input as Record<string, unknown>).evolvepro_mode = "pipeline";
    await applyKuroSnapshot(snapshot);
    const state = useAppStore.getState();
    expect(state.evolveproCsvPath).toBe("/project/evolvepro.csv");
    expect(state.evolveproMode).toBe("pipeline");
  });
});
