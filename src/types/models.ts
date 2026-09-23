import type { SortingState } from "@tanstack/react-table";
import type { SettingsBundle } from "./models.generated";

/** TypeScript interfaces for KURO JSON-RPC communication. */

export type MutationInputMode = "text" | "evolvepro";
export type CodonStrategy = "closest" | "optimal";
export type OverlapMode = "partial" | "full";

export interface PolymeraseInfo {
  name: string;
  manufacturer: string;
  fidelity: string;
  proofreading?: boolean | null;
}

/**
 * One rule outcome the codon-table validator reports about a table it accepted.
 *
 * `code` is one of the strings in `MESSAGE_CODES`
 * (kuma_core/kuro/codon_import.py); `params` carries exactly the
 * `{{placeholder}}` names the locale string for that code interpolates.
 * `src/lib/codonTableMessages.ts` owns the code -> locale-key mapping, so
 * nothing here needs to know what a code means.
 */
export interface CodonTableFinding {
  code: string;
  params: Record<string, unknown>;
}

/**
 * One codon table as `list_organisms` reports it.
 *
 * `taxid` is nullable because the backend emits `data.get("taxid")`
 * (kuma_core/kuro/codon_table.py) and a table JSON is not required to carry
 * the field. An in-house strain legitimately has none. The result is
 * validated element-by-element, so declaring `taxid` as a plain number would
 * make a single taxid-less table reject the WHOLE payload and leave the
 * organism dropdown empty.
 *
 * `cds_count` is nullable for the same reason: a hand-written table declares no
 * `n_cds` and the backend cannot invent one.
 */
export interface OrganismSummary {
  key: string;
  name: string;
  taxid: number | null;
  source: "builtin" | "user";
  aliases: string[];
  cds_count: number | null;
  table_sha256: string;
  warnings: CodonTableFinding[];
  /**
   * What the import silently changed (N1, N2, N4).
   *
   * The backend built these findings and then dropped them, so their thirty
   * locale strings were unreachable from any production path. They are
   * advisories, not defects: the table loaded, and this says what it looked
   * like before it did.
   */
  normalizations: CodonTableFinding[];
  /**
   * The whole table as a self-contained JSON object.
   *
   * Optional so a sidecar built before Phase 2 still parses. When absent the
   * workspace cannot embed this table and a digest disagreement cannot be
   * explained amino acid by amino acid; both degrade to the digest-only path
   * rather than to a wrong answer.
   */
  document?: CodonTableDocument;
}

/**
 * A codon table in the shape its file on disk has.
 *
 * Built by the backend from what the validator normalised rather than from the
 * bytes it read, so writing this object to `<key>.json` and validating it again
 * yields the same `table_sha256` (kuma_core/kuro/codon_table.py,
 * `_document_from_report`). That property is what makes the workspace embed
 * installable: a restore that produced a table with a different digest than the
 * project recorded would hit the mismatch branch it was meant to resolve.
 *
 * The traceability fields (`provenance`, `counts`, the assembly labels) ride
 * along under the index signature. None of them enters the canonical digest.
 */
export interface CodonTableDocument {
  key: string;
  name: string;
  taxid: number | null;
  source: string;
  genetic_code: number;
  aliases: string[];
  codons: Record<string, [string, number][]>;
  [field: string]: unknown;
}

/**
 * One file in the user codon-table folder that did not become an organism.
 *
 * `code` is the FIRST error code the validator raised (V1-V35), or the runtime
 * rule `R5` when a user file is shadowed by a bundled table of the same stem.
 * `reason` is the backend's English detail text, joined with `; ` when several
 * rules fired, and stays as the fallback for a sidecar older than `findings`.
 *
 * `findings` carries every error with its `params`, which is what
 * `formatCodonTableMessage` needs to rebuild the sentence in the active locale.
 * Every error and not only the first: `reason` already joins them all, so
 * localizing one code would drop the rest of what the file got wrong.
 */
export interface CodonTableFailure {
  filename: string;
  code: string;
  reason: string;
  findings?: CodonTableFinding[];
}

/**
 * The `list_organisms` envelope.
 *
 * Calling `list_organisms` IS the refresh action: the handler drops the
 * registry caches, seeds the user folder and re-reads both directories
 * (python-core/sidecar_kuro/handlers/misc.py, `handle_list_organisms`). There
 * is no separate refresh RPC in Phase 1.
 *
 * `user_dir` is the absolute path the sidecar actually resolved, not one the
 * frontend reconstructs: `kuma_home()` reads `HOME` before `Path.home()`, so a
 * guess would be wrong for any Windows process that inherited an MSYS
 * environment.
 */
export interface ListOrganismsResult {
  organisms: OrganismSummary[];
  failed: CodonTableFailure[];
  user_dir: string;
}

/**
 * One finding as the import RPC reports it.
 *
 * `CodonTableFinding` plus the backend's English `detail`. The import path
 * carries the detail because it can fail before any rule runs -- a CSV whose
 * columns cannot be located (V36) has its specifics only in that string --
 * whereas `list_organisms` already joins its details into `reason`.
 */
