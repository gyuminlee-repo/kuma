/**
 * Mock state data for each capture screen.
 * Based on real data: pTSN-PtIspS-idi(KanR)_corrected.dna + df_test.csv (95 EVOLVEpro variants)
 *
 * Primer data is stored separately in primer-data.json to keep this file manageable.
 */

import { createRequire } from "module";
import type {
  SequenceInfo,
  SdmPrimerResult,
  PlateMapping,
  FailedMutation,
} from "../src/types/models";

const require = createRequire(import.meta.url);
// eslint-disable-next-line @typescript-eslint/no-var-requires
const primerData = require("./primer-data.json") as SdmPrimerResult[];

// --- Real data from pTSN-PtIspS-idi(KanR)_corrected.gb ---

const mockSeqInfo: SequenceInfo = {
  header: "pTSN-PtIspS-idi(KanR)_corrected",
  seq_length: 6494,
  genes: [
    { gene: "IspS", product: "isoprene synthase", cds_start: 267, cds_end: 1950, aa_length: 561 },
    { gene: "idi", product: "isopentenyl-diphosphate delta-isomerase", cds_start: 2111, cds_end: 2660, aa_length: 183 },
    { gene: "aph(3')-Ia", product: "aminoglycoside phosphotransferase", cds_start: 3208, cds_end: 4024, aa_length: 272 },
    { gene: "lacIq", product: "lac repressor protein", cds_start: 5372, cds_end: 6455, aa_length: 361 },
  ],
};

// EVOLVEpro top-95 mutation text
const evolveMutationText = [
  "V100F","V299I","V550P","Y360F","V10L","E222D","V424W","R261W","N63S","Q426D",
  "Q426E","R560S","V108L","H448L","Q213T","R124W","E228D","H448M","S220F","R214P",
  "E189D","T397V","R254I","E559D","Q132W","T478L","T267H","L215F","H270N","T552F",
  "R560P","I551L","R225K","R477H","Q525N","T478F","H209C","V547I","V218L","R477A",
  "R225Q","D401E","I442V","D339E","V550C","K53N","V108F","H448F","V108I","L556W",
  "V5F","R261N","T487N","S112M","N63F","H448V","T552L","T478C","S11E","V286I",
  "R560G","Q426N","I44V","I428V","R560A","V334I","R254L","N28T","N64W","L346F",
  "K227I","R477Q","R251W","K53R","R87P","G508D","I308V","I62C","R87M","Y47F",
  "K409M","H183W","R225L","R93A","V248L","V46I","H448I","K409S","T552Y","K53S",
  "Q132M","T537A","D31N","T256A","T267W",
].join("\n");

