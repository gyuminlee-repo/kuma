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

// --- Real data from sample_plasmid.gb ---

const mockSeqInfo: SequenceInfo = {
  header: "Synthetic plasmid for KURO SDM primer design tool testing",
  seq_length: 5000,
  genes: [
    { gene: "lacZ_alpha", product: "lacZ alpha fragment", cds_start: 797, cds_end: 1160, aa_length: 121 },
    { gene: "synR", product: "synthetic regulator", cds_start: 1957, cds_end: 3100, aa_length: 381 },
    { gene: "ampR", product: "ampicillin resistance", cds_start: 3897, cds_end: 4200, aa_length: 101 },
  ],
};

// EVOLVEpro top-95 mutation text (from samples/sample_evolvepro.csv)
const evolveMutationText = [
  "N267F","Q163W","G28I","I132P","Y41H","S275R","K48N","D38A","V224Q","C13L",
  "G70L","G137P","C361R","P68G","Y115H","Y36C","S377D","S326Q","K90T","R355Y",
  "Y34V","V42R","L214P","F372N","W164V","V23Y","L214E","F111Q","K93W","K63I",
  "E374C","L228I","F293I","E179S","L51E","S332F","A99V","H297P","F50V","I260N",
  "E167R","R96A","D284G","H189K","C19M","H87L","S52C","F263W","H155D","W271I",
  "E167K","I363S","E33P","H87G","I31L","N200T","E58F","S56F","R105E","C19I",
  "G273F","K168P","A108T","I367K","Q2V","H245F","A136W","H12Q","D30N","K97W",
  "L321A","P122R","W188I","Q156A","H376S","W129I","C361Y","Q248L","V279S","T274P",
  "N250A","Q308W","P161M","I47K","A237P","S283V","V197A","I294F","H297Q","I181A",
  "S322C","F50M","A100C","F204K","D231Q",
].join("\n");

// parsedMutations — auto-generated from evolveMutationText
const parsedMutations = evolveMutationText.split("\n").map((raw) => {
  const wt_aa = raw[0];
  const mt_aa = raw[raw.length - 1];
  const position = parseInt(raw.slice(1, -1), 10);
  return { raw, wt_aa, position, mt_aa };
});

// (Legacy static parsedMutations array removed — now auto-generated above)

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
    caption: "Initial screen — before loading any file",
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
    caption: "GenBank file loaded — synR gene auto-selected",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationText: "",
      parsedMutations: [],
      designResults: [],
      plateMappings: [],
      statusMessage: "Loaded: Synthetic plasmid (5000 bp) | 3 gene(s) | Target: synR",
      progress: 0,
      isDesigning: false,
    },
  },
  {
    name: "03-mutations-entered",
    caption: "EVOLVEpro CSV loaded — 95 variants",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      evolveproCsvPath: "C:\\samples\\sample_evolvepro.csv",
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
    caption: "Design complete — primer table for 95 variants",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      evolveproCsvPath: "C:\\samples\\sample_evolvepro.csv",
      mutationText: evolveMutationText,
      designResults: mockDesignResults,
      successCount: mockDesignResults.length,
      totalCount: 95,
      failedMutations: [] as FailedMutation[],
      plateMappings: mockPlateMappings,
      dedupInfo: mockDedupInfo,
      statusMessage: `${mockDesignResults.length}/95 designed | Tm: ${mockDesignResults.filter(r => r.tm_condition_met).length}/${mockDesignResults.length}`,
      progress: 100,
      isDesigning: false,
      manuallySwapped: {},
      customCandidates: {},
      tableSorting: [],
    },
  },
  {
    name: "05-plate-map",
    caption: "Plate Map — 95 primers arranged in 96-well format",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      mutationText: evolveMutationText,
      designResults: mockDesignResults,
      successCount: mockDesignResults.length,
      totalCount: 95,
      failedMutations: [] as FailedMutation[],
      plateMappings: mockPlateMappings,
      dedupInfo: mockDedupInfo,
      statusMessage: `${mockDesignResults.length}/95 designed | Tm: ${mockDesignResults.filter(r => r.tm_condition_met).length}/${mockDesignResults.length}`,
      progress: 100,
      isDesigning: false,
    },
  },
];