export interface CodonTableImportFinding extends CodonTableFinding {
  detail?: string;
}

/**
 * What `import_codon_table` reports.
 *
 * `ok` and `installed` are two different facts. A `dry_run` that passes every
 * rule is `ok` and not `installed`, and that is the preview: the dialog shows
 * exactly the findings the real import would produce, from the same call with
 * one flag flipped, so preview and import cannot drift apart.
 *
 * `checks_performed` and `codons_examined` are surfaced rather than kept in
 * the backend because "no problems found" from zero checks and "no problems
 * found" from two hundred checks must not read the same on screen.
 *
 * `normalizations` is what the import silently changed (N1 U-to-T, N2 case,
 * N4 fractions recomputed from counts). Phase 2 made these reachable in the
 * listing; the preview is where they are actually useful, because this is the
 * one moment the user can still decide not to install the table.
 */
export interface ImportCodonTableResult {
  ok: boolean;
  installed: boolean;
  key: string;
  table_sha256: string | null;
  errors: CodonTableImportFinding[];
  warnings: CodonTableImportFinding[];
  normalizations: CodonTableImportFinding[];
  checks_performed: number;
  codons_examined: number;
  /** The document as it was or would be written. Null when the table was rejected. */
  document: CodonTableDocument | null;
  /** Where it was written. Null for a dry run and for a rejection. */
  path: string | null;
}

export interface ImportCodonTableParams {
  format: "json" | "csv" | "cusp" | "kazusa";
  key: string;
  filepath?: string;
  text?: string;
  name?: string;
  taxid?: number | null;
  genetic_code?: number;
  aliases?: string[];
  source?: string;
  overwrite?: boolean;
  dry_run?: boolean;
}

/**
 * Parameters for `export_codon_table`.
 *
 * No Kazusa. It is an input format only: the stored canonical form is decided
 * and a fourth spelling kuma would have to read back is a second canon.
 */
export interface ExportCodonTableParams {
  key: string;
  format: "json" | "csv" | "cusp";
  filepath: string;
}

export interface ExportCodonTableResult {
  path: string;
  format: string;
  bytes: number;
}

export interface PolymeraseProfile {
  name: string;
  tm_method: string;
  salt_correction: string;
  opt_tm: number;
  min_tm: number;
  max_tm: number;
  min_gc: number;
  max_gc: number;
  salt_monovalent: number;
  salt_divalent: number;
  dntp_conc: number;
  dna_conc: number;
  opt_tm_fwd?: number | null;
  opt_tm_rev?: number | null;
  opt_tm_overlap?: number | null;
  min_3prime_dist?: number;
  overlap_len?: number | null;
  fwd_len_min?: number | null;
  fwd_len_max?: number | null;
  rev_len_min?: number | null;
  rev_len_max?: number | null;
  default_overlap_mode?: OverlapMode | null;
  proofreading?: boolean | null;
}

export interface GeneInfo {
  gene: string;
  product: string;
  cds_start: number;
  cds_end: number;
  aa_length: number;
  organism?: string;
  organism_key?: string | null;
  translation?: string;
  uniprot_accession?: string;
}

export interface UniprotCandidate {
  accession: string;
  name: string;
  organism: string;
  length: number;
  identity: number;
  has_structure?: boolean;
  subunit?: string | null;
  oligomeric?: "monomer" | "multimer" | "unknown";
}

export interface SearchUniprotResult {
  candidates: UniprotCandidate[];
  auto_selected: string | null;
  error_detail?: string | null;
}

export interface StructureAvailabilityResult {
  availability: Record<string, boolean>;
}

export interface SequenceInfo {
  header: string;
  seq_length: number;
  genes: GeneInfo[];
}

export interface ParsedMutation {
  raw: string;
  wt_aa: string;
  position: number;
  mt_aa: string;
}

export interface ParseError {
  line: number;
  raw: string;
  reason: string;
}

export interface ParseMutationsResult {
  parsed: ParsedMutation[];
  errors: ParseError[];
}

export interface AlternativesResult {
  mutation?: string;
  count?: number;
  candidates: SdmPrimerResult[];
}

export interface OffTargetHit {
  position: number;
  strand: "sense" | "antisense";
  match_seq: string;
  tm: number;
  match_length: number;
}

