import { describe, expect, it } from "vitest";
import { buildKuroSnapshot, type KuroSnapshotState } from "./kuroSnapshot";

const baseState: KuroSnapshotState = {
  fastaPath: "/project/input.gb",
  selectedGene: "42",
  organism: "ecoli",
  mutationText: "A1V",
  mutationInputMode: "evolvepro",
  evolveproCsvPath: "/project/evolvepro.csv",
  evolveproMode: "pipeline",
  evolveproVariantColumn: "variant",
  evolveproScoreColumn: "score",
  evolveproScoreOrder: "asc",
  evolveproSheetName: "Sheet1",
  uniprotAccession: "P42212",
  domains: [],
  disabledDomains: [],
  positionDiversityEnabled: true,
  maxPerPosition: 2,
  domainDiversityEnabled: true,
  domainStrategy: "equal",
  domainOverlapPolicy: "largest",
  linkerHandling: "exclude",
  domainQuotaMin: 3,
  paretoDiversityEnabled: true,
  entropyWeightEnabled: true,
  entropyWeight: 0.4,
  paretoPoolMultiplier: 2,
  distanceMode: "3d",
  structuralDiversityEnabled: false,
  structuralKappa: 0.3,
  evolveproRound: 2,
  roundSize: 96,
  autoRedesignOnLoad: false,
  saveCache: false,
  selectedPolymerase: "Benchling",
  codonStrategy: "optimal",
  maxPrimers: 48,
  tmFwdTarget: 62,
  tmRevTarget: 58,
  tmOverlapTarget: 42,
  gcMin: 40,
  gcMax: 60,
  primerLenEnabled: true,
  fwdLenMin: 18,
  fwdLenMax: 34,
  revLenMin: 19,
  revLenMax: 28,
  fillOnFailure: true,
  overlapMode: "full",
  designResults: [],
  successCount: 0,
  totalCount: 0,
  failedMutations: [],
  plateMappings: [],
  dedupInfo: {},
  manuallySwapped: {},
  customCandidates: {},
  rescuedMutationDetails: [],
};

describe("buildKuroSnapshot", () => {
  it("serializes autosave inputs needed to restore EVOLVEpro mode with column overrides", () => {
    const snapshot = buildKuroSnapshot(baseState);

    expect(snapshot.input).toMatchObject({
      sequence_path: "/project/input.gb",
      selected_cds: "42",
      mutation_input_mode: "evolvepro",
      evolvepro_mode: "pipeline",
      evolvepro_csv_path: "/project/evolvepro.csv",
      evolvepro_variant_column: "variant",
      evolvepro_score_column: "score",
      evolvepro_score_order: "asc",
      evolvepro_sheet_name: "Sheet1",
      uniprot_accession: "P42212",
      organism: "ecoli",
    });
  });

  it("serializes parameters and diversity settings that hydration reapplies", () => {
    const snapshot = buildKuroSnapshot(baseState);

    expect(snapshot.parameters).toMatchObject({
      codon_strategy: "optimal",
      overlap_mode: "full",
    });
    expect(snapshot.diversity).toMatchObject({
      domain_strategy: "equal",
      domain_overlap_policy: "largest",
      linker_handling: "exclude",
      domain_quota_min: 3,
      distance_mode: "3d",
      auto_redesign_on_load: false,
      save_cache: false,
    });
  });

  it("serializes structural diversity settings", () => {
    const snapshot = buildKuroSnapshot(baseState);
    expect(snapshot.diversity).toMatchObject({
      structural_diversity_enabled: false,
      structural_kappa: 0.3,
    });
  });

  it("serializes structural diversity enabled=true with custom kappa", () => {
    const snapshot = buildKuroSnapshot({
      ...baseState,
      structuralDiversityEnabled: true,
      structuralKappa: 0.7,
    });
    expect(snapshot.diversity).toMatchObject({
      structural_diversity_enabled: true,
      structural_kappa: 0.7,
    });
  });
});
