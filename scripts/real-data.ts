/**
 * Capture states built from real KURO sidecar output.
 *
 * Every number here traces back to scripts/real-data.json, which
 * scripts/gen_real_capture_data.py obtains by driving the built sidecar over
 * JSON-RPC against the lab IspS records. Nothing in this file invents a value,
 * which is the difference from scripts/mock-data.ts.
 *
 * Regenerate the bundle before capturing:
 *   .venv/bin/python scripts/gen_real_capture_data.py
 */

import { createRequire } from "module";
import type {
  SequenceInfo,
  SdmPrimerResult,
  PlateMapping,
  FailedMutation,
} from "../src/types/models";

const require = createRequire(import.meta.url);

interface RealBundle {
  inputs: { genbank: string; evolvepro: string };
  design_params: {
    polymerase: string;
    codon_strategy: string;
    organism: string;
    tm_fwd_target: number;
    tm_rev_target: number;
    tm_overlap_target: number;
    target_start: number;
    top_n: number;
    round_size: number;
  };
  target_cds: { cds_start: number; cds_end: number; aa_length: number; translation: string };
  seq_info: SequenceInfo;
  evolvepro: {
    variants: string[];
    total_count: number;
    selected_count: number;
    domain_stats?: Record<string, { quota: number; selected: number }> | null;
    ranked_candidates?: unknown[];
    step_stats?: Record<string, unknown> | null;
  };
  design: {
    results: SdmPrimerResult[];
    success_count: number;
    total_count: number;
    failed_mutations: Array<{ mutation: string; reason: string; rank?: number }>;
    // The engine reports one entry per rescue with its provenance; older
    // bundles carried plain names.
    rescued_mutations?: Array<
      string | { original: string; type?: string; penalty?: number; tolerance_used?: number }
    >;
    rescue_stats?: Record<string, number>;
  };
  rescue?: { tol_max: number; rev_len_min: number };
  plate: { mappings: PlateMapping[] };
  uniprot: {
    candidates: Array<{
      accession: string;
      name: string;
      organism: string;
      length: number;
      identity: number;
      has_structure?: boolean;
    }>;
  };
  domains: {
    accession?: string;
    domains: Array<{ name: string; id: string; start: number; end: number; db: string }>;
  };
}

// eslint-disable-next-line @typescript-eslint/no-var-requires
const real = require("./real-data.json") as RealBundle;

const seqInfo = real.seq_info;
const targetStart = real.design_params.target_start;
// The store keys the gene selector by CDS start, as a string.
const selectedGene = String(targetStart);

const designResults = real.design.results;
const plateMappings = real.plate.mappings;
const failedMutations: FailedMutation[] = real.design.failed_mutations.map((f, i) => ({
  mutation: f.mutation,
  reason: f.reason,
  rank: f.rank ?? i + 1,
}));

const variants = real.evolvepro.variants;
const mutationText = variants.join("\n");
const parsedMutations = variants.map((raw) => ({
  raw,
  wt_aa: raw[0],
  position: parseInt(raw.slice(1, -1), 10),
  mt_aa: raw[raw.length - 1],
}));

const rescuedMutations = (real.design.rescued_mutations ?? []).map((entry) =>
  typeof entry === "string" ? entry : entry.original,
);
const rescuedRows = designResults.filter((r) => rescuedMutations.includes(r.mutation));

const uniprotCandidates = real.uniprot.candidates.slice(0, 3);
const topAccession = uniprotCandidates[0]?.accession ?? "";
const domains = real.domains.domains;

const dedupInfo: Record<string, string[]> = {};
for (const r of designResults) {
  (dedupInfo[r.reverse_seq] ??= []).push(r.mutation);
}

const tmMet = designResults.filter((r) => r.tm_condition_met).length;
const successCount = real.design.success_count;
const totalCount = real.design.total_count;
const designStatus = `${successCount}/${totalCount} designed | Tm ${tmMet}/${designResults.length}`;
const loadedStatus =
  `Loaded: ${seqInfo.header} (${seqInfo.seq_length} bp) | ` +
  `${seqInfo.genes.length} CDS | Target: ${targetStart}..${real.target_cds.cds_end} ` +
  `(${real.target_cds.aa_length} aa)`;

// Domain quotas the sidecar reported, if the run exercised domain diversity.
const domainStats = real.evolvepro.domain_stats ?? undefined;