export interface SdmPrimerResult {
  mutation: string;
  aa_position: number;
  codon_pos: number;
  forward_seq: string;
  reverse_seq: string;
  fwd_len: number;
  rev_len: number;
  overlap_len: number;
  candidate_count?: number;
  candidate_fwd_count?: number;
  candidate_rev_count?: number;
  tm_no_fwd: number;
  tm_no_rev: number;
  tm_overlap: number;
  tm_condition_met: boolean;
  tolerance_used: number;
  tolerance_fwd?: number;
  tolerance_rev?: number;
  has_offtarget: boolean;
  offtarget_fwd?: OffTargetHit[];
  offtarget_rev?: OffTargetHit[];
  penalty: number;
  gc_fwd: number;
  gc_rev: number;
  wt_codon: string;
  mt_codon: string;
  overlap_seq: string;
  hairpin_tm_fwd?: number;
  hairpin_tm_rev?: number;
  homodimer_tm_fwd?: number;
  homodimer_tm_rev?: number;
  hairpin_dg_fwd?: number;
  hairpin_dg_rev?: number;
  homodimer_dg_fwd?: number;
  homodimer_dg_rev?: number;
  // Per-structure warning verdicts from the engine
  // (sdm_engine.secondary_structure_warn_flags): hairpin warns when its
  // folded fraction at the pair's recommended Ta exceeds the engine limit,
  // homodimer on the absolute design-scale Tm. Absent on rows serialized
  // before the fields existed and cleared wherever pair Ta is unknown.
  hairpin_warn_fwd?: boolean;
  hairpin_warn_rev?: boolean;
  homodimer_warn_fwd?: boolean;
  homodimer_warn_rev?: boolean;
  synthesis_score_fwd?: number;
  synthesis_score_rev?: number;
  recommended_ta?: number | null;
  ta_mode?: "3step" | "2step" | "fixed";
  ta_detail?: string;
  ta_touchdown?: string | null;
  warnings: string[];
  overlap_mode?: "partial" | "full";
}

export interface DomainInfo {
  name: string;
  id: string;         // InterPro/Pfam ID (e.g. "PF01397")
  start: number;      // 1-based residue position
  end: number;
  db: string;         // "Pfam" | "InterPro" | "manual"
}

export interface FetchDomainsResult {
  accession: string;
  domains: DomainInfo[];
  source: "interpro_api" | "manual" | "error";
  protein_length?: number;
  error_msg?: string;
}
export interface AnnotateDomainsResult {
  domains: DomainInfo[];
  source: "interproscan" | "error";
  coordinate_frame: "reference";
  protein_length: number;
  ref_hash: string;
  cache_hit: boolean;
  error_msg?: string;
}


export interface DomainStat {
  quota: number;
  selected: number;
}

export interface EvolveproStepStats {
  position_filter_removed?: number | null;
  domain_selected?: number | null;
  pareto_exchanges?: number | null;
  start_codon_removed?: number | null;
  start_codon_removed_variants?: string[] | null;
}

export interface EvolveproLoadResult {
  variants: string[];
  y_preds: number[];
  total_count: number;
  selected_count: number;
  filtered_count?: number;
  domain_stats?: Record<string, DomainStat>;
  pareto_replaced?: number;
  pool_variants?: string[];
  used_variant_column?: string | null;
  used_score_column?: string | null;
  step_stats?: EvolveproStepStats;
  /** True when the loaded structure did not exactly cover the reference frame,
   *  so 3D Cα coordinates were dropped and structural/pareto selection fell back
   *  to 1-D sequence distance. */
  structure_frame_mismatch?: boolean;
  /** Ranked candidates beyond the selected set: selected + up to BUFFER_CAP extras, y_pred desc. */
  ranked_candidates?: import("./models.generated").RankedCandidateItem[];
  /**
   * Variants dropped for carrying a position-1 substitution, counted and named.
   *
   * `load_evolvepro_csv` returns these at the TOP level of its dict
   * (`kuma_core/kuro/evolvepro.py:715-716`) as well as inside `step_stats`
   * (`:721-722`), and `handle_load_evolvepro_csv` passes the dict through
   * without filtering (`python-core/sidecar_kuro/handlers/misc.py:236-237`).
   * Only the nested copies were modelled, so the top-level pair was invisible.
   *
   * Unlike the `step_stats` copies these are never null: the count is
   * `len(...)` and the list a comprehension (`evolvepro.py:583-585`), so an
   * empty list and 0 are what "none removed" looks like. Optional only because
   * a result persisted before this field was modelled replays verbatim.
   */
  start_codon_removed?: number;
  start_codon_removed_variants?: string[];
}

export interface EvolveproPreview {
  sheets: string[];
  headers: string[];
  rows: string[][];
}

export interface FailedMutation {
  mutation: string;
  rank: number;
  reason: string;
}

export interface RescuedMutation {
  original: string;
  rescued_by: string;
  type:
    | "pool_cascade"
    | "auto_relax"
    | "auto_suggestion"
    | "same_position"
    | "diff_position"
    | "auto_suggestion_l1"
    | "auto_suggestion_l2"
    | "auto_suggestion_l3"
    | "auto_suggestion_l4";
  penalty?: number;
  tolerance_used?: number;
  stage?: number;       // 1-6 cascade stage marker
  substitute?: string;  // new mutation string when type is same/diff_position
}

export interface RescueStats {
  pool_cascade: number;
  auto_relax: number;
  positions_attempted: number;
  pool_variants_tried: number;
}

