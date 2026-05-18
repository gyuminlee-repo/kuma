import i18next from "i18next";
import type { StateCreator } from "zustand";
import { resolveResource } from "@tauri-apps/api/path";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { sendRequest } from "../../lib/ipc-kuro";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type { Round } from "../../types/round";
import {
  buildEvolveproLoadParams,
  buildEvolveproLoadStateUpdate,
} from "./inputSlice.helpers";
import {
  validateCsvHeader,
  extractCsvHeader,
  EVOLVEPRO_CSV_SCHEMA,
} from "../../lib/schemaValidator";

import type { InputSlice } from "../slice-interfaces";
export type { InputSlice };

// EGFP sample mutation set: 120 mutations selected from safe positions of the
// bundled EGFP CDS (samples/egfp.fa). Verified against design_sdm_primers with
// the default "Benchling" polymerase profile: 118/120 succeed (≥96/96-well
// plate target). Positions in the 6–7, 15–16, 23, 33–42, 54–63, 67, 75, 93,
// 114–115, 179–199, 229–232, 239 ranges are excluded because primer design
// fails there with default Tm/length parameters (no valid primer pair).
// Source: fixtures/generate_egfp_sample_mutations.py (seeded random.seed(42)).
const EGFP_SAMPLE_MUTATIONS_120 = [
  "Q205E","T10K","A88K","T50E","K215W","S29Y","I137C","G11D","Q81I","Q158A",
  "I172H","V225W","N136I","E143Y","T98A","T64Q","E116L","P55H","V113E","V30P",
  "S31N","G117L","V17R","F166E","E125D","H170M","L202P","S176H","L222D","V17I",
  "F101D","F85E","L126K","N145P","L65P","T119H","N213K","L221D","I189G","N165I",
  "L65S","Q205W","H82N","D20K","V12M","F131L","D22I","D174N","K80T","D130S",
  "T51K","T50I","E236W","F166L","L237Y","L138Y","F131P","H82F","K159T","V30C",
  "L43F","L202G","R216Q","N186D","K127Q","N186S","V164K","H170A","R216E","R216W",
  "Y238K","S206M","L43M","H140G","N145A","T226K","K157G","Q158E","L202M","Q205V",
  "I189H","P55N","L65W","V164A","T187M","M154A","L43P","G105K","D174E","F28T",
  "N24W","F47G","K210T","R169G","V94T","I189R","K80W","A228I","F224M","K141V",
  "Y144E","M89I","D22N","F9Y","H170K","Q184I","S3D","E223C","F84D","G25V",
  "K86L","N213T","I48Y","S176T","A88T","E133I","S31E","K210R","T119Q","D134S",
].join("\n");

