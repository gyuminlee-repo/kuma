import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc";
import type {
  SequenceInfo,
  ParsedMutation,
  ParseError,
  ParseMutationsResult,
  EvolveproLoadResult,
  DomainInfo,
  FetchDomainsResult,
} from "../../types/models";

function formatError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export interface InputSlice {
  // State
  fastaPath: string;
  seqInfo: SequenceInfo | null;
  mutationInputMode: "text" | "evolvepro";
  mutationText: string;
  evolveproCsvPath: string;
  yPredMap: Record<string, number>;
  selectionStrategy: "none" | "topn" | "position" | "domain" | "pareto";
  positionDiversityEnabled: boolean;
  maxPerPosition: number;
  domainDiversityEnabled: boolean;
  domainStrategy: "proportional" | "equal";
  uniprotAccession: string;
  domains: DomainInfo[];
  domainLoading: boolean;
  disabledDomains: Set<string>;
  domainStats: Record<string, { quota: number; selected: number }>;
  paretoDiversityEnabled: boolean;
  parsedMutations: ParsedMutation[];
  parseErrors: ParseError[];
  selectedGene: string;

  // Actions
  loadSequence: (filepath: string) => Promise<void>;
  setSelectedGene: (gene: string) => void;
  setMutationInputMode: (mode: "text" | "evolvepro") => void;
  setMutationText: (text: string) => void;
  setSelectionStrategy: (strategy: "none" | "topn" | "position" | "domain" | "pareto") => void;
  setPositionDiversityEnabled: (enabled: boolean) => void;
  setMaxPerPosition: (n: number) => void;
  setDomainDiversityEnabled: (enabled: boolean) => void;
  setDomainStrategy: (strategy: "proportional" | "equal") => void;
  fetchDomains: (accession: string) => Promise<void>;
  setDomains: (domains: DomainInfo[]) => void;
  toggleDomain: (domainKey: string) => void;
  setParetoDiversityEnabled: (enabled: boolean) => void;
  loadEvolveproCsv: (filepath: string) => Promise<void>;
  parseMutations: () => Promise<void>;
}

let csvLoadGeneration = 0;