/**
 * How the most recent design run ended.
 *
 * "interrupted" is a run whose sidecar went away mid-request (menu restart or
 * an update install); the backend may well have finished, but the answer never
 * reached the store.
 */
export type DesignRunOutcome = "success" | "failed" | "cancelled" | "interrupted";

/**
 * Trace of the most recent design run, kept so an empty result table can tell
 * "never ran" apart from "ran and the results are gone". Session-scoped: it is
 * not written to the autosave snapshot, and unlike the result fields it is not
 * cleared by buildKuroResultResetPatch (that is the whole point of it).
 */
export interface DesignRunRecord {
  outcome: DesignRunOutcome;
  /** Epoch ms at which the run ended. */
  finishedAt: number;
  successCount: number;
  totalCount: number;
  failedCount: number;
  /** Error text or cancel reason; null when there is nothing to add. */
  detail: string | null;
}

export interface DesignResult {
  results: SdmPrimerResult[];
  success_count: number;
  total_count: number;
  failed_mutations: FailedMutation[];
  rescue_stats?: RescueStats;
  rescued_mutations?: RescuedMutation[];
  cancelled?: boolean;
}

export interface PlateMapping {
  well: string;
  primer_name: string;
  sequence: string;
  primer_type: "forward" | "reverse";
  mutation: string;
  tm?: number;
  tm_overlap?: number;
  wt_codon?: string;
  mt_codon?: string;
}

export interface PlateMapResult {
  mappings: PlateMapping[];
  dedup_info: Record<string, string[]>;
}

export interface ExportResult {
  success: boolean;
  filepath: string;
  /**
   * The run manifest written beside the export.
   *
   * All three export handlers call `write_run_manifest` and then attach the
   * path unconditionally (`python-core/sidecar_kuro/handlers/export.py:318-323`,
   * `:375-380`, `:473-478`), so a live sidecar always sends a string. Optional
   * on the type only because a result persisted before these keys existed
   * replays verbatim and has nothing to fall back to.
   */
  manifest_path?: string;
  /** The checksum file written beside the export. Same reasoning as above. */
  checksum_path?: string;
}

export interface SaveCustomPolymeraseResult {
  success: boolean;
  name: string;
}

export interface ExportOrderResult extends ExportResult {
  format: "idt" | "twist";
  primer_count: number;
}

/**
 * The two column parities of a 384 Echo source plate a round can occupy: "A1"
 * is the odd columns 1, 3 ... 23 and "A2" the even columns 2, 4 ... 24. A
 * 96-head stamp skips every other column, which is why a round is a parity
 * rather than a contiguous block. Forward primers sit on the even rows and
 * their reverses one row below, so a round is 192 wells and one plate holds
 * two of them. Mirrors kuma_core/kuro/plate_quadrant.QUADRANTS.
 */
export type EchoQuadrant = "A1" | "A2";

/**
 * What a saved project's `quadrant` field may hold. "B1" and "B2" are
 * interleaved-era names for these same rounds seen from their reverse rows,
 * so `foldPersistedPlacement` in lib/echoQuadrant.ts folds them onto "A1" and
 * "A2" without moving a single source well. "A13" is the right-half name
 * written between v0.16.61 and the release that restored this geometry, and
 * it folds onto neither: a block of twelve consecutive columns covers part of
 * both rounds, so such a placement reads as both rounds spent and none
 * selected. A stored "A1" or "A2" is dated by the saved app version, because
 * the half era spelled them the same. Nothing this app writes is outside
 * {@link EchoQuadrant}.
 */
export type PersistedEchoQuadrant = EchoQuadrant | "A13" | "B1" | "B2";

export interface ExportMappingResult extends ExportResult {
  format: "echo" | "janus";
  primer_count: number;
}

export interface WorkspaceV1 {
  version: 1;
  fastaPath: string;
  mutationInputMode: MutationInputMode;
  mutationText: string;
  evolveproCsvPath: string;
  selectedGene: string;
  codonStrategy: CodonStrategy;
  maxPrimers: number;
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;
  failedMutations: FailedMutation[];
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
  tableSorting: SortingState;
  manuallySwapped: Record<string, string>;
  customCandidates: Record<string, SdmPrimerResult[]>;
  tmFwdTarget: number;
  tmRevTarget: number;
  tmOverlapTarget: number;
  gcMin: number;
  gcMax: number;
  primerLenEnabled?: boolean;
  fwdLenMin?: number;
  fwdLenMax?: number;
  revLenMin?: number;
  revLenMax?: number;
  fillOnFailure?: boolean;
  tmTolerance?: number;
  // Domain diversity (optional, backward-compatible)
  uniprotAccession?: string;
  domains?: DomainInfo[];
  domainDiversityEnabled?: boolean;
  domainStrategy?: "proportional" | "equal";
  paretoDiversityEnabled?: boolean;
  structuralDiversityEnabled?: boolean;
  structuralKappa?: number;
  disabledDomains?: string[];
  rescuedMutations?: string[];
  entropyWeightEnabled?: boolean;
  entropyWeight?: number;
  organism?: string;
  pipelineMode?: boolean;
  positionDiversityEnabled?: boolean;
  maxPerPosition?: number;
  evolveproRound?: number;
  roundSize?: number;
  overlapMode?: OverlapMode;
  evolveproTotalCount?: number;
  evolveproFilteredCount?: number | null;
  evolveproParetoExchanges?: number | null;
  evolveproStepStats?: EvolveproStepStats | null;
}