/** Store keys shared by every state that shows a loaded sequence. */
const loaded = {
  fastaPath: real.inputs.genbank,
  seqInfo,
  selectedGene,
  organism: real.design_params.organism,
  polymerase: real.design_params.polymerase,
  codonStrategy: real.design_params.codon_strategy,
  tmFwdTarget: real.design_params.tm_fwd_target,
  tmRevTarget: real.design_params.tm_rev_target,
  tmOverlapTarget: real.design_params.tm_overlap_target,
  isDesigning: false,
};

/**
 * Store keys shared by every state that shows a finished design.
 *
 * setState merges, so the structure keys are cleared explicitly. Without that
 * the AlphaFold model loaded for the 3D screen stays on every later screen and
 * two frames end up looking like the same one.
 */
const designed = {
  ...loaded,
  structureAccession: "",
  structureLoaded: false,
  structureLoading: false,
  structure3dState: "off",
  uniprotAccession: "",
  domains: [],
  mutationInputMode: "evolvepro",
  evolveproCsvPath: real.inputs.evolvepro,
  mutationText,
  designResults,
  plateMappings,
  dedupInfo,
  successCount,
  totalCount,
  failedMutations,
  progress: 100,
  statusMessage: designStatus,
  manuallySwapped: {},
  customCandidates: {},
  tableSorting: [],
};

export interface ScreenState {
  name: string;
  caption: string;
  /** Merged into the app store before the screenshot. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  state: Record<string, any>;
  /** Wizard position, applied together with `state`. */
  nav?: { currentMajor: string; currentSubStep: string };
  /** Playwright selector clicked with real input, before `action` runs. */
  click?: string;
  /** Runs in the page after the state settles. */
  action?: string;
}

const NAV_LOAD = { currentMajor: "design", currentSubStep: "design.load" };
const NAV_MUTATION = { currentMajor: "design", currentSubStep: "design.mutation" };
const NAV_PARAMS = { currentMajor: "design", currentSubStep: "design.params" };
const NAV_SUBMIT = { currentMajor: "design", currentSubStep: "design.submit" };
const NAV_OUTPUT = { currentMajor: "output", currentSubStep: "output.summary" };
const NAV_EXPORT = { currentMajor: "export", currentSubStep: "export.all" };

