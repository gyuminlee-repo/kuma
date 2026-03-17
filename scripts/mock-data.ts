/**
 * Mock state data for each capture screen.
 * Matches AppState schema in src/store/appStore.ts
 */

import type {
  SequenceInfo,
  SdmPrimerResult,
  PlateMapping,
} from "../src/types/models";

// --- Shared mock data ---

const mockSeqInfo: SequenceInfo = {
  header: "pSHCE-dmpR_20160502",
  seq_length: 4532,
  genes: [
    { gene: "dmpR", product: "phenol-responsive transcriptional activator", cds_start: 1790, cds_end: 3730, aa_length: 647 },
  ],
};

function makePrimer(mutation: string, aaPos: number, codonPos: number): SdmPrimerResult {
  return {
    mutation,
    aa_position: aaPos,
    codon_pos: codonPos,
    forward_seq: "GCATCGAAGCTGCAGCGATCAAGCTTGCAGCGATCAAGCT",
    reverse_seq: "TAGCTTGATCGCTGCAGCTTCGATGC",
    fwd_len: 40,
    rev_len: 26,
    overlap_len: 20,
    overlap_seq: "GCATCGAAGCTGCAGCGATC",
    candidate_count: 3,
    candidate_fwd_count: 3,
    candidate_rev_count: 2,
    tm_no_fwd: 62.3,
    tm_no_rev: 58.1,
    tm_overlap: 42.5,
    tm_condition_met: true,
    tolerance_used: 0,
    tolerance_fwd: 0,
    tolerance_rev: 0,
    has_offtarget: false,
    penalty: 0.8,
    gc_fwd: 52.5,
    gc_rev: 46.2,
    wt_codon: "CAG",
    mt_codon: "GCG",
    warnings: [],
    hairpin_tm_fwd: 25.0,
    hairpin_tm_rev: 20.0,
    homodimer_tm_fwd: 22.0,
    homodimer_tm_rev: 18.0,
    hairpin_dg_fwd: -1.2,
    hairpin_dg_rev: -0.8,
    homodimer_dg_fwd: -1.0,
    homodimer_dg_rev: -0.6,
  };
}

const mockDesignResults: SdmPrimerResult[] = [
  makePrimer("Q232A", 232, 1888),
  makePrimer("Y233A", 233, 1891),
  makePrimer("E335A", 335, 2197),
  makePrimer("E167A", 167, 1693),
  makePrimer("K200A", 200, 1792),
  makePrimer("F203A", 203, 1801),
];

const mockPlateMappings: PlateMapping[] = mockDesignResults.flatMap((r, i) => [
  {
    well: `A${i + 1}`,
    primer_name: `${r.mutation}_Fwd`,
    sequence: r.forward_seq,
    primer_type: "forward" as const,
    mutation: r.mutation,
  },
  {
    well: `B${i + 1}`,
    primer_name: `${r.mutation}_Rev`,
    sequence: r.reverse_seq,
    primer_type: "reverse" as const,
    mutation: r.mutation,
  },
]);

// --- Screen states ---

export interface ScreenState {
  /** Screenshot filename without extension (e.g. "01-initial") */
  name: string;
  /** Human-readable caption for USER-GUIDE */
  caption: string;
  /** Partial AppState to inject via window.__store.setState() */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  state: Record<string, any>;
  /** Optional action to run after setState (e.g. click a menu) */
  action?: string;
}

export const screenStates: ScreenState[] = [
  {
    name: "01-initial",
    caption: "초기 실행 화면 — 파일을 로드하기 전 상태",
    state: {
      fastaPath: "",
      seqInfo: null,
      mutationText: "",
      parsedMutations: [],
      parseErrors: [],
      designResults: [],
      plateMappings: [],
      statusMessage: "Ready",
      progress: 0,
      isDesigning: false,
    },
  },
  {
    name: "02-file-loaded",
    caption: "GenBank 파일 로드 완료 — 유전자 정보가 자동 표시된다",
    state: {
      fastaPath: "/path/to/pSHCE-dmpR.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1790",
      mutationText: "",
      parsedMutations: [],
      designResults: [],
      plateMappings: [],
      statusMessage: "Loaded: pSHCE-dmpR_20160502 (4532 bp) | 1 gene(s) | Target: dmpR",
      progress: 0,
      isDesigning: false,
    },
  },
  {
    name: "03-mutations-entered",
    caption: "변이 목록 입력 및 유전자 선택 완료",
    state: {
      fastaPath: "/path/to/pSHCE-dmpR.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1790",
      mutationText: "Q232A\nY233A\nE335A\nE167A\nK200A\nF203A",
      parsedMutations: [
        { raw: "Q232A", wt_aa: "Q", position: 232, mt_aa: "A" },
        { raw: "Y233A", wt_aa: "Y", position: 233, mt_aa: "A" },
        { raw: "E335A", wt_aa: "E", position: 335, mt_aa: "A" },
        { raw: "E167A", wt_aa: "E", position: 167, mt_aa: "A" },
        { raw: "K200A", wt_aa: "K", position: 200, mt_aa: "A" },
        { raw: "F203A", wt_aa: "F", position: 203, mt_aa: "A" },
      ],
      parseErrors: [],
      designResults: [],
      plateMappings: [],
      statusMessage: "Ready",
      isDesigning: false,
    },
  },
  {
    name: "04-design-complete",
    caption: "프라이머 설계 완료 — 결과 테이블이 표시된다",
    state: {
      fastaPath: "/path/to/pSHCE-dmpR.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1790",
      mutationText: "Q232A\nY233A\nE335A\nE167A\nK200A\nF203A",
      designResults: mockDesignResults,
      successCount: 6,
      totalCount: 6,
      failedMutations: [],
      plateMappings: mockPlateMappings,
      dedupInfo: {},
      statusMessage: "6/6 designed | Tm condition: 6/6",
      progress: 100,
      isDesigning: false,
      manuallySwapped: {},
      customCandidates: {},
      tableSorting: [],
    },
  },
  {
    name: "05-plate-map",
    caption: "Plate Map — 96-well 형식으로 프라이머 배치가 표시된다",
    state: {
      fastaPath: "/path/to/pSHCE-dmpR.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1790",
      mutationText: "Q232A\nY233A\nE335A\nE167A\nK200A\nF203A",
      designResults: mockDesignResults,
      successCount: 6,
      totalCount: 6,
      failedMutations: [],
      plateMappings: mockPlateMappings,
      dedupInfo: { "TAGCTTGATCGCTGCAGCTTCGATGC": ["Q232A", "Y233A"] },
      statusMessage: "6/6 designed | Tm condition: 6/6",
      progress: 100,
      isDesigning: false,
    },
  },
];