export type DistanceMode = "auto" | "1d" | "3d";
export type DomainStrategy = "proportional" | "equal";
export type DomainOverlapPolicy = "first" | "largest";
export type LinkerHandling = "include" | "exclude" | "separate-bin";

export interface WorkspaceInputs {
  fastaPath: string;
  mutationInputMode: MutationInputMode;
  mutationText: string;
  evolveproCsvPath: string;
  selectedGene: string;
  /**
   * Path to the "Others" mode mutation source file (CSV/TSV/XLSX).
   * Optional for backward compatibility with workspaces saved before
   * this field existed. Empty string or undefined = no file selected.
   */
  othersSourcePath?: string;
}

export interface WorkspaceSettings {
  selectedPolymerase?: string;
  codonStrategy: CodonStrategy;
  maxPrimers: number;
  tmFwdTarget: number;
  tmRevTarget: number;
  tmOverlapTarget: number;
  gcMin: number;
  gcMax: number;
  primerLenEnabled?: boolean;
  fwdLenMin?: number;
  fwdLenMax?: number;
  revLenMin?: number;
  revLenMax?: number;
  fillOnFailure?: boolean;
  tmTolerance?: number;
  uniprotAccession?: string;
  domains?: DomainInfo[];
  refDomains?: DomainInfo[];
  refDomainHash?: string;
  structureAccession?: string;
  structureLoaded?: boolean;
  domainDiversityEnabled?: boolean;
  domainStrategy?: "proportional" | "equal";
  domainOverlapPolicy?: DomainOverlapPolicy;
  linkerHandling?: LinkerHandling;
  domainQuotaMin?: number;
  paretoDiversityEnabled?: boolean;
  structuralDiversityEnabled?: boolean;
  structuralKappa?: number;
  disabledDomains?: string[];
  rescuedMutations?: string[];
  entropyWeightEnabled?: boolean;
  entropyWeight?: number;
  paretoPoolMultiplier?: number;
  distanceMode?: DistanceMode;
  benchmarkTopPercentile?: number;
  benchmarkRandomTrials?: number;
  benchmarkRandomSeed?: number | null;
  autoRedesignOnLoad?: boolean;
  saveCache?: boolean;
  organism?: string;
  pipelineMode?: boolean;
  /**
   * EVOLVEpro selection mode tri-state. When present, takes priority over
   * `pipelineMode` on restore. Optional for backward compatibility.
   */
  evolveproMode?: "topN" | "pipeline" | "others";
  positionDiversityEnabled?: boolean;
  maxPerPosition?: number;
  evolveproRound?: number;
  roundSize?: number;
  overlapMode?: OverlapMode;
  /** §12 Optional RNG seed for reproducible design runs. */
  randomSeed?: number | null;
  echoTransferVol?: number;
  /**
   * Persisted, so it is read with the legacy value set. The store only ever
   * holds an {@link EchoQuadrant}, so saving cannot write a legacy name;
   * loading reads the pair through `foldPersistedPlacement` together with the
   * saved app version.
   */
  echoQuadrant?: PersistedEchoQuadrant | null;
  echoUsedQuadrants?: PersistedEchoQuadrant[];
  janusTransferVol?: number;
}

export interface WorkspaceResults {
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;
  failedMutations: FailedMutation[];
  excludedDesignMutations?: string[];
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
  manuallySwapped: Record<string, string>;
  customCandidates: Record<string, SdmPrimerResult[]>;
  rescuedMutationDetails?: RescuedMutation[];
}

export interface WorkspaceUi {
  tableSorting: SortingState;
}

export interface WorkspaceCache {
  evolveproTotalCount?: number;
  evolveproFilteredCount?: number | null;
  evolveproParetoExchanges?: number | null;
  evolveproStepStats?: EvolveproStepStats | null;
  benchmarkResults?: Record<string, BenchmarkResult> | null;
}

export interface WorkspaceV2 {
  version: 2;
  inputs: WorkspaceInputs;
  settings: WorkspaceSettings;
  results: WorkspaceResults;
  ui: WorkspaceUi;
  cache?: WorkspaceCache;
}

/**
 * WorkspaceV3 — schema_version "0.3" (string discriminator).
 * rounds: Round[] + active_round_id 추가.
 * v0.3 이전 워크스페이스 로드 시 throw.
 */
