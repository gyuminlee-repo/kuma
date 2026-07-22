import type { StateCreator } from "zustand";
import i18next from "i18next";
import { sendRequest } from "../../lib/ipc-kuro";
import { buildKuroResultResetPatch } from "../../lib/kuroResultReset";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import { useMameAppStore } from "../mame/mameAppStore";

import type { SequenceSlice } from "../slice-interfaces";
export type { SequenceSlice };

// Only domain/pareto/structural diversity actually consume uniprotAccession
// (reference-domain fetch, pareto 3D distance, structural diversity, 3D view).
// Top-N-only workflows never touch it, so BLAST-backed auto-search (slow, no
// known accession) is gated on at least one of these being enabled.
function diversityConsumersEnabled(state: AppState): boolean {
  return state.domainDiversityEnabled || state.paretoDiversityEnabled || state.structuralDiversityEnabled;
}

/**
 * 현재 선택된 CDS의 translation. 템플릿 동일성 판정에 쓴다.
 * 같은 경로라도 파일이 편집돼 대상 단백질 서열이 바뀌면 잔기 번호 기준이 달라진다.
 */
function targetTranslation(seqInfo: AppState["seqInfo"], selectedGene: string): string | null {
  if (!seqInfo) return null;
  const gene = seqInfo.genes.find((g) => String(g.cds_start) === selectedGene);
  return gene?.translation ?? null;
}

/**
 * 결과물을 비웠으면 상태 메시지에 재설계 안내를 덧붙인다.
 * 기존 영어 리터럴 메시지는 그대로 두고 덧붙이는 문장만 i18n 키로 처리한다.
 */
function withClearedNotice(message: string, cleared: boolean): string {
  if (!cleared) return message;
  return `${message} | ${i18next.t("sequenceSlice.resultsClearedOnTemplateChange")}`;
}

const UNIPROT_AUTO_SEARCH_SKIPPED_MESSAGE =
  "UniProt auto-search skipped (domain/pareto/structural diversity disabled), "
  + "use the Step 1 search button if you need it later.";