// parsedMutations (95 entries)
const parsedMutations = [
  { raw: "V100F", wt_aa: "V", position: 100, mt_aa: "F" },
  { raw: "V299I", wt_aa: "V", position: 299, mt_aa: "I" },
  { raw: "V550P", wt_aa: "V", position: 550, mt_aa: "P" },
  { raw: "Y360F", wt_aa: "Y", position: 360, mt_aa: "F" },
  { raw: "V10L", wt_aa: "V", position: 10, mt_aa: "L" },
  { raw: "E222D", wt_aa: "E", position: 222, mt_aa: "D" },
  { raw: "V424W", wt_aa: "V", position: 424, mt_aa: "W" },
  { raw: "R261W", wt_aa: "R", position: 261, mt_aa: "W" },
  { raw: "N63S", wt_aa: "N", position: 63, mt_aa: "S" },
  { raw: "Q426D", wt_aa: "Q", position: 426, mt_aa: "D" },
  { raw: "Q426E", wt_aa: "Q", position: 426, mt_aa: "E" },
  { raw: "R560S", wt_aa: "R", position: 560, mt_aa: "S" },
  { raw: "V108L", wt_aa: "V", position: 108, mt_aa: "L" },
  { raw: "H448L", wt_aa: "H", position: 448, mt_aa: "L" },
  { raw: "Q213T", wt_aa: "Q", position: 213, mt_aa: "T" },
  { raw: "R124W", wt_aa: "R", position: 124, mt_aa: "W" },
  { raw: "E228D", wt_aa: "E", position: 228, mt_aa: "D" },
  { raw: "H448M", wt_aa: "H", position: 448, mt_aa: "M" },
  { raw: "S220F", wt_aa: "S", position: 220, mt_aa: "F" },
  { raw: "R214P", wt_aa: "R", position: 214, mt_aa: "P" },
  { raw: "E189D", wt_aa: "E", position: 189, mt_aa: "D" },
  { raw: "T397V", wt_aa: "T", position: 397, mt_aa: "V" },
  { raw: "R254I", wt_aa: "R", position: 254, mt_aa: "I" },
  { raw: "E559D", wt_aa: "E", position: 559, mt_aa: "D" },
  { raw: "Q132W", wt_aa: "Q", position: 132, mt_aa: "W" },
  { raw: "T478L", wt_aa: "T", position: 478, mt_aa: "L" },
  { raw: "T267H", wt_aa: "T", position: 267, mt_aa: "H" },
  { raw: "L215F", wt_aa: "L", position: 215, mt_aa: "F" },
  { raw: "H270N", wt_aa: "H", position: 270, mt_aa: "N" },
  { raw: "T552F", wt_aa: "T", position: 552, mt_aa: "F" },
  { raw: "R560P", wt_aa: "R", position: 560, mt_aa: "P" },
  { raw: "I551L", wt_aa: "I", position: 551, mt_aa: "L" },
  { raw: "R225K", wt_aa: "R", position: 225, mt_aa: "K" },
  { raw: "R477H", wt_aa: "R", position: 477, mt_aa: "H" },
  { raw: "Q525N", wt_aa: "Q", position: 525, mt_aa: "N" },
  { raw: "T478F", wt_aa: "T", position: 478, mt_aa: "F" },
  { raw: "H209C", wt_aa: "H", position: 209, mt_aa: "C" },
  { raw: "V547I", wt_aa: "V", position: 547, mt_aa: "I" },
  { raw: "V218L", wt_aa: "V", position: 218, mt_aa: "L" },
  { raw: "R477A", wt_aa: "R", position: 477, mt_aa: "A" },
  { raw: "R225Q", wt_aa: "R", position: 225, mt_aa: "Q" },
  { raw: "D401E", wt_aa: "D", position: 401, mt_aa: "E" },
  { raw: "I442V", wt_aa: "I", position: 442, mt_aa: "V" },
  { raw: "D339E", wt_aa: "D", position: 339, mt_aa: "E" },
  { raw: "V550C", wt_aa: "V", position: 550, mt_aa: "C" },
  { raw: "K53N", wt_aa: "K", position: 53, mt_aa: "N" },
  { raw: "V108F", wt_aa: "V", position: 108, mt_aa: "F" },
  { raw: "H448F", wt_aa: "H", position: 448, mt_aa: "F" },
  { raw: "V108I", wt_aa: "V", position: 108, mt_aa: "I" },
  { raw: "L556W", wt_aa: "L", position: 556, mt_aa: "W" },
  { raw: "V5F", wt_aa: "V", position: 5, mt_aa: "F" },
  { raw: "R261N", wt_aa: "R", position: 261, mt_aa: "N" },
  { raw: "T487N", wt_aa: "T", position: 487, mt_aa: "N" },
  { raw: "S112M", wt_aa: "S", position: 112, mt_aa: "M" },
  { raw: "N63F", wt_aa: "N", position: 63, mt_aa: "F" },
  { raw: "H448V", wt_aa: "H", position: 448, mt_aa: "V" },
  { raw: "T552L", wt_aa: "T", position: 552, mt_aa: "L" },
  { raw: "T478C", wt_aa: "T", position: 478, mt_aa: "C" },
  { raw: "S11E", wt_aa: "S", position: 11, mt_aa: "E" },
  { raw: "V286I", wt_aa: "V", position: 286, mt_aa: "I" },
  { raw: "R560G", wt_aa: "R", position: 560, mt_aa: "G" },
  { raw: "Q426N", wt_aa: "Q", position: 426, mt_aa: "N" },
  { raw: "I44V", wt_aa: "I", position: 44, mt_aa: "V" },
  { raw: "I428V", wt_aa: "I", position: 428, mt_aa: "V" },
  { raw: "R560A", wt_aa: "R", position: 560, mt_aa: "A" },
  { raw: "V334I", wt_aa: "V", position: 334, mt_aa: "I" },
  { raw: "R254L", wt_aa: "R", position: 254, mt_aa: "L" },
  { raw: "N28T", wt_aa: "N", position: 28, mt_aa: "T" },
  { raw: "N64W", wt_aa: "N", position: 64, mt_aa: "W" },
  { raw: "L346F", wt_aa: "L", position: 346, mt_aa: "F" },
  { raw: "K227I", wt_aa: "K", position: 227, mt_aa: "I" },
  { raw: "R477Q", wt_aa: "R", position: 477, mt_aa: "Q" },
  { raw: "R251W", wt_aa: "R", position: 251, mt_aa: "W" },
  { raw: "K53R", wt_aa: "K", position: 53, mt_aa: "R" },
  { raw: "R87P", wt_aa: "R", position: 87, mt_aa: "P" },
  { raw: "G508D", wt_aa: "G", position: 508, mt_aa: "D" },
  { raw: "I308V", wt_aa: "I", position: 308, mt_aa: "V" },
  { raw: "I62C", wt_aa: "I", position: 62, mt_aa: "C" },
  { raw: "R87M", wt_aa: "R", position: 87, mt_aa: "M" },
  { raw: "Y47F", wt_aa: "Y", position: 47, mt_aa: "F" },
  { raw: "K409M", wt_aa: "K", position: 409, mt_aa: "M" },
  { raw: "H183W", wt_aa: "H", position: 183, mt_aa: "W" },
  { raw: "R225L", wt_aa: "R", position: 225, mt_aa: "L" },
  { raw: "R93A", wt_aa: "R", position: 93, mt_aa: "A" },
  { raw: "V248L", wt_aa: "V", position: 248, mt_aa: "L" },
  { raw: "V46I", wt_aa: "V", position: 46, mt_aa: "I" },
  { raw: "H448I", wt_aa: "H", position: 448, mt_aa: "I" },
  { raw: "K409S", wt_aa: "K", position: 409, mt_aa: "S" },
  { raw: "T552Y", wt_aa: "T", position: 552, mt_aa: "Y" },
  { raw: "K53S", wt_aa: "K", position: 53, mt_aa: "S" },
  { raw: "Q132M", wt_aa: "Q", position: 132, mt_aa: "M" },
  { raw: "T537A", wt_aa: "T", position: 537, mt_aa: "A" },
  { raw: "D31N", wt_aa: "D", position: 31, mt_aa: "N" },
  { raw: "T256A", wt_aa: "T", position: 256, mt_aa: "A" },
  { raw: "T267W", wt_aa: "T", position: 267, mt_aa: "W" },
];