export interface WorkspaceV3 {
  schema_version: "0.3";
  /**
   * Build that wrote the file, the same `__APP_VERSION__` stamp the autosave
   * snapshot carries. Optional because files written before this field exists
   * do not have it, and that absence places the file before v0.16.61, in the
   * interleaved era whose stored Echo placement already means a column parity
   * (`foldPersistedPlacement`).
   */
  kuma_version?: string;
  inputs: WorkspaceInputs;
  settings: WorkspaceSettings;
  results: WorkspaceResults;
  ui: WorkspaceUi;
  cache?: WorkspaceCache;
  rounds: import("./round").Round[];
  active_round_id: string | null;
  /**
   * The codon table this project designed with, in full.
   *
   * About 3.5 KB, and the whole table rather than a key, because a workspace is
   * the artifact that travels: opened on a machine that never had the file, a
   * key alone would name something nobody can produce. Written only for a
   * user-installed table; a bundled one is identified by its key, which the app
   * ships (design note section 8.2).
   *
   * Optional, and its absence is not a defect: every workspace saved before
   * Phase 2 lacks it, and those restore exactly as they did before.
   */
  codon_table?: CodonTableDocument | null;
  /**
   * The canonical digest of that table, recorded for a bundled table too.
   *
   * Separate from `codon_table` because it is a property of the backend's
   * normalisation, not of the document text, and because a bundled table needs
   * the digest without the body: a later build can ship different numbers under
   * a key this file names, and nothing but the digest would notice.
   */
  codon_table_sha256?: string | null;
}

export type WorkspaceData = WorkspaceV1 | WorkspaceV2 | WorkspaceV3;

export interface StructureResult {
  success: boolean;
  accession?: string;
  residues?: number;
  error?: string;
}

export interface StructureModelCandidate {
  name: string;
  ranking_score?: number | null;
  mean_plddt?: number | null;
  residue_count: number;
}

export interface LoadStructureFileResult {
  success: boolean;
  accession?: string;
  residues?: number;
  mean_plddt?: number | null;
  source_name?: string;
  selection_metric?: string;
  candidates?: StructureModelCandidate[];
  error?: string;
}

export interface FetchInterfaceResiduesResult {
  interface_positions: number[];
  source: string;
  pdb_id?: string;
  chains?: string[];
  oligomeric_state?: string | null;
  error?: string;
  note?: string;
}
export interface FetchPdbTextResult {
  success: boolean;
  accession: string;
  pdb_text: string | null;
  source: string;
}

export interface PredictStructureEsmfoldResult {
  success: boolean;
  source: "esmfold" | "esmfold_cache" | "error";
  pdb_text: string | null;
  plddt_mean: number;
  residue_count: number;
  coordinate_frame: "reference";
  seq_hash: string;
  cache_hit: boolean;
  error_msg?: string;
}

export interface FetchActiveSiteResult {
  accession: string;
  active_site_positions: number[];
  binding_positions: number[];
  source: string;
  has_annotation: boolean;
}

export interface ComputeDispersionResult {
  accession: string;
  mapped: number[];
  dropped: number[];
  n_positions: number;
  mean_pairwise: number;
  null_mean: number;
  null_p05: number;
  null_p95: number;
  percentile: number;
  klass: string;
  n_trials: number;
  seed: number | null;
  null_hist: { min: number; max: number; counts: number[] };
}


export interface BenchmarkResult {
  n_selected: number;
  hit_rate: number;
  mean_fitness: number;
  unique_positions: number;
  position_coverage: number;
  domain_coverage: number;
  structural_spread: number;
  hits: number;
  threshold: number;
  n_trials?: number;
}

export interface RunBenchmarkResult {
  results: Record<string, BenchmarkResult>;
  // True when a loaded structure did not cover the reference frame, so the
  // benchmark ran on 1D distance instead of 3D. Same guard as load_evolvepro.
  structure_frame_mismatch?: boolean;
}

export interface JsonRpcError {
  code: number;
  message: string;
}

export interface CancelDesignResult {
  cancelled: boolean;
  active_design?: boolean;
}

export type RpcParams = Record<string, unknown>;

/**
 * `health_info` result. Both sidecars build this dict literally and identically:
 * `python-core/sidecar_kuro/dispatcher.py:69-82` and
 * `python-core/sidecar_mame/dispatcher.py:59-72` each return
 * `{"pid": os.getpid(), "rss_bytes": <int>, "py_version": <str>}`.
 *
 * `rss_bytes` is 0 rather than absent when `kuma_core.shared.memory_monitor` is
 * missing, so the field is always present and always a number; the validator
 * requires it instead of treating it as optional.
 */
export interface HealthInfo {
  pid: number;
  rss_bytes: number;
  py_version: string;
}

