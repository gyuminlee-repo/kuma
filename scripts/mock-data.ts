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
  {
    name: "06-parameter-advanced",
    caption: "Parameter panel — Advanced options expanded",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "text",
      mutationText: "Q232A\nY233A\nE335A",
      statusMessage: "Ready",
      isDesigning: false,
    },
    action: `
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Advanced options...');
      if (btn) btn.click();
    `,
  },
  {
    name: "07-uniprot-candidates",
    caption: "UniProt candidate list (EVOLVEpro mode + pipeline active)",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      evolveproCsvPath: "C:\\samples\\sample_evolvepro.csv",
      mutationText: evolveMutationText,
      parsedMutations,
      pipelineMode: true,
      evolveproTotalCount: 95,
      uniprotSearching: false,
      uniprotCandidates: [
        { accession: "Q50L36", name: "mmoX", organism: "Methylococcus capsulatus", length: 527, identity: 99.8, has_structure: true },
        { accession: "P22869", name: "mmoX", organism: "Methylosinus trichosporium", length: 527, identity: 88.5, has_structure: true },
        { accession: "A0A0H5B7Q3", name: "mmoX", organism: "Methylocystis parvus", length: 525, identity: 84.2, has_structure: false },
      ],
      uniprotAccession: "Q50L36",
      statusMessage: "UniProt: auto-matched Q50L36 (99.8% identity)",
    },
  },
  {
    name: "08-diversity-position",
    caption: "Position diversity enabled (EVOLVEpro mode)",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      evolveproCsvPath: "C:\\samples\\sample_evolvepro.csv",
      mutationText: evolveMutationText,
      positionDiversityEnabled: true,
      maxPerPosition: 2,
      evolveproTotalCount: 95,
      statusMessage: "Position diversity: max 2 per position",
    },
  },
  {
    name: "09-diversity-domain",
    caption: "Domain diversity with InterPro domains fetched",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      uniprotAccession: "Q50L36",
      domainDiversityEnabled: true,
      domainStrategy: "proportional",
      domains: [
        { name: "MMO_hydroxylase_alpha_N", id: "IPR003430", start: 10, end: 180, db: "interpro" },
        { name: "MMO_hydroxylase_alpha_C", id: "IPR012348", start: 190, end: 380, db: "interpro" },
        { name: "MMO_hydroxylase_alpha_tail", id: "IPR008969", start: 385, end: 510, db: "interpro" },
      ],
      domainStats: {
        "MMO_hydroxylase_alpha_N-10": { quota: 30, selected: 28 },
        "MMO_hydroxylase_alpha_C-190": { quota: 45, selected: 45 },
        "MMO_hydroxylase_alpha_tail-385": { quota: 20, selected: 19 },
      },
      statusMessage: "Domain diversity: 3 domains, proportional",
    },
  },
  {
    name: "10-designing",
    caption: "Design in progress — progress bar active",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      mutationText: evolveMutationText,
      parsedMutations,
      isDesigning: true,
      progress: 45,
      statusMessage: "Designing primers... (42/95)",
    },
  },
  {
    name: "11-failed-rows",
    caption: "Result table with failed mutations (red rows)",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      mutationText: evolveMutationText,
      designResults: mockDesignResults.slice(0, 90),
      failedMutations: [
        { mutation: "C361R", reason: "Tm out of range (fwd 71.2°C > target 62°C + 3)" },
        { mutation: "H376S", reason: "Hairpin ΔG below threshold" },
        { mutation: "F372N", reason: "No valid primer pair within GC range" },
      ] as FailedMutation[],
      plateMappings: mockPlateMappings,
      dedupInfo: mockDedupInfo,
      successCount: 90,
      totalCount: 95,
      progress: 100,
      isDesigning: false,
      statusMessage: "90/95 designed | 3 failed, 2 rescued",
    },
  },
  {
    name: "12-plate-multi",
    caption: "Multi-plate navigation (192 mutations = 2 plates)",
    state: (() => {
      const extended = [...mockDesignResults, ...mockDesignResults].slice(0, 192).map((r, i) => ({ ...r, mutation: `M${i+1}` }));
      const plates = extended.map((r, i) => ({
        well: wellName(i % 96),
        primer_name: `${r.mutation}_F`,
        sequence: r.forward_seq,
        primer_type: "forward" as const,
        mutation: r.mutation,
      }));
      return {
        fastaPath: "C:\\samples\\sample_plasmid.gb",
        seqInfo: mockSeqInfo,
        selectedGene: "1957",
        mutationInputMode: "evolvepro",
        designResults: extended,
        plateMappings: plates,
        dedupInfo: {},
        successCount: 192,
        totalCount: 192,
        progress: 100,
        isDesigning: false,
        statusMessage: "192/192 designed",
      };
    })(),
  },
  {
    name: "19-gene-dropdown",
    caption: "Gene selection dropdown (multi-CDS GenBank)",
    state: {
      fastaPath: "C:\\samples\\multi_cds.gb",
      seqInfo: {
        ...mockSeqInfo,
        header: "Multi-CDS plasmid with 3 genes (5000 bp)",
      },
      selectedGene: "1957",
      statusMessage: "Loaded: Multi-CDS plasmid (5000 bp) | 3 gene(s) | Target: synR",
      isDesigning: false,
    },
    action: `
      const sel = document.querySelector('select[id*="gene" i]') || [...document.querySelectorAll('select')].find(s => s.options.length > 1);
      if (sel) { sel.focus(); sel.size = sel.options.length; }
    `,
  },
  {
    name: "20-pipeline-full",
    caption: "Full pipeline: EVOLVEpro + position + domain + Pareto",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      evolveproCsvPath: "C:\\samples\\sample_evolvepro.csv",
      mutationText: evolveMutationText,
      parsedMutations,
      pipelineMode: true,
      evolveproTotalCount: 95,
      positionDiversityEnabled: true,
      maxPerPosition: 2,
      domainDiversityEnabled: true,
      domainStrategy: "proportional",
      uniprotAccession: "Q50L36",
      domains: [
        { name: "MMO_hydroxylase_alpha_N", id: "IPR003430", start: 10, end: 180, db: "interpro" },
        { name: "MMO_hydroxylase_alpha_C", id: "IPR012348", start: 190, end: 380, db: "interpro" },
      ],
      domainStats: {
        "MMO_hydroxylase_alpha_N-10": { quota: 35, selected: 34 },
        "MMO_hydroxylase_alpha_C-190": { quota: 55, selected: 55 },
      },
      paretoDiversityEnabled: true,
      entropyWeightEnabled: true,
      entropyWeight: 0.3,
      paretoPoolMultiplier: 2.0,
      distanceMode: "auto",
      statusMessage: "Pipeline: Top-N → Position+Domain → Pareto+Entropy (95)",
    },
  },
  {
    name: "14-polymerase-editor",
    caption: "Custom Polymerase Editor dialog",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      isDesigning: false,
    },
    action: `
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Custom Polymerase');
      if (btn) btn.click();
    `,
  },
  {
    name: "15-benchmark-dialog",
    caption: "Benchmark dialog — strategy comparison",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      showBenchmark: true,
      benchmarkResults: null,
      isDesigning: false,
    },
  },
  {
    name: "16-design-report",
    caption: "Design Report dialog",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      mutationInputMode: "evolvepro",
      mutationText: evolveMutationText,
      designResults: mockDesignResults,
      plateMappings: mockPlateMappings,
      dedupInfo: mockDedupInfo,
      successCount: mockDesignResults.length,
      totalCount: 95,
      failedMutations: [] as FailedMutation[],
      showReport: true,
      progress: 100,
      isDesigning: false,
    },
  },
  {
    name: "17-mapping-export-dialog",
    caption: "Mapping Export dialog (Echo/JANUS)",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      designResults: mockDesignResults,
      plateMappings: mockPlateMappings,
      dedupInfo: mockDedupInfo,
      successCount: mockDesignResults.length,
      totalCount: 95,
      isDesigning: false,
    },
    action: `
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim().startsWith('Export Mapping'));
      if (btn) btn.click();
    `,
  },
  {
    name: "18-primer-popover",
    caption: "Primer candidate popover (Fwd click)",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      designResults: mockDesignResults,
      plateMappings: mockPlateMappings,
      successCount: mockDesignResults.length,
      totalCount: 95,
      isDesigning: false,
    },
    action: `
      const cells = document.querySelectorAll('td [class*="font-mono"], td [class*="cursor-pointer"]');
      if (cells.length) cells[0].click();
    `,
  },
  {
    name: "13-menu-bar",
    caption: "File menu expanded",
    state: {
      fastaPath: "C:\\samples\\sample_plasmid.gb",
      seqInfo: mockSeqInfo,
      selectedGene: "1957",
      designResults: mockDesignResults,
      plateMappings: mockPlateMappings,
      dedupInfo: mockDedupInfo,
      successCount: mockDesignResults.length,
      totalCount: 95,
      isDesigning: false,
    },
    action: `
      const fileBtn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'File');
      if (fileBtn) fileBtn.click();
    `,
  },
];