export const screenStates: ScreenState[] = [
  {
    name: "01-initial",
    caption: "Load step before any file is selected",
    nav: NAV_LOAD,
    state: {
      fastaPath: "",
      seqInfo: null,
      mutationText: "",
      parsedMutations: [],
      parseErrors: [],
      designResults: [],
      plateMappings: [],
      failedMutations: [],
      statusMessage: "Ready",
      progress: 0,
      isDesigning: false,
    },
  },
  {
    name: "02-file-loaded",
    caption: `GenBank loaded, IspS CDS ${targetStart} selected`,
    nav: NAV_LOAD,
    state: { ...loaded, mutationText: "", parsedMutations: [], designResults: [], plateMappings: [], statusMessage: loadedStatus, progress: 0 },
  },
  {
    name: "03-mutations-entered",
    caption: `EVOLVEpro predictions loaded, ${variants.length} variants`,
    nav: NAV_MUTATION,
    state: {
      ...loaded,
      mutationInputMode: "evolvepro",
      evolveproCsvPath: real.inputs.evolvepro,
      mutationText,
      parsedMutations,
      parseErrors: [],
      designResults: [],
      plateMappings: [],
      evolveproTotalCount: real.evolvepro.total_count,
      statusMessage: `EVOLVEpro: ${variants.length} of ${real.evolvepro.total_count} variants selected`,
    },
  },
  {
    name: "04-design-complete",
    caption: `Primer table for ${successCount} designed variants`,
    nav: NAV_OUTPUT,
    state: designed,
  },
  {
    name: "05-plate-map",
    caption: `Plate map, ${plateMappings.length} primers`,
    nav: NAV_OUTPUT,
    state: designed,
    action: `
      const panel = document.querySelector('[data-testid="output-plate-panel"]');
      if (!panel) return false;
      const toggle = document.querySelector('[data-testid="panel-toggle"]');
      if (toggle) toggle.click();
      panel.scrollIntoView({ block: 'center' });
      return true;
    `,
  },
  {
    name: "06-parameter-advanced",
    caption: "Parameter step with advanced options expanded",
    nav: NAV_PARAMS,
    state: { ...loaded, mutationInputMode: "text", mutationText: variants.slice(0, 3).join("\n"), statusMessage: "Ready" },
    action: `
      const btn = [...document.querySelectorAll('button')]
        .find(b => /advanced|고급/i.test(b.textContent || ''));
      if (!btn) return false;
      btn.click();
      return true;
    `,
  },
  {
    name: "07-uniprot-candidates",
    caption: `UniProt hits for the IspS translation, top ${topAccession}`,
    nav: NAV_SUBMIT,
    state: {
      ...loaded,
      mutationInputMode: "evolvepro",
      evolveproCsvPath: real.inputs.evolvepro,
      mutationText,
      parsedMutations,
      pipelineMode: true,
      evolveproTotalCount: real.evolvepro.total_count,
      uniprotSearching: false,
      uniprotCandidates,
      uniprotAccession: topAccession,
      statusMessage: `UniProt: ${topAccession} at ${uniprotCandidates[0]?.identity ?? 0}% identity`,
    },
  },
  {
    name: "08-diversity-position",
    caption: "Position diversity limit applied to the variant pool",
    nav: NAV_SUBMIT,
    state: {
      ...loaded,
      mutationInputMode: "evolvepro",
      evolveproCsvPath: real.inputs.evolvepro,
      mutationText,
      parsedMutations,
      positionDiversityEnabled: true,
      maxPerPosition: 2,
      evolveproTotalCount: real.evolvepro.total_count,
      statusMessage: "Position diversity: max 2 per position",
    },
  },
  {
    name: "09-diversity-domain",
    caption: `Domain diversity over ${domains.length} InterPro domains of ${real.domains.accession ?? topAccession}`,
    nav: NAV_SUBMIT,
    state: {
      ...loaded,
      mutationInputMode: "evolvepro",
      uniprotAccession: real.domains.accession ?? topAccession,
      domainDiversityEnabled: true,
      domainStrategy: "proportional",
      domains,
      ...(domainStats ? { domainStats } : {}),
      statusMessage: `Domain diversity: ${domains.length} domains, proportional`,
    },
  },
  {
    name: "10-designing",
    caption: "Design running",
    nav: NAV_SUBMIT,
    state: {
      ...loaded,
      mutationInputMode: "evolvepro",
      mutationText,
      parsedMutations,
      isDesigning: true,
      progress: Math.round((successCount / totalCount) * 100 * 0.5),
      statusMessage: `Designing primers... (${Math.floor(totalCount / 2)}/${totalCount})`,
    },
  },
  {
    // The stock parameters reject two mutations at codon 267 and the rescue
    // pass recovers both with a shorter reverse primer, so there is no
    // rejection left to show. This frame carries the rescued rows instead.
    name: "11-rescued-rows",
    caption:
      rescuedRows.length > 0
        ? `Primer table scrolled to the ${rescuedRows.length} rescued mutations ` +
          `(${rescuedRows.map((r) => `${r.mutation} rev ${r.rev_len} bp`).join(", ")})`
        : `Sequence map marking the ${failedMutations.length} rejected mutations`,
    nav: NAV_OUTPUT,
    state: {
      ...designed,
      statusMessage:
        rescuedMutations.length > 0
          ? `${successCount}/${totalCount} designed | ${rescuedMutations.length} rescued`
          : `${successCount}/${totalCount} designed | ${failedMutations.length} failed`,
    },
    action: `
      const names = ${JSON.stringify(rescuedMutations)};
      if (names.length === 0) return false;
      const row = [...document.querySelectorAll('tr')]
        .find(tr => names.some(n => (tr.textContent || '').includes(n)));
      if (!row) return false;
      row.scrollIntoView({ block: 'center' });
      return true;
    `,
  },
  {
    name: "12-plate-multi",
    caption: "Plate pair review switched to the deduplicated reverse plate",
    nav: NAV_OUTPUT,
    state: designed,
    // The forward and reverse plates are the two pages of the pair review, so
    // this is the plate navigation the file name promises.
    click: "button:has-text('Reverse (')",

  },
  {
    name: "13-menu-bar",
    caption: "File menu expanded",
    nav: NAV_OUTPUT,
    state: designed,
    click: "button:text-is('File')",
  },
  {
    name: "14-polymerase-editor",
    caption: "Custom polymerase editor",
    nav: NAV_PARAMS,
    state: loaded,
    click: "button:has-text('Custom Polymerase')",
  },
  {
    // The benchmark dialog returns null without measured fitness, and the
    // EVOLVEpro table for this target carries predictions only (y_actual is
    // empty in all 10,547 rows), so a benchmark frame cannot be produced from
    // this input. The 3D panel takes the slot: it shows the AlphaFold model the
    // sidecar fetched for the top UniProt hit.
    name: "15-structure-3d",
    caption: `AlphaFold model for ${real.domains.accession ?? topAccession} in the 3D panel`,
    nav: NAV_OUTPUT,
    state: {
      ...designed,
      uniprotAccession: real.domains.accession ?? topAccession,
      structureAccession: real.domains.accession ?? topAccession,
      structureLoaded: true,
      structureLoading: false,
      structure3dState: "on",
      domains,
    },
    action: `
      const panel = document.querySelector('[data-testid="selection3d-panel"]');
      if (!panel) return false;
      const body = panel.querySelector('[data-testid="panel-body"]');
      if (!body) {
        const toggle = panel.querySelector('[data-testid="panel-toggle"]');
        if (toggle) toggle.click();
      }
      panel.scrollIntoView({ block: 'center' });
      return true;
    `,
  },
  {
    name: "16-design-report",
    // Anchored on the Tm distribution rather than the rejection list: the
    // rescue pass empties that list, and a section that can vanish is not
    // something to hang a screenshot on.
    caption: "Design report inspector, scrolled to the primer statistics",
    nav: NAV_OUTPUT,
    state: designed,
    action: `
      const panel = document.querySelector('[data-testid="inspector"]');
      if (!panel) return false;
      const target = [...panel.querySelectorAll('*')]
        .find(el => /tm distribution/i.test((el.textContent || '').slice(0, 60)));
      if (!target) return false;
      target.scrollIntoView({ block: 'start' });
      return true;
    `,
  },
  {
    // Named for the step, not a dialog: AppLayout dropped the mapping popup and
    // the options now live inline on the export step.
    name: "17-mapping-export",
    caption: "Export step with the plate-mapping and order options",
    nav: NAV_EXPORT,
    state: designed,
    action: `
      const sel = document.querySelector('select#amount, select[id="amount"]');
      const body = document.querySelector('[data-testid="wizard-body"]');
      if (!body) return false;
      if (sel) sel.focus();
      body.scrollIntoView({ block: 'start' });
      return true;
    `,
  },
  {
    name: "18-primer-popover",
    caption: "Primer candidate popover",
    nav: NAV_OUTPUT,
    state: designed,
    action: `
      const cell = document.querySelector('td.cursor-pointer');
      if (!cell) return false;
      cell.click();
      return true;
    `,
  },
  {
    name: "19-gene-dropdown",
    caption: `Gene selector over the ${seqInfo.genes.length} CDS of the plasmid`,
    nav: NAV_LOAD,
    state: { ...loaded, statusMessage: loadedStatus },
    action: `
      const sel = [...document.querySelectorAll('select')].find(s => s.options.length > 1);
      if (!sel) return false;
      sel.focus();
      sel.size = Math.min(sel.options.length, 6);
      return true;
    `,
  },
  {
    name: "20-pipeline-full",
    caption: "Full selection pipeline: top-N, position, domain, Pareto",
    nav: NAV_SUBMIT,
    state: {
      ...loaded,
      mutationInputMode: "evolvepro",
      evolveproCsvPath: real.inputs.evolvepro,
      mutationText,
      parsedMutations,
      pipelineMode: true,
      evolveproTotalCount: real.evolvepro.total_count,
      positionDiversityEnabled: true,
      maxPerPosition: 2,
      domainDiversityEnabled: true,
      domainStrategy: "proportional",
      uniprotAccession: real.domains.accession ?? topAccession,
      domains,
      ...(domainStats ? { domainStats } : {}),
      paretoDiversityEnabled: true,
      entropyWeightEnabled: true,
      entropyWeight: 0.3,
      paretoPoolMultiplier: 2.0,
      distanceMode: "auto",
      statusMessage:
        `Pipeline: top-${real.design_params.top_n} to position and domain to Pareto ` +
        `(${variants.length} of ${real.evolvepro.total_count})`,
    },
  },
];