// Use imported primer data as mockDesignResults
const mockDesignResults: SdmPrimerResult[] = primerData;

// Plate mappings (fwd: column order, rev: deduplicated)
function wellName(idx: number): string {
  const rows = "ABCDEFGH";
  const col = Math.floor(idx / 8) + 1;
  const row = idx % 8;
  return `${rows[row]}${String(col).padStart(2, "0")}`;
}

const mockPlateMappings: PlateMapping[] = [
  ...mockDesignResults.map((r, i) => ({
    well: wellName(i),
    primer_name: `${r.mutation}_F`,
    sequence: r.forward_seq,
    primer_type: "forward" as const,
    mutation: r.mutation,
  })),
  ...(() => {
    const seen = new Map<string, PlateMapping>();
    for (const r of mockDesignResults) {
      if (!seen.has(r.reverse_seq)) {
        seen.set(r.reverse_seq, {
          well: wellName(seen.size),
          primer_name: `${r.mutation}_R`,
          sequence: r.reverse_seq,
          primer_type: "reverse" as const,
          mutation: r.mutation,
        });
      }
    }
    return [...seen.values()];
  })(),
];

// Dedup info for shared reverse detection
const mockDedupInfo: Record<string, string[]> = {};
for (const r of mockDesignResults) {
  if (!mockDedupInfo[r.reverse_seq]) mockDedupInfo[r.reverse_seq] = [];
  mockDedupInfo[r.reverse_seq].push(r.mutation);
}