export const createInputSlice: StateCreator<InputSlice, [], [], InputSlice> = (set, get) => ({
  fastaPath: "",
  seqInfo: null,
  mutationInputMode: "text",
  mutationText: "",
  evolveproCsvPath: "",
  yPredMap: {},
  selectionStrategy: "none",
  positionDiversityEnabled: false,
  maxPerPosition: 1,
  domainDiversityEnabled: false,
  domainStrategy: "proportional",
  uniprotAccession: "",
  domains: [],
  domainLoading: false,
  disabledDomains: new Set<string>(),
  domainStats: {},
  paretoDiversityEnabled: false,
  parsedMutations: [],
  parseErrors: [],
  selectedGene: "",

  loadSequence: async (filepath: string) => {
    try {
      set({ statusMessage: "Loading sequence file..." } as Partial<InputSlice>);
      const info = await sendRequest<SequenceInfo>("load_fasta", { filepath });

      let bestGene = info.genes.length > 0 ? info.genes[0] : null;
      if (info.genes.length > 1) {
        for (const g of info.genes) {
          if (!bestGene || g.aa_length > bestGene.aa_length) {
            bestGene = g;
          }
        }
      }

      const selectedKey = bestGene ? String(bestGene.cds_start) : "";
      set({
        fastaPath: filepath,
        seqInfo: info,
        selectedGene: selectedKey,
        statusMessage: `Loaded: ${info.header} (${info.seq_length} bp) | ${info.genes.length} gene(s) | Target: ${bestGene?.gene ?? "none"}`,
      } as Partial<InputSlice>);
    } catch (err) {
      set({ statusMessage: `Sequence file load failed: ${formatError(err)}` } as Partial<InputSlice>);
    }
  },

  setSelectedGene: (gene: string) => set({ selectedGene: gene }),
  setMutationInputMode: (mode) => set({ mutationInputMode: mode }),
  setMutationText: (text) => set({ mutationText: text }),

  setSelectionStrategy: (strategy) => {
    set({ selectionStrategy: strategy });
    const { evolveproCsvPath } = get();
    if (evolveproCsvPath && strategy !== "none") get().loadEvolveproCsv(evolveproCsvPath);
  },

  setPositionDiversityEnabled: (enabled: boolean) => {
    set({ positionDiversityEnabled: enabled });
    const { evolveproCsvPath } = get();
    if (evolveproCsvPath) get().loadEvolveproCsv(evolveproCsvPath);
  },

  setMaxPerPosition: (n: number) => {
    set({ maxPerPosition: Math.max(1, n) });
    const { evolveproCsvPath } = get();
    if (evolveproCsvPath) get().loadEvolveproCsv(evolveproCsvPath);
  },

  setDomainDiversityEnabled: (enabled: boolean) => {
    set({ domainDiversityEnabled: enabled });
    const { evolveproCsvPath } = get();
    if (evolveproCsvPath) get().loadEvolveproCsv(evolveproCsvPath);
  },

  setDomainStrategy: (strategy: "proportional" | "equal") => {
    set({ domainStrategy: strategy });
    const { evolveproCsvPath } = get();
    if (evolveproCsvPath) get().loadEvolveproCsv(evolveproCsvPath);
  },

  fetchDomains: async (accession: string) => {
    set({ domainLoading: true, statusMessage: "Fetching domain info..." } as Partial<InputSlice>);
    try {
      const result = await sendRequest<FetchDomainsResult>("fetch_domains", { accession });
      set({
        uniprotAccession: accession,
        domains: result.domains,
        disabledDomains: new Set<string>(),
        domainLoading: false,
        statusMessage: result.domains.length > 0
          ? `Domains: ${result.domains.length} found (${result.source})`
          : result.error_msg ? `Domain fetch failed: ${result.error_msg}` : "No domains found",
      } as Partial<InputSlice>);
      const { evolveproCsvPath } = get();
      if (evolveproCsvPath && result.domains.length > 0) get().loadEvolveproCsv(evolveproCsvPath);
    } catch (err) {
      set({ domainLoading: false, statusMessage: `Domain fetch failed: ${formatError(err)}` } as Partial<InputSlice>);
    }
  },

  setDomains: (domains: DomainInfo[]) => {
    set({ domains, disabledDomains: new Set<string>() });
    const { evolveproCsvPath, domainDiversityEnabled } = get();
    if (evolveproCsvPath && domainDiversityEnabled) get().loadEvolveproCsv(evolveproCsvPath);
  },

  toggleDomain: (domainKey: string) => {
    const next = new Set(get().disabledDomains);
    if (next.has(domainKey)) next.delete(domainKey);
    else next.add(domainKey);
    set({ disabledDomains: next });
    const { evolveproCsvPath, domainDiversityEnabled } = get();
    if (evolveproCsvPath && domainDiversityEnabled) get().loadEvolveproCsv(evolveproCsvPath);
  },

  setParetoDiversityEnabled: (enabled: boolean) => {
    set({ paretoDiversityEnabled: enabled });
    const { evolveproCsvPath } = get();
    if (evolveproCsvPath) get().loadEvolveproCsv(evolveproCsvPath);
  },

  loadEvolveproCsv: async (filepath: string) => {
    const gen = ++csvLoadGeneration;
    try {
      const { positionDiversityEnabled, maxPerPosition, domainDiversityEnabled, domains, disabledDomains, domainStrategy, paretoDiversityEnabled } = get();
      const maxPrimers = (get() as unknown as { maxPrimers: number }).maxPrimers;
      const activeDomains = domains.filter((d) => !disabledDomains.has(`${d.name}-${d.start}`));
      set({ statusMessage: "Loading EVOLVEpro CSV...", evolveproCsvPath: filepath } as Partial<InputSlice>);
      const result = await sendRequest<EvolveproLoadResult>(
        "load_evolvepro_csv",
        {
          filepath,
          top_n: maxPrimers,
          ...(positionDiversityEnabled && { max_per_position: maxPerPosition }),
          ...(domainDiversityEnabled && activeDomains.length > 0 && {
            domain_diversity: true,
            domains: activeDomains.map((d) => ({ name: d.name, start: d.start, end: d.end })),
            domain_strategy: domainStrategy,
          }),
          ...(paretoDiversityEnabled && { pareto_diversity: true }),
        },
      );
      if (gen !== csvLoadGeneration) return;
      const yMap: Record<string, number> = {};
      result.variants.forEach((v, i) => { yMap[v] = result.y_preds[i] ?? 0; });
      const variantText = result.variants.join("\n");
      const filteredMsg = result.filtered_count
        ? ` (${result.filtered_count} filtered, max ${maxPerPosition}/pos)`
        : "";
      const domainMsg = result.domain_stats
        ? " | " + Object.entries(result.domain_stats).map(([name, s]) =>
            s.selected < s.quota
              ? `${name}: ${s.selected}/${s.quota} \u26A0`
              : `${name}: ${s.selected}/${s.quota}`
          ).join(", ")
        : "";
      const paretoMsg = result.pareto_replaced != null && result.pareto_replaced > 0
        ? ` | Pareto: ${result.pareto_replaced} diversified`
        : "";
      set({
        mutationText: variantText,
        mutationInputMode: "evolvepro",
        yPredMap: yMap,
        domainStats: result.domain_stats ?? {},
        statusMessage: `EVOLVEpro: ${result.selected_count}/${result.total_count} variants${filteredMsg}${domainMsg}${paretoMsg}`,
      } as Partial<InputSlice>);
    } catch (err) {
      if (gen === csvLoadGeneration) {
        set({ statusMessage: `EVOLVEpro CSV load failed: ${formatError(err)}` } as Partial<InputSlice>);
      }
    }
  },

  parseMutations: async () => {
    const { mutationText } = get();
    try {
      const result = await sendRequest<ParseMutationsResult>(
        "parse_mutations_text",
        { text: mutationText },
      );
      set({ parsedMutations: result.parsed, parseErrors: result.errors });
    } catch (err) {
      set({ statusMessage: `Mutation parse failed: ${formatError(err)}` } as Partial<InputSlice>);
    }
  },
});
