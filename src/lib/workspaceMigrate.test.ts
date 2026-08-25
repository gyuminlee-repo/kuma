import { describe, expect, it } from "vitest";
import { migrateWorkspace } from "./workspaceMigrate";

describe("WorkspaceV1 migration", () => {
  it("preserves declared diversity and EVOLVEpro settings", () => {
    const migrated = migrateWorkspace({
      version: 1,
      fastaPath: "",
      mutationInputMode: "evolvepro",
      mutationText: "",
      evolveproCsvPath: "",
      selectedGene: "",
      codonStrategy: "closest",
      maxPrimers: 95,
      designResults: [],
      successCount: 0,
      totalCount: 0,
      failedMutations: [],
      plateMappings: [],
      dedupInfo: {},
      tableSorting: [],
      manuallySwapped: {},
      customCandidates: {},
      tmFwdTarget: 62,
      tmRevTarget: 58,
      tmOverlapTarget: 42,
      gcMin: 40,
      gcMax: 60,
      structuralDiversityEnabled: true,
      structuralKappa: 0.75,
      evolveproRound: 4,
      roundSize: 48,
      overlapMode: "full",
    }, "1", "0.3");

    expect(migrated.settings).toMatchObject({
      structuralDiversityEnabled: true,
      structuralKappa: 0.75,
      evolveproRound: 4,
      roundSize: 48,
      overlapMode: "full",
    });
  });
});