// --- Screen states ---

export interface ScreenState {
  name: string;
  caption: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  state: Record<string, any>;
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
    caption: "GenBank 파일 로드 완료 — IspS 유전자가 자동 선택된다",
    state: {
      fastaPath: "D:\\_workspace\\_projects\\030.EvolveProprimer\\pTSN-PtIspS-idi(KanR)_corrected.dna",
      seqInfo: mockSeqInfo,
      selectedGene: "267",
      mutationText: "",
      parsedMutations: [],
      designResults: [],
      plateMappings: [],
      statusMessage: "Loaded: pTSN-PtIspS-idi(KanR)_corrected (6494 bp) | 4 gene(s) | Target: IspS",
      progress: 0,
      isDesigning: false,
    },
  },
  {
    name: "03-mutations-entered",
    caption: "EVOLVEpro CSV에서 95개 변이 목록 로드 완료",
    state: {
      fastaPath: "D:\\_workspace\\_projects\\030.EvolveProprimer\\pTSN-PtIspS-idi(KanR)_corrected.dna",
      seqInfo: mockSeqInfo,
      selectedGene: "267",
      mutationInputMode: "evolvepro",
      evolveproCsvPath: "D:\\_workspace\\_projects\\030.EvolveProprimer\\df_test.csv",
      mutationText: evolveMutationText,
      parsedMutations,
      parseErrors: [],
      designResults: [],
      plateMappings: [],
      statusMessage: "EVOLVEpro: 95 variants loaded (y_pred sorted)",
      isDesigning: false,
    },
  },
  {
    name: "04-design-complete",
    caption: "프라이머 설계 완료 — 95개 변이에 대한 프라이머 테이블",
    state: {
      fastaPath: "D:\\_workspace\\_projects\\030.EvolveProprimer\\pTSN-PtIspS-idi(KanR)_corrected.dna",
      seqInfo: mockSeqInfo,
      selectedGene: "267",
      mutationInputMode: "evolvepro",
      evolveproCsvPath: "D:\\_workspace\\_projects\\030.EvolveProprimer\\df_test.csv",
      mutationText: evolveMutationText,
      designResults: mockDesignResults,
      successCount: 95,
      totalCount: 95,
      failedMutations: [] as FailedMutation[],
      plateMappings: mockPlateMappings,
      dedupInfo: mockDedupInfo,
      statusMessage: "95/95 designed | Tm condition: 95/95",
      progress: 100,
      isDesigning: false,
      manuallySwapped: {},
      customCandidates: {},
      tableSorting: [],
    },
  },
  {
    name: "05-plate-map",
    caption: "Plate Map — 96-well 형식으로 95개 프라이머 배치가 표시된다",
    state: {
      fastaPath: "D:\\_workspace\\_projects\\030.EvolveProprimer\\pTSN-PtIspS-idi(KanR)_corrected.dna",
      seqInfo: mockSeqInfo,
      selectedGene: "267",
      mutationInputMode: "evolvepro",
      mutationText: evolveMutationText,
      designResults: mockDesignResults,
      successCount: 95,
      totalCount: 95,
      failedMutations: [] as FailedMutation[],
      plateMappings: mockPlateMappings,
      dedupInfo: mockDedupInfo,
      statusMessage: "95/95 designed | Tm condition: 95/95",
      progress: 100,
      isDesigning: false,
    },
  },
];