export interface RpcMethodMap {
  /**
   * Status-bar and crash-report probe. Present on both dispatchers under the
   * same name and with the same result, so the MAME table in
   * `src/types/mame/validators.ts` guards it with the same shape.
   */
  health_info: {
    params: Record<string, never>;
    result: HealthInfo;
  };
  list_polymerases: {
    params: Record<string, never>;
    result: PolymeraseInfo[];
  };
  get_polymerase_details: {
    params: { name: string };
    result: PolymeraseProfile;
  };
  save_custom_polymerase: {
    params: PolymeraseProfile;
    result: SaveCustomPolymeraseResult;
  };
  list_organisms: {
    params: Record<string, never>;
    result: ListOrganismsResult;
  };
  import_codon_table: {
    params: ImportCodonTableParams;
    result: ImportCodonTableResult;
  };
  export_codon_table: {
    params: ExportCodonTableParams;
    result: ExportCodonTableResult;
  };
  load_fasta: {
    params: { filepath: string };
    result: SequenceInfo;
  };
  parse_mutations_text: {
    params: { text: string };
    result: ParseMutationsResult;
  };
  design_sdm_primers: {
    params: RpcParams;
    result: DesignResult;
  };
  load_evolvepro_csv: {
    params: RpcParams;
    result: EvolveproLoadResult;
  };
  preview_evolvepro_source: {
    params: RpcParams;
    result: EvolveproPreview;
  };
  get_plate_map: {
    params: Record<string, never>;
    result: PlateMapResult;
  };
  get_alternatives: {
    params: { mutation: string };
    result: AlternativesResult;
  };
  swap_primer: {
    params: { mutation: string; candidate_idx: number; swap_type: "both" | "fwd" | "rev" };
    result: SdmPrimerResult;
  };
  commit_design_result: {
    params: { mutation: string; candidate_idx: number };
    result: SdmPrimerResult;
  };
  export_excel: {
    params: RpcParams;
    result: ExportResult;
  };
  export_order: {
    params: RpcParams & { bom?: boolean };
    result: ExportOrderResult;
  };
  export_mapping: {
    params: RpcParams & {
      bom?: boolean;
      mapping_range?: { row_start: string; row_end: string } | null;
      /**
       * Column parity of the 384 source plate this round fills: "A1" is the
       * odd columns and "A2" the even ones. The reverse primer sits one 384
       * row below its forward primer in the same column. Takes precedence over
       * mapping_range, which cannot express a column offset. Echo only. A half
       * name from v0.16.61 is refused by the sidecar rather than folded, so
       * only {@link EchoQuadrant} may be sent.
       */
      quadrant?: EchoQuadrant | null;
      /** Quadrants already spent on a part-used plate, stated by the operator. */
      used_quadrants?: EchoQuadrant[];
    };
    result: ExportMappingResult;
  };
  export_echo_mapping_dry_run: {
    params: {
      transfer_vol?: number;
      mappings?: PlateMapping[];
      dedup_info?: Record<string, string[]>;
      mapping_range?: { row_start: string; row_end: string } | null;
      /**
       * Same placement parameters export_mapping takes, so the preview and the
       * exported csv name the same source wells. quadrant outranks
       * mapping_range, and a quadrant already listed in used_quadrants is
       * refused here as it is on export.
       */
      quadrant?: EchoQuadrant | null;
      used_quadrants?: EchoQuadrant[];
    };
    result: {
      rows: Array<{
        source_plate: string;
        source_well_name: string;
        source_well: string;
        dest_plate: string;
        dest_well_name: string;
        dest_well: string;
        transfer_vol: number;
        mutation: string;
      }>;
      total: number;
      transfer_vol: number;
    };
  };
  export_janus_mapping_dry_run: {
    params: {
      transfer_vol?: number;
      mappings?: PlateMapping[];
      dedup_info?: Record<string, string[]>;
      mapping_range?: { row_start: string; row_end: string } | null;
    };
    result: {
      // The first eight fields are the instrument sheet columns, in
      // JANUS_DEVICE_HEADER order (kuma_core/shared/janus_deck.py); `mutation`
      // and `role` ride along for the UI and are never written to a file. The
      // sheet has no liquid class column, so no field carries one.
      rows: Array<{
        name: string;
        type: string;
        no: number;
        // `Asp. Rack` / `Dsp. Rack`: plate NAMES ("fw plate", "rv plate",
        // "PCR mixture plate"), not deck slot numbers.
        asp_rack: string;
        asp_posi: string;
        dsp_rack: string;
        dsp_posi: string;
        volume: number;
        mutation: string;
        // Stated direction of the transfer (kuma_core/kuro/plate_mapper.py
        // build_janus_rows). Optional: a packaged sidecar predating the field
        // omits it, and the preview then leaves the row out, since a plate name
        // chosen by deck policy cannot be read back as a direction.
        role?: "fwd" | "rev";
      }>;
      total: number;
      transfer_vol: number;
    };
  };
  export_macrogen: {
    params: {
      project_id?: string;
      output_path: string;
      fwd_plate_name?: string;
      rev_plate_name?: string;
      amount?: "0.05" | "0.2";
      purification?: "MOPC";
    };
    result: { ok: true; path: string };
  };
  export_all: {
    params: {
      project_id?: string;
      project_name?: string | null;
      output_dir: string;
      fwd_plate_name?: string;
      rev_plate_name?: string;
      amount?: "0.05" | "0.2";
      purification?: "MOPC";
      echo_transfer_vol?: number;
      /** Forward-primer quadrant of the 384 Echo source plate. Echo csv only. */
      quadrant?: EchoQuadrant | null;
      /** Quadrants already spent on a part-used plate, stated by the operator. */
      used_quadrants?: EchoQuadrant[];
      janus_transfer_vol?: number;
      bom?: boolean;
      mappings?: PlateMapping[];
      dedup_info?: Record<string, string[]>;
    };
    result: {
      success: string[];
      failed: { path: string; reason: string }[];
      output_dir: string;
    };
  };
  export_benchmark_csv: {
    params: { filepath: string; results: Record<string, BenchmarkResult>; bom?: boolean };
    result: ExportResult;
  };
  evaluate_primer: {
    params: RpcParams;
    result: SdmPrimerResult;
  };
  retry_failed_mutation: {
    params: RpcParams;
    result: AlternativesResult;
  };
  save_json: {
    params: { filepath: string; data: unknown };
    result: ExportResult;
  };
  save_workspace: {
    params: { filepath: string; data: WorkspaceData };
    result: ExportResult;
  };
  load_workspace: {
    params: { filepath: string };
    result: WorkspaceData;
  };
  fetch_domains: {
    params: { accession: string };
    result: FetchDomainsResult;
  };
  annotate_domains_by_sequence: {
    params: { sequence: string; ref_hash?: string };
    result: AnnotateDomainsResult;
  };
  search_uniprot: {
    params: {
      gene_name: string;
      organism: string;
      translation: string;
      known_accession: string;
      /**
       * Off when the BLAST switch in Settings is off. BLAST is the secondary
       * step here, so switching it off narrows the search to direct accession
       * lookup rather than refusing it.
       */
      use_blast?: boolean;
    };
    result: SearchUniprotResult;
  };
  check_structures_available: {
    params: { accessions: string[] };
    result: StructureAvailabilityResult;
  };
  fetch_structure: {
    params: { accession: string };
    result: StructureResult;
  };
  load_structure_file: {
    params: { filepath: string };
    result: LoadStructureFileResult;
  };
  fetch_interface_residues: {
    params: { accession: string; ref_seq: string };
    result: FetchInterfaceResiduesResult;
  };
  run_benchmark: {
    params: RpcParams;
    result: RunBenchmarkResult;
  };
  cancel_design: {
    params: Record<string, never>;
    result: CancelDesignResult;
  };
  // Phase 3: Settings
  settings_load: {
    params: Record<string, never>;
    result: { settings: SettingsBundle };
  };
  settings_save: {
    params: { settings: SettingsBundle };
    result: { ok: boolean; path: string };
  };
  // G001: 3D Analysis panel RPCs
  fetch_pdb_text: {
    params: { accession: string };
    result: FetchPdbTextResult;
  };
  fetch_active_site_residues: {
    params: { accession: string };
    result: FetchActiveSiteResult;
  };
  compute_dispersion: {
    params: {
      accession: string;
      ref_seq: string;
      positions: number[];
      n_trials?: number;
      seed?: number | null;
      pdb_text?: string | null;
      coordinate_frame?: "accession" | "reference";
    };
    result: ComputeDispersionResult;
  };
  predict_structure_esmfold: {
    params: { sequence: string };
    result: PredictStructureEsmfoldResult;
  };
}