export const createSequenceSlice: StateCreator<AppState, [], [], SequenceSlice> = (set, get) => ({
  fastaPath: "",
  seqInfo: null,
  selectedGene: "",
  organism: "ecoli",

  loadSequence: async (filepath: string) => {
    // 판정에 쓸 직전 상태는 set()이 덮어쓰기 전에 잡아 둔다.
    const prev = get();
    const prevFastaPath = prev.fastaPath;
    const prevSeqInfo = prev.seqInfo;
    const prevTranslation = targetTranslation(prevSeqInfo, prev.selectedGene);
    const prevHadResults = prev.designResults.length > 0;

    try {
      set({ statusMessage: "Loading sequence file..." });
      const info = await sendRequest("load_fasta", { filepath });

      let bestGene = info.genes.length > 0 ? info.genes[0] : null;
      if (info.genes.length > 1) {
        for (const g of info.genes) {
          if (!bestGene || g.aa_length > bestGene.aa_length) {
            bestGene = g;
          }
        }
      }

      const selectedKey = bestGene ? String(bestGene.cds_start) : "";

      // 템플릿이 바뀌면 designResults의 잔기 번호(F385Y 등)는 선택된 CDS 기준이라
      // 의미를 잃는다. 경로가 다르거나, 같은 경로라도 대상 translation이 달라졌으면
      // 파생 결과물을 비운다. 직전 결과물이 없으면 비울 것도 없으므로 건너뛴다.
      // mutationText는 사용자가 직접 입력한 원본이라 보존한다(파생 상태만 무효화).
      const templateChanged =
        filepath !== prevFastaPath || prevTranslation !== (bestGene?.translation ?? null);
      const invalidateResults = prevSeqInfo !== null && prevHadResults && templateChanged;

      const loadedMessage =
        `Loaded: ${info.header} (${info.seq_length} bp) | ${info.genes.length} gene(s) `
        + `| Target: ${bestGene?.gene ?? "none"}`;

      set({
        ...(invalidateResults ? buildKuroResultResetPatch() : {}),
        fastaPath: filepath,
        seqInfo: info,
        selectedGene: selectedKey,
        domains: [],
        refDomains: [],
        refDomainHash: "",
        refDomainsLoading: false,
        disabledDomains: [],
        domainStats: {},
        domainLoading: false,
        poolVariants: [],
        benchmarkResults: null,
        showBenchmark: false,
        uniprotCandidates: [],
        uniprotSearching: false,
        uniprotAccession: "",
        structureAccession: "",
        structureLoaded: false,
        structureLoading: false,
        statusMessage: withClearedNotice(loadedMessage, invalidateResults),
      });

      // Dual-write to MAME shared store so BarcodeSetupPanel can auto-fill.
      try {
        useMameAppStore.getState().setSharedFastaPath(filepath);
      } catch {
        // Defensive: never let the cross-store hand-off break sequence load.
      }

      // Auto-trigger UniProt search if gene has db_xref or translation.
      // Known-accession lookups are cheap (backend skips BLAST at >=95%
      // identity), so those always run. BLAST-only lookups (no known
      // accession) are gated on an actual accession consumer being enabled.
      if (bestGene) {
        const knownAcc = bestGene.uniprot_accession ?? "";
        const translation = bestGene.translation ?? "";
        const organism = bestGene.organism ?? "";
        if (knownAcc) {
          get().searchUniprot(bestGene.gene, organism, translation, knownAcc);
        } else if (translation) {
          if (diversityConsumersEnabled(get())) {
            get().searchUniprot(bestGene.gene, organism, translation, knownAcc);
          } else {
            // 이 분기는 위 set()의 statusMessage를 동기적으로 대체한다.
            // 결과물을 비웠으면 그 공지가 렌더 전에 사라지지 않게 함께 실어 보낸다.
            set({ statusMessage: withClearedNotice(UNIPROT_AUTO_SEARCH_SKIPPED_MESSAGE, invalidateResults) });
          }
        }
      }
    } catch (err) {
      set({ statusMessage: `Sequence file load failed: ${formatError(err)}` });
    }
  },

  setSelectedGene: (gene: string) => {
    // 대상 CDS가 바뀌면 잔기 번호 기준이 바뀌므로 loadSequence와 같은 이유로
    // 파생 결과물을 비운다. 같은 gene 재선택이거나 결과물이 없으면 건너뛴다.
    // mutationText는 사용자 원본이라 여기서도 보존한다.
    const prevState = get();
    const invalidateResults = gene !== prevState.selectedGene && prevState.designResults.length > 0;

    set({
      ...(invalidateResults ? buildKuroResultResetPatch() : {}),
      ...(invalidateResults
        ? { statusMessage: i18next.t("sequenceSlice.resultsClearedOnTemplateChange") }
        : {}),
      // 아래 uniprot 블록이 statusMessage를 동기적으로 덮을 수 있어
      // skip 분기에서 같은 공지를 다시 실어 보낸다(withClearedNotice).
      selectedGene: gene,
      domains: [],
      refDomains: [],
      refDomainHash: "",
      refDomainsLoading: false,
      disabledDomains: [],
      domainStats: {},
      domainLoading: false,
      poolVariants: [],
      benchmarkResults: null,
      showBenchmark: false,
      uniprotCandidates: [],
      uniprotSearching: false,
      uniprotAccession: "",
      structureAccession: "",
      structureLoaded: false,
      structureLoading: false,
    });
    const { seqInfo, organism } = get();
    const g = seqInfo?.genes.find((g) => String(g.cds_start) === gene);
    if (g) {
      const knownAcc = g.uniprot_accession ?? "";
      const translation = g.translation ?? "";
      if (knownAcc) {
        get().searchUniprot(g.gene, g.organism ?? organism, translation, knownAcc);
      } else if (translation) {
        if (diversityConsumersEnabled(get())) {
          get().searchUniprot(g.gene, g.organism ?? organism, translation, knownAcc);
        } else {
          set({ statusMessage: withClearedNotice(UNIPROT_AUTO_SEARCH_SKIPPED_MESSAGE, invalidateResults) });
        }
      }
    }
  },

  setOrganism: (organism: string) => set({ organism }),
});