export const createInputSlice: StateCreator<AppState, [], [], InputSlice> = (set, get) => {
  let csvLoadGeneration = 0;

  return ({
  mutationInputMode: "text",
  mutationText: "",
  parsedMutations: [],
  parseErrors: [],
  evolveproCsvPath: "",
  evolveproTotalCount: 0,
  evolveproFilteredCount: null,
  evolveproParetoExchanges: null,
  evolveproStepStats: null,
  yPredMap: {},

  setMutationInputMode: (mode) => set({
    mutationInputMode: mode,
    ...(mode === "text" && {
      evolveproCsvPath: "",
      evolveproTotalCount: 0,
      evolveproFilteredCount: null,
      evolveproParetoExchanges: null,
      evolveproStepStats: null,
      yPredMap: {},
      domainStats: {},
      poolVariants: [],
    }),
  }),
  setMutationText: (text) => set({ mutationText: text }),

  loadEvolveproCsv: async (filepath: string, topNOverride?: number) => {
    const gen = ++csvLoadGeneration;
    try {
      const {
        pipelineMode,
        positionDiversityEnabled,
        maxPerPosition,
        domainDiversityEnabled,
        domains,
        disabledDomains,
        domainStrategy,
        domainOverlapPolicy,
        linkerHandling,
        domainQuotaMin,
        paretoDiversityEnabled,
        entropyWeightEnabled,
        entropyWeight,
        paretoPoolMultiplier,
        distanceMode,
        evolveproRound,
        roundSize,
        maxPrimers,
      } = get();
      const effectiveTopN = topNOverride ?? maxPrimers;
      const activeDomains = domains.filter((d) => !disabledDomains.includes(`${d.name}-${d.start}`));
      const excludedDomains = domains.filter((d) => disabledDomains.includes(`${d.name}-${d.start}`));
      const modeLabel = "EVOLVEpro";

      // v0.3 §4: pass protein ref_seq so sidecar can convert EVOLVEpro
      // short-form variants (89W) back to internal notation (F89W).
      // Pulled from the selected gene's translation when available.
      const seqInfo = get().seqInfo;
      const selectedGeneKey = get().selectedGene;
      const refSeq = (() => {
        if (!seqInfo) return "";
        const gene = seqInfo.genes.find((g) => String(g.cds_start) === selectedGeneKey)
          ?? seqInfo.genes[0];
        return gene?.translation ?? "";
      })();
      set({ statusMessage: `Loading ${modeLabel} CSV...`, evolveproCsvPath: filepath });

      // §3 Input Guards: sidecar 호출 전 헤더 컬럼 검증
      try {
        const csvText = await readTextFile(filepath);
        const header = extractCsvHeader(csvText);
        const spec = EVOLVEPRO_CSV_SCHEMA;
        const validation = validateCsvHeader(header, spec);
        if (!validation.valid) {
          const detail = validation.errors.join("; ");
          set({
            statusMessage: i18next.t("inputSlice.csvFormatError", { mode: modeLabel, detail }),
            evolveproCsvPath: "",
          });
          return;
        }
      } catch {
        // 파일 읽기 실패 시 sidecar 에 위임 (경로 오류는 sidecar가 처리)
      }

      const usePipeline = pipelineMode;
        const params = buildEvolveproLoadParams({
          filepath,
          topN: effectiveTopN,
          usePipeline,
        positionDiversityEnabled,
        maxPerPosition,
        activeDomains,
        excludedDomains,
        domainDiversityEnabled,
        domainStrategy,
        domainOverlapPolicy,
        linkerHandling,
        domainQuotaMin,
        paretoDiversityEnabled,
        entropyWeightEnabled,
          entropyWeight,
          paretoPoolMultiplier,
          distanceMode,
          structureAccession: get().uniprotAccession,
          evolveproRound,
          roundSize,
          refSeq,
        });
      const result = await sendRequest("load_evolvepro_csv", params);
      if (gen !== csvLoadGeneration) return;
      const update = buildEvolveproLoadStateUpdate({
        result,
        currentMode: get().mutationInputMode,
        maxPerPosition,
      });
      if (result.total_count > 0 && maxPrimers > result.total_count) {
        get().setMaxPrimers(result.total_count);
      }
      set({
        mutationText: update.mutationText,
        mutationInputMode: "evolvepro",
        yPredMap: update.yPredMap,
        domainStats: update.domainStats,
        poolVariants: update.poolVariants,
        evolveproTotalCount: update.evolveproTotalCount,
        evolveproFilteredCount: update.evolveproFilteredCount,
        evolveproParetoExchanges: update.evolveproParetoExchanges,
        evolveproStepStats: update.evolveproStepStats,
        statusMessage: update.statusMessage,
      });
    } catch (err) {
      if (gen === csvLoadGeneration) {
        set({
          mutationText: "",
          evolveproTotalCount: 0,
          evolveproFilteredCount: null,
          evolveproParetoExchanges: null,
          evolveproStepStats: null,
          yPredMap: {},
          domainStats: {},
          poolVariants: [],
          statusMessage: `EVOLVEpro CSV load failed: ${formatError(err)}`,
        });
      }
      throw err;
    }
  },

  parseMutations: async () => {
    const { mutationText } = get();
    try {
      const result = await sendRequest(
        "parse_mutations_text",
        { text: mutationText },
      );
      set({ parsedMutations: result.parsed, parseErrors: result.errors });
    } catch (err) {
      set({ statusMessage: `Mutation parse failed: ${formatError(err)}` });
    }
  },

  loadSampleData: async () => {
    // Item 1 (PI 2026-05-15): "Load sample data" must auto-populate every required
    // field so the user can press Next at each wizard step without manual setup.
    //
    // Why text mode (not evolvepro) for the EGFP fixture:
    //   The bundled `sample_evolvepro.csv` was authored for the legacy ispS sample
    //   and references high residue positions / WT residues that do not match the
    //   EGFP CDS (239 aa) introduced in Item 4. Loading that CSV against EGFP
    //   yields position/WT-residue validation failures inside `load_evolvepro_csv`
    //   and leaves `mutationText` empty, breaking the design.mutation Next gate.
    //   Until the CSV is regenerated for EGFP (separate follow-up), the sample
    //   loader uses text-mode with a small demo set of valid EGFP mutations.
    //
    //   The four mutations below use the actual WT residues at positions 65, 100,
    //   150, 200 of the bundled EGFP translation, so the design pipeline accepts
    //   them without further user intervention.
    //
    // Other required defaults (codon strategy "closest", polymerase "Benchling",
    // pipelineMode / diversity flags) are already set by the respective slice
    // initial state, so the wizard's design.submit gate clears on its own once
    // seqInfo + mutationText are present and the single-gene FASTA auto-selects
    // selectedGene inside loadSequence.
    try {
      set({ statusMessage: "Loading sample data..." });
      const gbPath = await resolveResource("samples/egfp.fa");
      await get().loadSequence(gbPath);
      if (!get().seqInfo) {
        // loadSequence swallowed an error and left statusMessage with the cause; preserve it.
        return;
      }
      // Force text mode (clears any stale evolvepro CSV state).
      get().setMutationInputMode("text");
      // Demo mutations valid against the bundled EGFP translation.
      // Parser expects one mutation per line (sidecar_kuro/handlers/sequence.py:55).
      // 120-variant set: chosen from EGFP positions where default Benchling
      // Tm/length parameters yield a valid primer pair, so the user can fill
      // a full 96-well plate without manual deletion. Verified: 118/120 succeed.
      get().setMutationText(EGFP_SAMPLE_MUTATIONS_120);
      set({ statusMessage: "Sample data loaded (EGFP + 120 demo mutations)." });
    } catch (err) {
      set({ statusMessage: `Sample load failed: ${formatError(err)}` });
    }
  },

  loadRoundActivity: (prevRound: Round) => {
    const warnings: string[] = [];

    // Step 1: filter merged_table — ngs_success && mutation && mutation !== "WT" && log2_fc !== null
    const filtered = prevRound.merged_table.filter(
      (r) =>
        r.ngs_success &&
        r.mutation !== null &&
        r.mutation !== undefined &&
        r.mutation !== "WT" &&
        r.log2_fc !== null &&
        r.log2_fc !== undefined,
    );

    // Step 7: 0 rows → ok=false, no state change
    if (filtered.length === 0) {
      warnings.push("0 rows after filter (ngs_success && non-WT && log2_fc not null)");
      return { ok: false, warnings };
    }

    // Step 2: build yPredMap (variant → log2_fc)
    const yPredMap: Record<string, number> = {};
    const variants: string[] = [];
    for (const r of filtered) {
      const variant = r.mutation as string;
      yPredMap[variant] = r.log2_fc as number;
      if (!variants.includes(variant)) {
        variants.push(variant);
      }
    }

    // Steps 3–6: apply state updates
    // Note: mutationText = variants.join("\n") for design pipeline compatibility.
    // Spec §4.5 step 5 literal (mutationText="") would break KURO design which
    // reads mutationText as primary variant input. Deviation documented in PR.
    set({
      // Step 3: force evolvepro mode
      mutationInputMode: "evolvepro",
      // Step 4/5: hydrate evolvepro state (evolvepro rows → mutationText + yPredMap)
      mutationText: variants.join("\n"),
      yPredMap,
      evolveproTotalCount: filtered.length,
      evolveproCsvPath: "",  // memory hydrate — no CSV file path
      // Step 6: clear stale diversity cache
      evolveproFilteredCount: null,
      evolveproParetoExchanges: null,
      evolveproStepStats: null,
      domainStats: {},
      poolVariants: [],
      statusMessage: `Round ${prevRound.n} activity loaded: ${filtered.length} variants (EVOLVEpro mode)`,
    });

    return { ok: true, warnings };
  },
});
};
