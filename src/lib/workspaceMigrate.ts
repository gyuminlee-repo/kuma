/**
 * workspaceMigrate.ts — §14 Schema dry-run migration helpers
 *
 * Defines a typed migration registry and a `migrateWorkspace` runner.
 * Each migration key is `"<from>-><to>"` where versions are the discriminator
 * values (numeric `version` for V1/V2, string `schema_version` for V3+).
 *
 * Current registry:
 *   "1->0.3"  : WorkspaceV1 → WorkspaceV3 structure
 *   "2->0.3"  : WorkspaceV2 → WorkspaceV3 structure
 *
 * If no path exists for a given (from, to) pair, `migrateWorkspace` throws.
 */

import i18next from "i18next";

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- intentional: migration fn operates on unknown JSON blobs
export type MigrationFn = (workspace: Record<string, unknown>) => Record<string, unknown>;

export const MIGRATIONS: Record<string, MigrationFn> = {
  /**
   * WorkspaceV1 (version: 1, flat structure) → WorkspaceV3 (schema_version: "0.3").
   * Lifts all flat fields into inputs/settings/results/ui sub-objects and adds
   * empty rounds array + null active_round_id.
   */
  "1->0.3": (ws) => {
    return {
      schema_version: "0.3",
      rounds: [],
      active_round_id: null,
      inputs: {
        fastaPath: ws.fastaPath ?? "",
        mutationInputMode: ws.mutationInputMode === "text" ? "evolvepro" : (ws.mutationInputMode ?? "evolvepro"),
        mutationText: ws.mutationText ?? "",
        evolveproCsvPath: ws.evolveproCsvPath ?? "",
        selectedGene: ws.selectedGene ?? "",
      },
      settings: {
        selectedPolymerase: undefined,
        codonStrategy: ws.codonStrategy ?? "closest",
        maxPrimers: ws.maxPrimers ?? 95,
        tmFwdTarget: ws.tmFwdTarget ?? 62,
        tmRevTarget: ws.tmRevTarget ?? 58,
        tmOverlapTarget: ws.tmOverlapTarget ?? 42,
        gcMin: ws.gcMin ?? 40,
        gcMax: ws.gcMax ?? 60,
        primerLenEnabled: ws.primerLenEnabled ?? true,
        fwdLenMin: ws.fwdLenMin,
        fwdLenMax: ws.fwdLenMax,
        revLenMin: ws.revLenMin,
        revLenMax: ws.revLenMax,
        fillOnFailure: ws.fillOnFailure ?? true,
        tmTolerance: ws.tmTolerance,
        uniprotAccession: ws.uniprotAccession,
        domains: ws.domains,
        domainDiversityEnabled: ws.domainDiversityEnabled,
        domainStrategy: ws.domainStrategy,
        domainOverlapPolicy: "first",
        linkerHandling: "include",
        domainQuotaMin: 1,
        paretoDiversityEnabled: ws.paretoDiversityEnabled,
        structuralDiversityEnabled: false,
        structuralKappa: 0.3,
        disabledDomains: ws.disabledDomains,
        rescuedMutations: ws.rescuedMutations,
        entropyWeightEnabled: ws.entropyWeightEnabled,
        entropyWeight: ws.entropyWeight,
        paretoPoolMultiplier: 2.0,
        distanceMode: "auto",
        benchmarkTopPercentile: 10,
        benchmarkRandomTrials: 100,
        benchmarkRandomSeed: null,
        autoRedesignOnLoad: true,
        saveCache: true,
        organism: ws.organism,
        pipelineMode: ws.pipelineMode,
        positionDiversityEnabled: ws.positionDiversityEnabled,
        maxPerPosition: ws.maxPerPosition,
        overlapMode: undefined,
      },
      results: {
        designResults: ws.designResults ?? [],
        successCount: ws.successCount ?? 0,
        totalCount: ws.totalCount ?? 0,
        failedMutations: ws.failedMutations ?? [],
        plateMappings: ws.plateMappings ?? [],
        dedupInfo: ws.dedupInfo ?? {},
        manuallySwapped: ws.manuallySwapped ?? {},
        customCandidates: ws.customCandidates ?? {},
        rescuedMutationDetails: [],
      },
      ui: {
        tableSorting: ws.tableSorting ?? [],
      },
      cache: {
        evolveproTotalCount: ws.evolveproTotalCount,
        evolveproFilteredCount: ws.evolveproFilteredCount ?? null,
        evolveproParetoExchanges: ws.evolveproParetoExchanges ?? null,
        evolveproStepStats: ws.evolveproStepStats ?? null,
        benchmarkResults: null,
      },
    };
  },

  /**
   * WorkspaceV2 (version: 2, inputs/settings/results/ui structure) → WorkspaceV3.
   * Adds rounds: [], active_round_id: null, schema_version: "0.3".
   */
  "2->0.3": (ws) => {
    const { version: _version, ...rest } = ws;
    return {
      ...rest,
      schema_version: "0.3",
      rounds: (ws.rounds as unknown[]) ?? [],
      active_round_id: (ws.active_round_id as string | null) ?? null,
    };
  },
};

/**
 * Detect the current version string from a raw workspace JSON blob.
 * Returns "0.3" | "2" | "1" | "unknown".
 */
export function detectWorkspaceVersion(ws: Record<string, unknown>): string {
  if (ws.schema_version === "0.3") return "0.3";
  if (ws.version === 2) return "2";
  if (ws.version === 1) return "1";
  return "unknown";
}

/**
 * Apply migration(s) from `fromVer` to `toVer`.
 * Throws if no migration path is defined.
 */
export function migrateWorkspace(
  json: Record<string, unknown>,
  fromVer: string,
  toVer: string,
): Record<string, unknown> {
  if (fromVer === toVer) return json;
  const key = `${fromVer}->${toVer}`;
  const fn = MIGRATIONS[key];
  if (!fn) {
    throw new Error(
      i18next.t("workspaceMigrate.noMigrationPath", { from: fromVer, to: toVer }),
    );
  }
  return fn(json);
}