export type RpcMethod = keyof RpcMethodMap;
export type RpcMethodParams<K extends RpcMethod> = RpcMethodMap[K]["params"];
export type RpcMethodResult<K extends RpcMethod> = RpcMethodMap[K]["result"];

// JSON-RPC types

export interface JsonRpcRequest<K extends RpcMethod = RpcMethod> {
  jsonrpc: "2.0";
  id: number;
  method: K;
  params: RpcMethodParams<K>;
}

export interface JsonRpcSuccessResponse<T = unknown> {
  jsonrpc: "2.0";
  id: number;
  result: T;
  error?: never;
}

export interface JsonRpcErrorResponse {
  jsonrpc: "2.0";
  id: number | null;
  result?: never;
  error: JsonRpcError;
}

export interface ReadyNotification {
  jsonrpc: "2.0";
  method: "ready";
  params: Record<string, never>;
}

export interface ProgressNotification {
  value: number;
  message: string;
}

export interface ProgressNotificationMessage {
  jsonrpc: "2.0";
  method: "progress";
  params: ProgressNotification;
}

export type JsonRpcResponse<T = unknown> = JsonRpcSuccessResponse<T> | JsonRpcErrorResponse;
export type JsonRpcNotification = ReadyNotification | ProgressNotificationMessage;
export type JsonRpcMessage = JsonRpcResponse | JsonRpcNotification;
