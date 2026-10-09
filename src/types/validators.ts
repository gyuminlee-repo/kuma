import type {
  AlternativesResult,
  AnnotateDomainsResult,
  CancelDesignResult,
  ComputeDispersionResult,
  DesignResult,
  EvolveproLoadResult,
  EvolveproPreview,
  ExportMappingResult,
  ExportOrderResult,
  ExportResult,
  FetchActiveSiteResult,
  FetchDomainsResult,
  FetchInterfaceResiduesResult,
  FetchPdbTextResult,
  HealthInfo,
  PredictStructureEsmfoldResult,
  PredictionBundleInventory,
  PredictionBundleEvidence,
  JsonRpcError,
  ParseMutationsResult,
  PlateMapResult,
  PolymeraseInfo,
  PolymeraseProfile,
  ProgressNotification,
  RpcMethod,
  RpcMethodResult,
  RunBenchmarkResult,
  SaveCustomPolymeraseResult,
  SearchUniprotResult,
  SequenceInfo,
  SdmPrimerResult,
  StructureAvailabilityResult,
  StructureResult,
  StructureModelCandidate,
  StrictSpatialComparison,
  StrictSpatialProfile,
  StrictSpatialResult,
  LoadStructureFileResult,
  WorkspaceData,
  ContactEmailErrorCode,
} from "./models";
import { CONTACT_EMAIL_REQUIRED } from "./models";

/**
 * True for a plain JSON object, false for `null` and for arrays.
 *
 * The `!Array.isArray` clause is the point. `typeof [] === "object"` and
 * `[] !== null`, so without it every `Record<string, T>` field in this file
 * accepted an array: `isRecordOf` reduces to `Object.values(value).every(guard)`,
 * and `Object.values([])` is `[]`, which satisfies `.every` vacuously. An empty
 * array therefore passed as a populated map, and `src/types/mame/validators.ts`
 * imports this same helper, so its `isRecordOfString` and
 * `isRecordOfFiniteNumber` inherited it too.
 *
 * Tightening here is safe for the top-level `isRecord(value)` calls that open
 * most validators in this file: no KURO or MAME handler returns a bare array for
 * a result those guards cover (`list_polymerases`, the one that still returns a
 * bare list, goes through `isArrayOf` instead; `list_organisms` returns an
 * envelope and is checked by `isListOrganismsResult`).
 */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every(isNumber);
}

function isArrayOf<T>(
  value: unknown,
  guard: (item: unknown) => boolean,
): value is T[] {
  return Array.isArray(value) && value.every(guard);
}

function isRecordOf<T>(
  value: unknown,
  guard: (item: unknown) => boolean,
): value is Record<string, T> {
  return isRecord(value) && Object.values(value).every(guard);
}

function isOptional<T>(
  value: unknown,
  guard: (item: unknown) => boolean,
): value is T | undefined {
  return value === undefined || guard(value);
}

function isOptionalNullable<T>(
  value: unknown,
  guard: (item: unknown) => boolean,
): value is T | null | undefined {
  return value === undefined || value === null || guard(value);
}

function isMutationInputMode(value: unknown): boolean {
  return value === "text" || value === "evolvepro";
}

function isCodonStrategy(value: unknown): boolean {
  return value === "closest" || value === "optimal";
}

function isDomainStrategy(value: unknown): boolean {
  return value === "proportional" || value === "equal";
}

function isDomainOverlapPolicy(value: unknown): boolean {
  return value === "first" || value === "largest";
}

function isLinkerHandling(value: unknown): boolean {
  return value === "include" || value === "exclude" || value === "separate-bin";
}

function isDistanceMode(value: unknown): boolean {
  return value === "auto" || value === "1d" || value === "3d";
}

function isSortingState(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.every(
      (entry) =>
        isRecord(entry) &&
        isString(entry.id) &&
        isBoolean(entry.desc),
    )
  );
}

export function isJsonRpcError(value: unknown): value is JsonRpcError {
  return (
    isRecord(value) &&
    typeof value.code === "number" &&
    typeof value.message === "string"
  );
}

export function isProgressNotificationParams(value: unknown): value is ProgressNotification {
  return (
    isRecord(value) &&
    typeof value.value === "number" &&
    typeof value.message === "string"
  );
}

function isPolymeraseInfo(value: unknown): value is PolymeraseInfo {
  return (
    isRecord(value) &&
    isString(value.name) &&
    isString(value.manufacturer) &&
    isString(value.fidelity)
  );
}

function isPolymeraseProfile(value: unknown): value is PolymeraseProfile {
  return (
    isRecord(value) &&
    isString(value.name) &&
    isString(value.tm_method) &&
    isString(value.salt_correction) &&
    isNumber(value.opt_tm) &&
    isNumber(value.min_tm) &&
    isNumber(value.max_tm) &&
    isNumber(value.min_gc) &&
    isNumber(value.max_gc) &&
    isNumber(value.salt_monovalent) &&
    isNumber(value.salt_divalent) &&
    isNumber(value.dntp_conc) &&
    isNumber(value.dna_conc) &&
    isOptionalNullable(value.opt_tm_fwd, isNumber) &&
    isOptionalNullable(value.opt_tm_rev, isNumber) &&
    isOptionalNullable(value.opt_tm_overlap, isNumber) &&
    isOptional(value.min_3prime_dist, isNumber) &&
    isOptionalNullable(value.overlap_len, isNumber) &&
    isOptionalNullable(value.fwd_len_min, isNumber) &&
    isOptionalNullable(value.fwd_len_max, isNumber) &&
    isOptionalNullable(value.rev_len_min, isNumber) &&
    isOptionalNullable(value.rev_len_max, isNumber)
  );
}

function isCodonTableFinding(value: unknown): boolean {
  return isRecord(value) && isString(value.code) && isRecord(value.params);
}

// `taxid` and `cds_count` are nullable on purpose: the backend emits
// `data.get("taxid")` and a codon table JSON need not carry either field (an
// in-house strain has no NCBI id and a hand-written table declares no CDS
// count). This guard runs per element, so requiring a number here made one
// taxid-less table reject the entire `list_organisms` payload and render an
// empty organism dropdown.
function isOrganismSummary(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.key) &&
    isString(value.name) &&
    (value.taxid === null || isNumber(value.taxid)) &&
    (value.source === "builtin" || value.source === "user") &&
    isStringArray(value.aliases) &&
    (value.cds_count === null || isNumber(value.cds_count)) &&
    isString(value.table_sha256) &&
    isArrayOf(value.warnings, isCodonTableFinding) &&
    // Both optional so a sidecar built before Phase 2 still lists its
    // organisms instead of rendering an empty dropdown. The consumers treat an
    // absent document as "cannot embed, cannot diff", which is the same answer
    // they give for a table that has none.
    (value.normalizations === undefined ||
      isArrayOf(value.normalizations, isCodonTableFinding)) &&
    (value.document === undefined || isCodonTableDocument(value.document))
  );
}

function isCodonPairList(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.every(
      (pair) =>
        Array.isArray(pair) &&
        pair.length === 2 &&
        isString(pair[0]) &&
        isNumber(pair[1]),
    )
  );
}

export function isCodonTableDocument(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.key) &&
    isString(value.name) &&
    (value.taxid === null || isNumber(value.taxid)) &&
    isString(value.source) &&
    isNumber(value.genetic_code) &&
    isStringArray(value.aliases) &&
    isRecord(value.codons) &&
    Object.values(value.codons).every(isCodonPairList)
  );
}

function isCodonTableFailure(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.filename) &&
    isString(value.code) &&
    isString(value.reason) &&
    (value.findings === undefined ||
      isArrayOf(value.findings, isCodonTableFinding))
  );
}

// The envelope, not a bare array. `failed` and `user_dir` are properties of the
// listing as a whole and have no place inside an element, so widening the
// result meant changing its top-level shape rather than adding fields.
function isListOrganismsResult(value: unknown): boolean {
  return (
    isRecord(value) &&
    isArrayOf(value.organisms, isOrganismSummary) &&
    isArrayOf(value.failed, isCodonTableFailure) &&
    isString(value.user_dir)
  );
}

// `detail` is optional: the backend's English sentence, kept as the fallback
// for a code a build does not know. The localized sentence is rebuilt from
// `code` and `params`, so a guard that required `detail` would reject a
// perfectly renderable finding.
function isCodonTableImportFinding(value: unknown): boolean {
  return (
    isCodonTableFinding(value) &&
    (!isRecord(value) || value.detail === undefined || isString(value.detail))
  );
}

// `table_sha256`, `document` and `path` are all nullable rather than absent,
// because all three are "known not to exist" rather than "not reported": a
// rejected import has no digest, a dry run has no path. Making them optional
// would let a sidecar that forgot to send them pass as a successful install.
function isImportCodonTableResult(value: unknown): boolean {
  return (
    isRecord(value) &&
    isBoolean(value.ok) &&
    isBoolean(value.installed) &&
    isString(value.key) &&
    (value.table_sha256 === null || isString(value.table_sha256)) &&
    isArrayOf(value.errors, isCodonTableImportFinding) &&
    isArrayOf(value.warnings, isCodonTableImportFinding) &&
    isArrayOf(value.normalizations, isCodonTableImportFinding) &&
    isNumber(value.checks_performed) &&
    isNumber(value.codons_examined) &&
    (value.document === null || isCodonTableDocument(value.document)) &&
    (value.path === null || isString(value.path))
  );
}

function isCodonPreviewTopRow(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.aa) &&
    isString(value.codon) &&
    isNumber(value.fraction) &&
    isNumber(value.count)
  );
}

function isCodonPreviewDivergentRow(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.aa) &&
    isString(value.codon) &&
    isNumber(value.fraction) &&
    isNumber(value.reference_fraction) &&
    isNumber(value.delta)
  );
}

// The counts are checked, the two record maps are not looked into beyond being
// objects. `cds_excluded` is keyed by the sidecar's exclusion reasons and
// `excluded_examples` by the same set; enumerating them here would pin a list
// that lives in codon_compute.py and would reject a sidecar that added a sixth
// reason, which is the opposite of what a guard at this boundary is for.
function isCodonTablePreview(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.source_format) &&
    isNumber(value.cds_total) &&
    isNumber(value.cds_counted) &&
    isRecord(value.cds_excluded) &&
    isRecord(value.excluded_examples) &&
    isNumber(value.codon_count) &&
    isArrayOf(value.top_codons, isCodonPreviewTopRow) &&
    (value.reference_key === null || isString(value.reference_key)) &&
    isArrayOf(value.divergent_codons, isCodonPreviewDivergentRow)
  );
}

// The import envelope plus the tally. Not optional: a compute reply without a
// preview is a sidecar that ran the scan and threw the numbers away, and the
// dialog would render a panel of blanks rather than an error.
function isComputeCodonTableResult(value: unknown): boolean {
  return (
    isImportCodonTableResult(value) &&
    isRecord(value) &&
    isCodonTablePreview(value.preview)
  );
}

function isExportCodonTableResult(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.path) &&
    isString(value.format) &&
    isNumber(value.bytes)
  );
}

function isGeneInfo(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.gene) &&
    isString(value.product) &&
    isNumber(value.cds_start) &&
    isNumber(value.cds_end) &&
    isNumber(value.aa_length) &&
    isOptional(value.organism, isString) &&
    isOptional(value.translation, isString) &&
    isOptional(value.uniprot_accession, isString)
  );
}

function isSequenceInfo(value: unknown): value is SequenceInfo {
  return (
    isRecord(value) &&
    isString(value.header) &&
    isNumber(value.seq_length) &&
    isArrayOf(value.genes, isGeneInfo)
  );
}

function isParsedMutation(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.raw) &&
    isString(value.wt_aa) &&
    isNumber(value.position) &&
    isString(value.mt_aa)
  );
}

function isParseError(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNumber(value.line) &&
    isString(value.raw) &&
    isString(value.reason)
  );
}

function isParseMutationsResult(value: unknown): value is ParseMutationsResult {
  return (
    isRecord(value) &&
    isArrayOf(value.parsed, isParsedMutation) &&
    isArrayOf(value.errors, isParseError)
  );
}

function isOffTargetHit(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNumber(value.position) &&
    (value.strand === "sense" || value.strand === "antisense") &&
    isString(value.match_seq) &&
    isNumber(value.tm) &&
    isNumber(value.match_length)
  );
}

function isSdmPrimerResult(value: unknown): value is SdmPrimerResult {
  return (
    isRecord(value) &&
    isString(value.mutation) &&
    isNumber(value.aa_position) &&
    isNumber(value.codon_pos) &&
    isString(value.forward_seq) &&
    isString(value.reverse_seq) &&
    isNumber(value.fwd_len) &&
    isNumber(value.rev_len) &&
    isNumber(value.overlap_len) &&
    isOptional(value.candidate_count, isNumber) &&
    isOptional(value.candidate_fwd_count, isNumber) &&
    isOptional(value.candidate_rev_count, isNumber) &&
    isNumber(value.tm_no_fwd) &&
    isNumber(value.tm_no_rev) &&
    isNumber(value.tm_overlap) &&
    isBoolean(value.tm_condition_met) &&
    isNumber(value.tolerance_used) &&
    isOptional(value.tolerance_fwd, isNumber) &&
    isOptional(value.tolerance_rev, isNumber) &&
    isBoolean(value.has_offtarget) &&
    isOptional(value.offtarget_fwd, (item) => isArrayOf(item, isOffTargetHit)) &&
    isOptional(value.offtarget_rev, (item) => isArrayOf(item, isOffTargetHit)) &&
    isNumber(value.penalty) &&
    isNumber(value.gc_fwd) &&
    isNumber(value.gc_rev) &&
    isString(value.wt_codon) &&
    isString(value.mt_codon) &&
    isString(value.overlap_seq) &&
    isOptional(value.hairpin_tm_fwd, isNumber) &&
    isOptional(value.hairpin_tm_rev, isNumber) &&
    isOptional(value.homodimer_tm_fwd, isNumber) &&
    isOptional(value.homodimer_tm_rev, isNumber) &&
    isOptional(value.hairpin_dg_fwd, isNumber) &&
    isOptional(value.hairpin_dg_rev, isNumber) &&
    isOptional(value.homodimer_dg_fwd, isNumber) &&
    isOptional(value.homodimer_dg_rev, isNumber) &&
    isOptional(value.hairpin_warn_fwd, isBoolean) &&
    isOptional(value.hairpin_warn_rev, isBoolean) &&
    isOptional(value.homodimer_warn_fwd, isBoolean) &&
    isOptional(value.homodimer_warn_rev, isBoolean) &&
    isOptional(value.synthesis_score_fwd, isNumber) &&
    isOptional(value.synthesis_score_rev, isNumber) &&
    isOptionalNullable(value.recommended_ta, isNumber) &&
    isOptional(value.ta_mode, isString) &&
    isOptional(value.ta_detail, isString) &&
    isOptionalNullable(value.ta_touchdown, isString) &&
    isStringArray(value.warnings)
  );
}

function isAlternativesResult(value: unknown): value is AlternativesResult {
  return (
    isRecord(value) &&
    isOptional(value.mutation, isString) &&
    isOptional(value.count, isNumber) &&
    isArrayOf(value.candidates, isSdmPrimerResult)
  );
}

function isDomainInfo(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.name) &&
    isString(value.id) &&
    isNumber(value.start) &&
    isNumber(value.end) &&
    isString(value.db)
  );
}

function isFetchDomainsResult(value: unknown): value is FetchDomainsResult {
  return (
    isRecord(value) &&
    isString(value.accession) &&
    isArrayOf(value.domains, isDomainInfo) &&
    (value.source === "interpro_api" || value.source === "manual" || value.source === "error") &&
    isOptional(value.protein_length, isNumber) &&
    isOptional(value.error_msg, isString)
  );
}
function isAnnotateDomainsResult(value: unknown): value is AnnotateDomainsResult {
  return (
    isRecord(value) &&
    isArrayOf(value.domains, isDomainInfo) &&
    (value.source === "interproscan" || value.source === "error") &&
    value.coordinate_frame === "reference" &&
    isNumber(value.protein_length) &&
    isString(value.ref_hash) &&
    isBoolean(value.cache_hit) &&
    isOptional(value.error_msg, isString) &&
    isOptionalNullable(value.error_code, isContactEmailErrorCode)
  );
}


function isDomainStat(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNumber(value.quota) &&
    isNumber(value.selected)
  );
}

function isEvolveproStepStats(value: unknown): boolean {
  return (
    isRecord(value) &&
    isOptionalNullable(value.position_filter_removed, isNumber) &&
    isOptionalNullable(value.domain_selected, isNumber) &&
    isOptionalNullable(value.pareto_exchanges, isNumber)
  );
}

function isSha256(value: unknown): value is string {
  return isString(value) && /^[a-f0-9]{64}$/.test(value);
}

function isHttpsUrl(value: unknown): value is string {
  if (!isString(value)) return false;
  try { return new URL(value).protocol === "https:"; } catch { return false; }
}

function isPredictionBundleInventory(value: unknown): value is PredictionBundleInventory {
  if (!(isRecord(value) && value.schema_version === 1 && isString(value.source_name)
    && isSha256(value.bundle_sha256) && (value.format === "af3_server" || value.format === "colabfold")
    && isHttpsUrl(value.source_url) && (value.terms_url === null || isHttpsUrl(value.terms_url))
    && isOptional(value.notices, isPredictionNotices)
    && isArrayOf(value.models, (model) => isRecord(model)
      && isString(model.model_id) && model.model_id.length > 0
      && isString(model.structure_member) && model.structure_member === model.model_id
      && (model.confidence_member === null || isString(model.confidence_member))
      && (model.structure_format === "pdb" || model.structure_format === "cif")
      && isArrayOf(model.chains, (chain) => isRecord(chain)
        && isString(chain.chain_id) && isString(chain.author_chain_id)
        && isString(chain.sequence) && /^[A-Z]+$/.test(chain.sequence)
        && chain.length === chain.sequence.length)))) return false;
  const inventory = value as unknown as PredictionBundleInventory;
  return inventory.models.length > 0
    && new Set(inventory.models.map((model) => model.model_id)).size === inventory.models.length
    && inventory.models.every((model) => model.chains.length > 0
      && new Set(model.chains.map((chain) => chain.chain_id)).size === model.chains.length);
}

function isPredictionNotices(value: unknown): boolean {
  return Array.isArray(value) && value.length <= 256 && value.every((notice) => isRecord(notice)
    && isString(notice.member) && notice.member.length <= 4096 && isSha256(notice.sha256)
    && isString(notice.text) && notice.text.length <= 262144);
}

function isPredictionBundleEvidence(value: unknown): value is PredictionBundleEvidence {
  const nonnegative = (item: unknown): item is number => isNumber(item) && item >= 0;
  if (!(isRecord(value) && (value.format === "af3_server" || value.format === "colabfold")
    && isString(value.source_name) && isSha256(value.bundle_sha256)
    && isString(value.model_id) && value.model_id.length > 0 && isString(value.chain_id) && isString(value.author_chain_id)
    && isString(value.structure_member) && value.structure_member === value.model_id
    && (value.confidence_member === null || isString(value.confidence_member))
    && isSha256(value.structure_sha256) && (value.confidence_sha256 === null || isSha256(value.confidence_sha256))
    && (value.confidence_member === null) === (value.confidence_sha256 === null)
    && isHttpsUrl(value.source_url) && (value.terms_url === null || isHttpsUrl(value.terms_url))
    && isSha256(value.display_sha256) && value.display_kind === "reference-ca-trace"
    && isArrayOf(value.plddt_by_reference, (item) => item === null || (nonnegative(item) && item <= 100))
    && isString(value.plddt_source) && value.interdomain_confidence === "not_assessed"
    && isOptional(value.source_notices, isPredictionNotices)
    && isOptionalNullable(value.sequence_member, isString)
    && isOptionalNullable(value.sequence_sha256, isSha256)
    && isOptional(value.missing_reference_positions, (positions) => isArrayOf(positions,
      (position) => isNumber(position) && Number.isSafeInteger(position) && position > 0))
    && isStringArray(value.warnings) && isRecord(value.pae)
    && (value.pae.status === "available" || value.pae.status === "unavailable")
    && (value.pae.source === null || isString(value.pae.source))
    && nonnegative(value.pae.dimension) && Number.isSafeInteger(value.pae.dimension)
    && (value.pae.mean === null || nonnegative(value.pae.mean))
    && (value.pae.max === null || nonnegative(value.pae.max))
    && value.pae.scope === "selected-chain-polymer" && value.pae.directional === true)) return false;
  const evidence = value as unknown as PredictionBundleEvidence;
  if ((evidence.sequence_member == null) !== (evidence.sequence_sha256 == null)) return false;
  return evidence.pae.status === "available"
    ? evidence.pae.dimension > 0 && evidence.pae.source !== null
      && ((evidence.pae.mean === null && evidence.pae.max === null)
        || (evidence.pae.mean !== null && evidence.pae.max !== null && evidence.pae.max >= evidence.pae.mean))
    : evidence.pae.mean === null && evidence.pae.max === null;
}

function isStrictSpatialProfile(value: unknown): value is StrictSpatialProfile {
  const positiveInteger = (item: unknown): item is number => isNumber(item) && Number.isSafeInteger(item) && item > 0;
  return isRecord(value)
    && positiveInteger(value.variant_count) && positiveInteger(value.site_count)
    && positiveInteger(value.max_variants_per_site)
    && value.site_count <= value.variant_count && value.max_variants_per_site <= value.variant_count
    && (value.minimum_site_distance === null || (isNumber(value.minimum_site_distance) && value.minimum_site_distance >= 0))
    && (value.minimum_site_distance === null) === (value.site_count < 2)
    && isNumber(value.coverage_mean_distance) && value.coverage_mean_distance >= 0
    && isNumber(value.coverage_max_distance) && value.coverage_max_distance >= value.coverage_mean_distance
    && (value.score_mean === null || isNumber(value.score_mean))
    && (value.mean_score_rank === null || (isNumber(value.mean_score_rank) && value.mean_score_rank >= 1));
}

function isStrictSpatialComparison(value: unknown, report: StrictSpatialResult): boolean {
  if (value === undefined) return true; // Additive diagnostics: older certificates remain usable.
  if (!(isRecord(value) && value.baseline === "configured-score-top-n"
    && value.universe === "eligible-variants-after-budget-and-cap-policy"
    && value.candidate_site_count === report.eligible_site_count
    && value.score_available === report.score_available
    && isStrictSpatialProfile(value.selected)
    && (value.top_n === null || isStrictSpatialProfile(value.top_n))
    && (value.top_n_variants === null || isStringArray(value.top_n_variants))
    && (value.top_n_overlap_count === null || (isNumber(value.top_n_overlap_count)
      && Number.isSafeInteger(value.top_n_overlap_count) && value.top_n_overlap_count >= 0))
    && (value.score_gap_to_top_n === null || (isNumber(value.score_gap_to_top_n) && value.score_gap_to_top_n >= 0)))) return false;
  const comparison = value as unknown as StrictSpatialComparison;
  const selected = comparison.selected;
  if (selected.variant_count !== report.selected_variant_count || selected.site_count !== report.selected_site_count
    || selected.max_variants_per_site !== report.site_multiplicities.reduce((maximum, row) => Math.max(maximum, row.variant_count), 0)
    || selected.minimum_site_distance !== report.geometry_site_min_pair_distance) return false;
  if (!comparison.score_available) return selected.score_mean === null && selected.mean_score_rank === null
    && comparison.top_n === null && comparison.top_n_variants === null
    && comparison.top_n_overlap_count === null && comparison.score_gap_to_top_n === null;
  const baseline = comparison.top_n;
  const variants = comparison.top_n_variants;
  if (baseline === null || variants === null || selected.mean_score_rank === null || baseline.mean_score_rank === null
    || variants.length !== report.requested_count || new Set(variants).size !== variants.length
    || baseline.variant_count !== variants.length || baseline.site_count > comparison.candidate_site_count
    || selected.mean_score_rank > report.eligible_variant_count || baseline.mean_score_rank > report.eligible_variant_count) return false;
  const multiplicities = new Map<number, number>();
  const eligible = new Set(report.eligible_positions);
  const selectedIds = new Set(report.selected_variants);
  for (const variant of variants) {
    const match = /^([ACDEFGHIKLMNPQRSTVWY])([1-9]\d*)([ACDEFGHIKLMNPQRSTVWY])$/.exec(variant);
    if (match === null || match[1] === match[3] || !eligible.has(Number(match[2]))) return false;
    const position = Number(match[2]);
    multiplicities.set(position, (multiplicities.get(position) ?? 0) + 1);
  }
  const maximum = [...multiplicities.values()].reduce((largest, size) => Math.max(largest, size), 0);
  const expectedGap = selected.score_mean === null || baseline.score_mean === null ? null
    : report.score_order === "asc" ? selected.score_mean - baseline.score_mean : baseline.score_mean - selected.score_mean;
  const tolerance = 1e-9 * Math.max(1, Math.abs(selected.score_mean ?? 0), Math.abs(baseline.score_mean ?? 0));
  const gapValid = expectedGap === null || !Number.isFinite(expectedGap) || expectedGap < 0
    ? comparison.score_gap_to_top_n === null
    : comparison.score_gap_to_top_n !== null && Math.abs(comparison.score_gap_to_top_n - expectedGap) <= tolerance;
  return baseline.site_count === multiplicities.size && baseline.max_variants_per_site === maximum
    && (report.budget_mode !== "unique_sites" || maximum === 1)
    && (report.site_cap === null || maximum <= report.site_cap)
    && comparison.top_n_overlap_count === variants.filter((variant) => selectedIds.has(variant)).length
    && gapValid;
}

function isStrictSpatialResult(value: unknown): boolean {
  const positiveInteger = (item: unknown): item is number => isNumber(item) && Number.isSafeInteger(item) && item > 0;
  const count = (item: unknown) => isNumber(item) && Number.isSafeInteger(item) && item >= 0;
  const distance = (item: unknown) => item === null || (isNumber(item) && item >= 0);
  if (!(isRecord(value) && value.schema_version === 1
    && isString(value.source_accession) && isString(value.source_sha256)
    && isString(value.reference_sha256) && isString(value.candidate_sha256)
    && (value.score_order === "asc" || value.score_order === "desc")
    && isBoolean(value.score_available) && isString(value.pdb_text)
    && isOptional(value.structure_format, (format) => format === "pdb" || format === "cif")
    && isOptional(value.prediction_bundle, isPredictionBundleEvidence)
    && value.coordinate_frame === "reference"
    && (value.budget_mode === "unique_sites" || value.budget_mode === "distinct_variants")
    && value.selection_policy === (value.budget_mode === "unique_sites"
      ? "single-site-full-pool-fps-v1" : "distinct-variant-full-pool-fps-v1")
    && (value.site_cap === null || positiveInteger(value.site_cap))
    && (value.budget_mode !== "unique_sites" || value.site_cap === null)
    && isStringArray(value.selected_variants)
    && isArrayOf(value.selected_positions, positiveInteger)
    && isArrayOf(value.eligible_positions, positiveInteger)
    && count(value.source_row_count) && count(value.parsed_variant_count)
    && count(value.parsing_omitted_count) && count(value.start_position_omitted_count)
    && count(value.duplicate_variant_omitted_count)
    && positiveInteger(value.requested_count) && positiveInteger(value.eligible_site_count)
    && positiveInteger(value.selected_variant_count) && positiveInteger(value.selected_site_count)
    && positiveInteger(value.eligible_variant_count)
    && distance(value.geometry_variant_min_pair_distance) && distance(value.geometry_site_min_pair_distance)
    && isArrayOf(value.site_multiplicities, (row) => isRecord(row)
      && positiveInteger(row.reference_position) && positiveInteger(row.variant_count))
    && isArrayOf(value.excluded, (row) => isRecord(row) && isString(row.variant) && isString(row.reason))
    && isArrayOf(value.mapping, (row) => isRecord(row)
      && positiveInteger(row.reference_position) && isNumber(row.structure_position) && Number.isSafeInteger(row.structure_position)
      && (value.prediction_bundle !== undefined || row.structure_position > 0)
      && isString(row.chain_id) && isString(row.insertion_code)
      && isOptional(row.model_id, (item) => isString(item) || (isNumber(item) && Number.isSafeInteger(item)))
      && isOptional(row.polymer_position, positiveInteger)
      && isOptional(row.viewer_position, positiveInteger)
      && isOptional(row.viewer_chain_id, isString) && isOptional(row.viewer_insertion_code, isString)
      && isNumberArray(row.coordinate) && row.coordinate.length === 3))) return false;

  // Array element predicates above check the full shape; keep the accounting
  // checks explicit so repeated sites cannot silently replace distinct IDs.
  const report = value as unknown as StrictSpatialResult;
  if (report.prediction_bundle && (report.structure_format !== "pdb"
    || report.source_sha256 !== report.prediction_bundle.structure_sha256
    || report.prediction_bundle.plddt_by_reference.length === 0
    || !report.mapping.every((row) => row.viewer_position === row.reference_position
      && row.viewer_chain_id === "A" && row.viewer_insertion_code === ""
      && row.reference_position <= (report.prediction_bundle?.plddt_by_reference.length ?? 0)))) return false;
  const multiplicities = new Map<number, number>();
  for (const position of report.selected_positions) {
    multiplicities.set(position, (multiplicities.get(position) ?? 0) + 1);
  }
  const mapped = new Set(report.mapping.map((row) => row.reference_position));
  const eligible = new Set(report.eligible_positions);
  return report.requested_count === report.selected_variants.length
    && report.selected_variant_count === report.selected_variants.length
    && report.selected_positions.length === report.selected_variants.length
    && new Set(report.selected_variants).size === report.selected_variants.length
    && report.selected_site_count === multiplicities.size
    && report.eligible_site_count === eligible.size
    && eligible.size === report.eligible_positions.length
    && report.eligible_variant_count >= report.selected_variant_count
    && report.eligible_variant_count >= report.eligible_site_count
    && mapped.size === report.mapping.length
    && report.eligible_positions.every((position) => mapped.has(position))
    && report.selected_variants.every((variant, index) => {
      const match = /^([ACDEFGHIKLMNPQRSTVWY])([1-9]\d*)([ACDEFGHIKLMNPQRSTVWY])$/.exec(variant);
      return match !== null && match[1] !== match[3]
        && Number(match[2]) === report.selected_positions[index]
        && eligible.has(report.selected_positions[index]);
    })
    && (report.budget_mode !== "unique_sites" || multiplicities.size === report.selected_variant_count)
    && [...multiplicities.values()].every((size) => report.site_cap === null || size <= report.site_cap)
    && report.site_multiplicities.length === multiplicities.size
    && new Set(report.site_multiplicities.map((row) => row.reference_position)).size === multiplicities.size
    && report.site_multiplicities.every((row) => multiplicities.get(row.reference_position) === row.variant_count)
    && (report.geometry_variant_min_pair_distance === null) === (report.selected_variant_count < 2)
    && (report.geometry_site_min_pair_distance === null) === (report.selected_site_count < 2)
    && isStrictSpatialComparison(value.comparison, report);
}

function isEvolveproLoadResult(value: unknown): value is EvolveproLoadResult {
  return (
    isRecord(value) &&
    isStringArray(value.variants) &&
    isNumberArray(value.y_preds) &&
    isNumber(value.total_count) &&
    isNumber(value.selected_count) &&
    isOptionalNullable(value.filtered_count, isNumber) &&
    isOptionalNullable(value.domain_stats, (item) => isRecordOf(item, isDomainStat)) &&
    isOptionalNullable(value.pareto_replaced, isNumber) &&
    isOptionalNullable(value.pool_variants, isStringArray) &&
    isOptionalNullable(value.used_variant_column, isString) &&
    isOptionalNullable(value.used_score_column, isString) &&
    isOptionalNullable(value.step_stats, isEvolveproStepStats) &&
    isOptional(value.strict_spatial, isStrictSpatialResult)
  );
}

function isFailedMutation(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.mutation) &&
    isNumber(value.rank) &&
    isString(value.reason)
  );
}

function isRescueStats(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNumber(value.pool_cascade) &&
    isNumber(value.auto_relax) &&
    isNumber(value.positions_attempted) &&
    isNumber(value.pool_variants_tried)
  );
}

function isRescuedMutation(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.original) &&
    isString(value.rescued_by) &&
    (value.type === "pool_cascade" ||
      value.type === "auto_relax" ||
      value.type === "auto_suggestion" ||
      value.type === "same_position" ||
      value.type === "diff_position" ||
      value.type === "auto_suggestion_l1" ||
      value.type === "auto_suggestion_l2" ||
      value.type === "auto_suggestion_l3" ||
      value.type === "auto_suggestion_l4") &&
    isOptional(value.penalty, isNumber) &&
    isOptional(value.tolerance_used, isNumber) &&
    isOptional(value.stage, isNumber) &&
    isOptional(value.substitute, isString)
  );
}

function isDesignResult(value: unknown): value is DesignResult {
  return (
    isRecord(value) &&
    isArrayOf(value.results, isSdmPrimerResult) &&
    isNumber(value.success_count) &&
    isNumber(value.total_count) &&
    isArrayOf(value.failed_mutations, isFailedMutation) &&
    isOptional(value.rescue_stats, isRescueStats) &&
    isOptional(value.rescued_mutations, (item) => isArrayOf(item, isRescuedMutation)) &&
    isOptional(value.cancelled, isBoolean)
  );
}

function isPlateMapping(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.well) &&
    isString(value.primer_name) &&
    isString(value.sequence) &&
    (value.primer_type === "forward" || value.primer_type === "reverse") &&
    isString(value.mutation) &&
    isOptional(value.tm, isNumber) &&
    isOptional(value.tm_overlap, isNumber) &&
    isOptional(value.wt_codon, isString) &&
    isOptional(value.mt_codon, isString)
  );
}

function isPlateMapResult(value: unknown): value is PlateMapResult {
  return (
    isRecord(value) &&
    isArrayOf(value.mappings, isPlateMapping) &&
    isRecordOf(value.dedup_info, isStringArray)
  );
}

function isExportResult(value: unknown): value is ExportResult {
  return (
    isRecord(value) &&
    isBoolean(value.success) &&
    isString(value.filepath)
  );
}

function isExportOrderResult(value: unknown): value is ExportOrderResult {
  return (
    isRecord(value) &&
    isExportResult(value) &&
    (value.format === "idt" || value.format === "twist") &&
    isNumber(value.primer_count)
  );
}

function isExportMappingResult(value: unknown): value is ExportMappingResult {
  return (
    isRecord(value) &&
    isExportResult(value) &&
    (value.format === "echo" || value.format === "janus") &&
    isNumber(value.primer_count)
  );
}

function isSaveCustomPolymeraseResult(value: unknown): value is SaveCustomPolymeraseResult {
  return (
    isRecord(value) &&
    isBoolean(value.success) &&
    isString(value.name)
  );
}

function isWorkspaceInputs(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.fastaPath) &&
    isMutationInputMode(value.mutationInputMode) &&
    isString(value.mutationText) &&
    isString(value.evolveproCsvPath) &&
    isString(value.selectedGene) &&
    isOptional(value.othersSourcePath, isString)
  );
}

function isWorkspaceSettings(value: unknown): boolean {
  return (
    isRecord(value) &&
    isOptional(value.selectedPolymerase, isString) &&
    isCodonStrategy(value.codonStrategy) &&
    isNumber(value.maxPrimers) &&
    isNumber(value.tmFwdTarget) &&
    isNumber(value.tmRevTarget) &&
    isNumber(value.tmOverlapTarget) &&
    isNumber(value.gcMin) &&
    isNumber(value.gcMax) &&
    isOptional(value.primerLenEnabled, isBoolean) &&
    isOptional(value.fwdLenMin, isNumber) &&
    isOptional(value.fwdLenMax, isNumber) &&
    isOptional(value.revLenMin, isNumber) &&
    isOptional(value.revLenMax, isNumber) &&
    isOptional(value.fillOnFailure, isBoolean) &&
    isOptional(value.tmTolerance, isNumber) &&
    isOptional(value.structureAccession, isString) &&
    isOptional(value.structureLoaded, isBoolean) &&
    isOptional(value.uniprotAccession, isString) &&
    isOptional(value.domains, (item) => isArrayOf(item, isDomainInfo)) &&
    isOptional(value.refDomains, (item) => isArrayOf(item, isDomainInfo)) &&
    isOptional(value.refDomainHash, isString) &&
    isOptional(value.domainDiversityEnabled, isBoolean) &&
    isOptional(value.domainStrategy, isDomainStrategy) &&
    isOptional(value.domainOverlapPolicy, isDomainOverlapPolicy) &&
    isOptional(value.linkerHandling, isLinkerHandling) &&
    isOptional(value.domainQuotaMin, isNumber) &&
    isOptional(value.paretoDiversityEnabled, isBoolean) &&
    isOptional(value.disabledDomains, isStringArray) &&
    isOptional(value.rescuedMutations, isStringArray) &&
    isOptional(value.entropyWeightEnabled, isBoolean) &&
    isOptional(value.entropyWeight, isNumber) &&
    isOptional(value.paretoPoolMultiplier, isNumber) &&
    isOptional(value.distanceMode, isDistanceMode) &&
    isOptional(value.benchmarkTopPercentile, isNumber) &&
    isOptional(value.benchmarkRandomTrials, isNumber) &&
    isOptionalNullable(value.benchmarkRandomSeed, isNumber) &&
    isOptional(value.autoRedesignOnLoad, isBoolean) &&
    isOptional(value.saveCache, isBoolean) &&
    isOptional(value.organism, isString) &&
    isOptional(value.pipelineMode, isBoolean) &&
    isOptional(value.evolveproMode, (v) => v === "topN" || v === "pipeline" || v === "others") &&
    isOptional(value.overlapMode, (v) => v === "partial" || v === "full") &&
    isOptionalNullable(value.randomSeed, isNumber) &&
    isOptional(value.echoTransferVol, isNumber) &&
    isOptionalNullable(value.echoQuadrant, isPersistedEchoQuadrant) &&
    isOptional(value.echoUsedQuadrants, (v) => isArrayOf(v, isPersistedEchoQuadrant)) &&
    isOptional(value.echoRoundQuadrants, (v) => isArrayOf(v, (e) => e === null || isString(e))) &&
    // Loose like the parity list: normalizeRoundPicks turns a bad entry into "not picked".
    isOptional(value.echoRoundPlates, (v) => Array.isArray(v)) &&
    isOptional(value.janusTransferVol, isNumber) &&
    isOptional(value.positionDiversityEnabled, isBoolean) &&
    isOptional(value.maxPerPosition, isNumber) &&
    isOptional(value.evolveproRound, isNumber) &&
    isOptional(value.roundSize, isNumber) &&
    isOptional(value.structuralDiversityEnabled, isBoolean) &&
    isOptional(value.structuralKappa, isNumber)
  );
}

function isWorkspaceResults(value: unknown): boolean {
  return (
    isRecord(value) &&
    isArrayOf(value.designResults, isSdmPrimerResult) &&
    isNumber(value.successCount) &&
    isNumber(value.totalCount) &&
    isArrayOf(value.failedMutations, isFailedMutation) &&
    isOptional(value.excludedDesignMutations, isStringArray) &&
    isArrayOf(value.plateMappings, isPlateMapping) &&
    isRecordOf(value.dedupInfo, isStringArray) &&
    isRecordOf(value.manuallySwapped, isString) &&
    isRecordOf(value.customCandidates, (item) => isArrayOf(item, isSdmPrimerResult)) &&
    isOptional(value.rescuedMutationDetails, (item) => isArrayOf(item, isRescuedMutation))
  );
}

function isBenchmarkResult(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNumber(value.n_selected) &&
    isNumber(value.hit_rate) &&
    isNumber(value.mean_fitness) &&
    isNumber(value.unique_positions) &&
    isNumber(value.position_coverage) &&
    isNumber(value.domain_coverage) &&
    isNumber(value.structural_spread) &&
    isNumber(value.hits) &&
    isNumber(value.threshold) &&
    isOptional(value.n_trials, isNumber)
  );
}

function isWorkspaceCache(value: unknown): boolean {
  return (
    isRecord(value) &&
    isOptionalNullable(value.evolveproFilteredCount, isNumber) &&
    isOptionalNullable(value.evolveproParetoExchanges, isNumber) &&
    isOptional(value.evolveproTotalCount, isNumber) &&
    isOptionalNullable(value.evolveproStepStats, isEvolveproStepStats) &&
    isOptionalNullable(value.benchmarkResults, (item) => isRecordOf(item, isBenchmarkResult))
  );
}

function isPersistedEchoQuadrant(value: unknown): boolean {
  // 세 시대의 저장 이름을 전부 읽을 수 있어야 한다. A1/A2 는 현재 이름이고,
  // B1/B2 는 교차 시절 이름이라 fold 로 접히며, A13 은 half 시절 이름이라
  // foldPersistedPlacement 가 거부한다. 여기서 떨어뜨리면 거부 안내조차 못 낸다.
  return value === "A1" || value === "A13" || value === "A2" || value === "B1" || value === "B2";
}

function isPlateMeta(value: unknown): boolean {
  return isRecord(value) && isArrayOf(value.plates, (plate) =>
    isRecord(plate) && isString(plate.plate_id) &&
    isStringArray(plate.wt_wells) && isStringArray(plate.control_wells));
}

function isActivityRecord(value: unknown): boolean {
  return isRecord(value) && isString(value.plate_id) && isString(value.well_id) &&
    isNumber(value.value) && isNumber(value.replicate_idx) &&
    isBoolean(value.is_wt) && isString(value.source_file);
}

function isNullableString(value: unknown): boolean {
  return value === null || isString(value);
}

function isNullableNumber(value: unknown): boolean {
  return value === null || isNumber(value);
}

function isMergedRow(value: unknown): boolean {
  return isRecord(value) && isString(value.plate_id) && isString(value.well_id) &&
    isNullableString(value.mutation) &&
    (value.mutation_source === "kuro_design" || value.mutation_source === "mame_genotype" || value.mutation_source === "activity_only") &&
    isNullableString(value.expected_mutation) && isNullableString(value.called_mutation) &&
    isBoolean(value.ngs_success) && isNullableNumber(value.activity_raw_mean) &&
    isNullableNumber(value.activity_raw_sd) && isNumberArray(value.activity_replicates) &&
    isNumber(value.replicate_n) && isNullableNumber(value.fold_change) &&
    isNullableNumber(value.log2_fc) && isOptionalNullable(value.activity_merged_mean, isNumber);
}

function isRoundFile(value: unknown): boolean {
  return isRecord(value) && isString(value.path) &&
    isOptional(value.wt_values, isNumberArray) &&
    isOptional(value.variant_replicates, (v) => isRecordOf(v, isNumberArray));
}

function isDecisionLabel(value: unknown): boolean {
  return value === "continue_walking" || value === "switch_combinatorial" ||
    value === "stop" || value === "deferred";
}

function isAdvisoryResult(value: unknown): boolean {
  if (!isRecord(value) || !isArrayOf(value.missing_inputs, (v) => v === "wt_replicates")) return false;
  switch (value.advisory) {
    case "decision":
      return isDecisionLabel(value.label) && isString(value.reason) &&
        isNullableNumber(value.confidence);
    case "not_assessable":
      return (value.reason === "wt_replicates_missing" || value.reason === "wt_replicates_insufficient") &&
        isArrayOf(value.blocked_decisions, isDecisionLabel) &&
        isOptional(value.wt_replicate_count, isNumber) && isOptional(value.wt_replicate_min, isNumber);
    default:
      return false;
  }
}

function isRound(value: unknown): boolean {
  return isRecord(value) && isString(value.id) && isNumber(value.n) &&
    isString(value.created_at) &&
    (value.status === "design" || value.status === "ordered" || value.status === "ngs_done" ||
      value.status === "activity_linked" || value.status === "exported" ||
      value.status === "combinatorial" || value.status === "closed" || value.status === "error") &&
    (value.error_info === null || (isRecord(value.error_info) &&
      (value.error_info.stage === "upload" || value.error_info.stage === "merge" ||
        value.error_info.stage === "export" || value.error_info.stage === "handoff") &&
      isString(value.error_info.message) && isString(value.error_info.occurred_at))) &&
    isPlateMeta(value.plate_meta) && isRecord(value.design) && isRecord(value.genotype) &&
    (value.activity === null || (isRecord(value.activity) &&
      isArrayOf(value.activity.records, isActivityRecord) && isPlateMeta(value.activity.plate_meta))) &&
    isArrayOf(value.merged_table, isMergedRow) &&
    isOptionalNullable(value.evolvepro_input, (v) =>
      isRecord(v) && isRoundFile(v) && isString(v.produced_at)) &&
    isOptionalNullable(value.advisory, (v) =>
      isRecord(v) && isAdvisoryResult(v.result) &&
      isArrayOf(v.inputs, (entry) => isRecord(entry) && isRoundFile(entry) && isNumber(entry.n)) &&
      isString(v.decided_at) && isString(v.input_signature));
}

function isWorkspaceData(value: unknown): value is WorkspaceData {
  if (!isRecord(value)) {
    return false;
  }

  if (value.schema_version === "0.3") {
    return (
      isWorkspaceInputs(value.inputs) &&
      isWorkspaceSettings(value.settings) &&
      isWorkspaceResults(value.results) &&
      isRecord(value.ui) &&
      isSortingState(value.ui.tableSorting) &&
      isOptional(value.cache, isWorkspaceCache) &&
      isArrayOf(value.rounds, isRound) &&
      (value.active_round_id === null || isString(value.active_round_id))
    );
  }

  if (!isNumber(value.version)) {
    return false;
  }

  if (value.version === 1) {
    return (
      isString(value.fastaPath) &&
      isMutationInputMode(value.mutationInputMode) &&
      isString(value.mutationText) &&
      isString(value.evolveproCsvPath) &&
      isString(value.selectedGene) &&
      isCodonStrategy(value.codonStrategy) &&
      isNumber(value.maxPrimers) &&
      isArrayOf(value.designResults, isSdmPrimerResult) &&
      isNumber(value.successCount) &&
      isNumber(value.totalCount) &&
      isArrayOf(value.failedMutations, isFailedMutation) &&
      isArrayOf(value.plateMappings, isPlateMapping) &&
      isRecordOf(value.dedupInfo, isStringArray) &&
      isSortingState(value.tableSorting) &&
      isRecordOf(value.manuallySwapped, isString) &&
      isRecordOf(value.customCandidates, (item) => isArrayOf(item, isSdmPrimerResult)) &&
      isNumber(value.tmFwdTarget) &&
      isNumber(value.tmRevTarget) &&
      isNumber(value.tmOverlapTarget) &&
      isNumber(value.gcMin) &&
      isNumber(value.gcMax) &&
      isOptional(value.primerLenEnabled, isBoolean) &&
      isOptional(value.fwdLenMin, isNumber) &&
      isOptional(value.fwdLenMax, isNumber) &&
      isOptional(value.revLenMin, isNumber) &&
      isOptional(value.revLenMax, isNumber) &&
      isOptional(value.fillOnFailure, isBoolean) &&
      isOptional(value.uniprotAccession, isString) &&
      isOptional(value.domains, (item) => isArrayOf(item, isDomainInfo)) &&
      isOptional(value.domainDiversityEnabled, isBoolean) &&
      isOptional(value.domainStrategy, isDomainStrategy) &&
      isOptional(value.paretoDiversityEnabled, isBoolean) &&
      isOptional(value.disabledDomains, isStringArray) &&
      isOptional(value.rescuedMutations, isStringArray) &&
      isOptional(value.entropyWeightEnabled, isBoolean) &&
      isOptional(value.entropyWeight, isNumber) &&
      isOptional(value.organism, isString) &&
      isOptional(value.pipelineMode, isBoolean) &&
      isOptional(value.positionDiversityEnabled, isBoolean) &&
      isOptional(value.maxPerPosition, isNumber) &&
      isOptional(value.evolveproRound, isNumber) &&
      isOptional(value.roundSize, isNumber) &&
      isOptionalNullable(value.evolveproFilteredCount, isNumber) &&
      isOptionalNullable(value.evolveproParetoExchanges, isNumber) &&
      isOptional(value.evolveproTotalCount, isNumber) &&
      isOptionalNullable(value.evolveproStepStats, isEvolveproStepStats)
    );
  }

  if (value.version === 2) {
    return (
      isWorkspaceInputs(value.inputs) &&
      isWorkspaceSettings(value.settings) &&
      isWorkspaceResults(value.results) &&
      isRecord(value.ui) &&
      isSortingState(value.ui.tableSorting) &&
      isOptional(value.cache, isWorkspaceCache)
    );
  }

  return false;
}

function isUniprotCandidate(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.accession) &&
    isString(value.name) &&
    isString(value.organism) &&
    isNumber(value.length) &&
    isNumber(value.identity) &&
    isOptional(value.has_structure, isBoolean) &&
    isOptionalNullable(value.subunit, isString) &&
    isOptional(value.oligomeric, isString)
  );
}

function isSearchUniprotResult(value: unknown): value is SearchUniprotResult {
  return (
    isRecord(value) &&
    isArrayOf(value.candidates, isUniprotCandidate) &&
    (value.auto_selected === null || isString(value.auto_selected)) &&
    isOptionalNullable(value.error_detail, isString) &&
    isOptionalNullable(value.error_code, isContactEmailErrorCode)
  );
}

function isContactEmailErrorCode(value: unknown): value is ContactEmailErrorCode {
  return value === CONTACT_EMAIL_REQUIRED;
}

function isStructureAvailabilityResult(value: unknown): value is StructureAvailabilityResult {
  return (
    isRecord(value) &&
    isRecordOf(value.availability, isBoolean)
  );
}

function isStructureResult(value: unknown): value is StructureResult {
  return (
    isRecord(value) &&
    isBoolean(value.success) &&
    isOptional(value.accession, isString) &&
    isOptional(value.residues, isNumber) &&
    isOptional(value.error, isString)
  );
}

function isStructureModelCandidate(value: unknown): value is StructureModelCandidate {
  return (
    isRecord(value) &&
    isString(value.name) &&
    isNumber(value.residue_count) &&
    (value.ranking_score === null || isOptional(value.ranking_score, isNumber)) &&
    (value.mean_plddt === null || isOptional(value.mean_plddt, isNumber))
  );
}

function isLoadStructureFileResult(value: unknown): value is LoadStructureFileResult {
  return (
    isRecord(value) &&
    isBoolean(value.success) &&
    isOptional(value.accession, isString) &&
    isOptional(value.residues, isNumber) &&
    (value.mean_plddt === null || isOptional(value.mean_plddt, isNumber)) &&
    isOptional(value.source_name, isString) &&
    isOptional(value.selection_metric, isString) &&
    isOptional(value.candidates, (c): c is StructureModelCandidate[] =>
      isArrayOf(c, isStructureModelCandidate),
    ) &&
    isOptional(value.error, isString)
  );
}

function isFetchInterfaceResiduesResult(value: unknown): value is FetchInterfaceResiduesResult {
  return (
    isRecord(value) &&
    isNumberArray(value.interface_positions) &&
    isString(value.source) &&
    isOptional(value.pdb_id, isString) &&
    isOptional(value.error, isString) &&
    isOptional(value.note, isString)
  );
}
function isFetchPdbTextResult(value: unknown): value is FetchPdbTextResult {
  return (
    isRecord(value) &&
    isBoolean(value.success) &&
    isString(value.accession) &&
    (value.pdb_text === null || isString(value.pdb_text)) &&
    isString(value.source)
  );
}

function isPredictStructureEsmfoldResult(value: unknown): value is PredictStructureEsmfoldResult {
  return (
    isRecord(value) &&
    isBoolean(value.success) &&
    (value.source === "esmfold" || value.source === "esmfold_cache" || value.source === "error") &&
    (value.pdb_text === null || isString(value.pdb_text)) &&
    isNumber(value.plddt_mean) &&
    isNumber(value.residue_count) &&
    value.coordinate_frame === "reference" &&
    isString(value.seq_hash) &&
    isBoolean(value.cache_hit) &&
    isOptional(value.error_msg, isString)
  );
}

function isFetchActiveSiteResult(value: unknown): value is FetchActiveSiteResult {
  return (
    isRecord(value) &&
    isString(value.accession) &&
    isNumberArray(value.active_site_positions) &&
    isNumberArray(value.binding_positions) &&
    isString(value.source) &&
    isBoolean(value.has_annotation) &&
    isOptional(value.features, (items) => isArrayOf(items, isRecord)) &&
    isOptional(value.annotation_status, (item) => item === "present" || item === "no_matching_features" || item === "error") &&
    isOptionalNullable(value.sequence_version, isNumber) &&
    isOptional(value.projection_status, (item) => item === "unverified")
  );
}
function isNullHistogram(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNumber(value.min) &&
    isNumber(value.max) &&
    isNumberArray(value.counts)
  );
}


function isComputeDispersionResult(value: unknown): value is ComputeDispersionResult {
  return (
    isRecord(value) &&
    isString(value.accession) &&
    isNumberArray(value.mapped) &&
    isNumberArray(value.dropped) &&
    isNumber(value.n_positions) &&
    isNumber(value.mean_pairwise) &&
    isNumber(value.null_mean) &&
    isNumber(value.null_p05) &&
    isNumber(value.null_p95) &&
    isNumber(value.percentile) &&
    isString(value.klass) &&
    isNumber(value.n_trials) &&
    (value.seed === null || value.seed === undefined || isNumber(value.seed)) &&
    isNullHistogram(value.null_hist)
  );
}


function isRunBenchmarkResult(value: unknown): value is RunBenchmarkResult {
  return (
    isRecord(value) &&
    isRecordOf(value.results, isBenchmarkResult) &&
    isOptional(value.structure_frame_mismatch, isBoolean)
  );
}

function isCancelDesignResult(value: unknown): value is CancelDesignResult {
  return (
    isRecord(value) &&
    isBoolean(value.cancelled) &&
    isOptional(value.active_design, isBoolean)
  );
}

function isPreviewEvolveproSourceResult(value: unknown): value is EvolveproPreview {
  return (
    isRecord(value) &&
    isArrayOf(value.sheets, isString) &&
    isArrayOf(value.headers, isString) &&
    isArrayOf(value.rows, (row): row is string[] => isArrayOf(row, isString))
  );
}

/**
 * One `export_echo_mapping_dry_run` row.
 *
 * Ground truth is `build_echo_rows`, `kuma_core/kuro/plate_mapper.py:897-905`
 * (forward block) and `:925-933` (reverse block). Both emit the same eight keys
 * and no others, and none is conditional.
 *
 * `transfer_vol` here is the PER-ROW split volume from `_split_echo_volume`
 * (`plate_mapper.py:675`), not the envelope volume: a transfer above 500 nL is
 * emitted as several rows, so the row value and the envelope value legitimately
 * differ and the guard does not tie them together.
 */
function isEchoDryRunRow(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.source_plate) &&
    isString(value.source_well_name) &&
    isString(value.source_well) &&
    isString(value.dest_plate) &&
    isString(value.dest_well_name) &&
    isString(value.dest_well) &&
    isNumber(value.transfer_vol) &&
    isString(value.mutation)
  );
}

/**
 * One `export_janus_mapping_dry_run` row.
 *
 * Ground truth is `build_janus_rows`, `kuma_core/kuro/plate_mapper.py:1048-1058`
 * (forward) and `:1071-1082` (reverse). The volume key is `volume` here, where
 * the Echo row calls the same quantity `transfer_vol`; the two builders really
 * do disagree, so the guards do too.
 *
 * `role` is the one optional field, and it is optional for a stated reason
 * rather than for safety: a packaged sidecar predating the field omits it and
 * the preview drops the row (see the `RpcMethodMap` comment on this result).
 * Present-but-wrong is still refused.
 */
function isJanusDryRunRow(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.name) &&
    isString(value.type) &&
    isNumber(value.no) &&
    isString(value.asp_rack) &&
    isString(value.asp_posi) &&
    isString(value.dsp_rack) &&
    isString(value.dsp_posi) &&
    isNumber(value.volume) &&
    isString(value.mutation) &&
    (value.role === undefined || value.role === "fwd" || value.role === "rev")
  );
}

/**
 * `SettingsBundle` and its three nested groups.
 *
 * Every field is checked ONLY when present, which is not laziness: the Pydantic
 * models give all of them defaults (`python-core/sidecar_kuro/models.py:1020-1058`),
 * so `scripts/gen-models.mjs` emits every field optional in
 * `src/types/models.generated.ts:926-962`. A guard demanding all of them would
 * refuse payloads the declared type calls legal.
 *
 * What it does buy over the `"settings" in value` membership test it replaces:
 * `{settings: null}`, `{settings: []}`, a `theme` outside the three literals and
 * a non-boolean consent flag are all refused now, and each of those reaches a
 * settings screen that renders it.
 */
function isSettingsNetwork(value: unknown): boolean {
  return (
    isRecord(value) &&
    isOptional(value.offline_mode, isBoolean) &&
    isOptional(value.consent_uniprot, isBoolean) &&
    isOptional(value.consent_blast, isBoolean) &&
    isOptional(value.consent_alphafold, isBoolean) &&
    isOptional(value.consent_interpro, isBoolean) &&
    isOptional(value.consent_esmfold, isBoolean)
  );
}

function isSettingsBundle(value: unknown): boolean {
  return (
    isRecord(value) &&
    isOptional(value.language, isString) &&
    isOptional(
      value.theme,
      (v) => v === "light" || v === "dark" || v === "auto",
    ) &&
    isOptionalNullable(value.default_workspace_folder, isString) &&
    isOptional(value.network, isSettingsNetwork)
  );
}

/**
 * `health_info`.
 *
 * Ground truth is the dict literal in `python-core/sidecar_kuro/dispatcher.py:69-82`:
 * `{"pid": os.getpid(), "rss_bytes": <int>, "py_version": <str>}`. `rss_bytes`
 * falls back to `0` rather than being omitted when the memory monitor import
 * fails, so all three keys are unconditionally present and none is optional.
 *
 * `isNumber` is `Number.isFinite`-backed on purpose: the status bar divides
 * `rss_bytes` by 1024^2 and renders it, and `NaN MB` is a worse tooltip than a
 * refused probe.
 */
function isHealthInfo(value: unknown): value is HealthInfo {
  return (
    isRecord(value) &&
    isNumber(value.pid) &&
    isNumber(value.rss_bytes) &&
    isString(value.py_version)
  );
}

const rpcResultValidators = {
  health_info: (value): value is RpcMethodResult<"health_info"> =>
    isHealthInfo(value),
  list_polymerases: (value): value is RpcMethodResult<"list_polymerases"> =>
    isArrayOf(value, isPolymeraseInfo),
  get_polymerase_details: (value): value is RpcMethodResult<"get_polymerase_details"> =>
    isPolymeraseProfile(value),
  save_custom_polymerase: (value): value is RpcMethodResult<"save_custom_polymerase"> =>
    isSaveCustomPolymeraseResult(value),
  list_organisms: (value): value is RpcMethodResult<"list_organisms"> =>
    isListOrganismsResult(value),
  compute_codon_table: (value): value is RpcMethodResult<"compute_codon_table"> =>
    isComputeCodonTableResult(value),
  import_codon_table: (value): value is RpcMethodResult<"import_codon_table"> =>
    isImportCodonTableResult(value),
  export_codon_table: (value): value is RpcMethodResult<"export_codon_table"> =>
    isExportCodonTableResult(value),
  load_fasta: (value): value is RpcMethodResult<"load_fasta"> =>
    isSequenceInfo(value),
  parse_mutations_text: (value): value is RpcMethodResult<"parse_mutations_text"> =>
    isParseMutationsResult(value),
  design_sdm_primers: (value): value is RpcMethodResult<"design_sdm_primers"> =>
    isDesignResult(value),
  load_evolvepro_csv: (value): value is RpcMethodResult<"load_evolvepro_csv"> =>
    isEvolveproLoadResult(value),
  inspect_prediction_bundle: (value): value is RpcMethodResult<"inspect_prediction_bundle"> =>
    isPredictionBundleInventory(value),
  get_plate_map: (value): value is RpcMethodResult<"get_plate_map"> =>
    isPlateMapResult(value),
  get_alternatives: (value): value is RpcMethodResult<"get_alternatives"> =>
    isAlternativesResult(value),
  swap_primer: (value): value is RpcMethodResult<"swap_primer"> =>
    isSdmPrimerResult(value),
  commit_design_result: (value): value is RpcMethodResult<"commit_design_result"> =>
    isSdmPrimerResult(value),
  export_excel: (value): value is RpcMethodResult<"export_excel"> =>
    isExportResult(value),
  export_order: (value): value is RpcMethodResult<"export_order"> =>
    isExportOrderResult(value),
  export_mapping: (value): value is RpcMethodResult<"export_mapping"> =>
    isExportMappingResult(value),
  // Envelope from python-core/sidecar_kuro/handlers/export.py:782 (and the two
  // empty early returns at :758 and :769, which carry the same three keys).
  // The rows are checked element by element rather than with a bare
  // Array.isArray, and the numbers go through isNumber, so NaN and Infinity are
  // refused here as they are everywhere else in this file.
  export_echo_mapping_dry_run: (value): value is RpcMethodResult<"export_echo_mapping_dry_run"> =>
    isRecord(value) &&
    isArrayOf(value.rows, isEchoDryRunRow) &&
    isNumber(value.total) &&
    isNumber(value.transfer_vol),
  // export.py:827, empty early returns at :806 and :817. The envelope
  // transfer_vol is a float here where Echo emits an int; both are just numbers
  // on the wire, so the guard is the same and the difference is only noted.
  export_janus_mapping_dry_run: (value): value is RpcMethodResult<"export_janus_mapping_dry_run"> =>
    isRecord(value) &&
    isArrayOf(value.rows, isJanusDryRunRow) &&
    isNumber(value.total) &&
    isNumber(value.transfer_vol),
  export_macrogen: (value): value is RpcMethodResult<"export_macrogen"> =>
    typeof value === "object" && value !== null &&
    (value as { ok?: unknown }).ok === true &&
    typeof (value as { path?: unknown }).path === "string",
  export_all: (value): value is RpcMethodResult<"export_all"> =>
    isRecord(value) &&
    isStringArray(value.success) &&
    isArrayOf(value.failed, (v) => isRecord(v) && isString(v.path) && isString(v.reason)) &&
    isString(value.output_dir) &&
    (value.vectormaps === undefined ||
      (isRecord(value.vectormaps) &&
        isString(value.vectormaps.output_dir) &&
        isStringArray(value.vectormaps.success) &&
        isArrayOf(value.vectormaps.failed, (v) => isRecord(v) && isString(v.path) && isString(v.reason)) &&
        (value.vectormaps.skipped_reason === null || isString(value.vectormaps.skipped_reason)) &&
        typeof value.vectormaps.sha_checked === "boolean")),
  export_benchmark_csv: (value): value is RpcMethodResult<"export_benchmark_csv"> =>
    isExportResult(value),
  evaluate_primer: (value): value is RpcMethodResult<"evaluate_primer"> =>
    isSdmPrimerResult(value),
  retry_failed_mutation: (value): value is RpcMethodResult<"retry_failed_mutation"> =>
    isAlternativesResult(value),
  save_json: (value): value is RpcMethodResult<"save_json"> =>
    isExportResult(value),
  save_workspace: (value): value is RpcMethodResult<"save_workspace"> =>
    isExportResult(value),
  load_workspace: (value): value is RpcMethodResult<"load_workspace"> =>
    isWorkspaceData(value),
  fetch_domains: (value): value is RpcMethodResult<"fetch_domains"> =>
    isFetchDomainsResult(value),
  annotate_domains_by_sequence: (value): value is RpcMethodResult<"annotate_domains_by_sequence"> =>
    isAnnotateDomainsResult(value),
  search_uniprot: (value): value is RpcMethodResult<"search_uniprot"> =>
    isSearchUniprotResult(value),
  check_structures_available: (value): value is RpcMethodResult<"check_structures_available"> =>
    isStructureAvailabilityResult(value),
  fetch_structure: (value): value is RpcMethodResult<"fetch_structure"> =>
    isStructureResult(value),
  load_structure_file: (value): value is RpcMethodResult<"load_structure_file"> =>
    isLoadStructureFileResult(value),
  fetch_interface_residues: (value): value is RpcMethodResult<"fetch_interface_residues"> =>
    isFetchInterfaceResiduesResult(value),
  run_benchmark: (value): value is RpcMethodResult<"run_benchmark"> =>
    isRunBenchmarkResult(value),
  cancel_design: (value): value is RpcMethodResult<"cancel_design"> =>
    isCancelDesignResult(value),
  // Phase 3: Settings
  // SettingsLoadResponse / SettingsSaveResponse,
  // python-core/sidecar_kuro/models.py:1063 and :1075. These replace membership
  // tests (`"settings" in value`, `"ok" in value && "path" in value`) that
  // accepted {settings: null} and {ok: false, path: null} unchanged.
  settings_load: (value): value is RpcMethodResult<"settings_load"> =>
    isRecord(value) &&
    isSettingsBundle(value.settings) &&
    (value.effective_contact_email === undefined ||
      value.effective_contact_email === null ||
      isString(value.effective_contact_email)) &&
    (value.contact_email_source === undefined ||
      value.contact_email_source === "env" ||
      value.contact_email_source === "preferences" ||
      value.contact_email_source === "legacy_config" ||
      value.contact_email_source === "none"),
  settings_save: (value): value is RpcMethodResult<"settings_save"> =>
    isRecord(value) && isBoolean(value.ok) && isString(value.path),
  preview_evolvepro_source: (value): value is RpcMethodResult<"preview_evolvepro_source"> =>
    isPreviewEvolveproSourceResult(value),
  // G001: 3D Analysis panel RPCs
  fetch_pdb_text: (value): value is RpcMethodResult<"fetch_pdb_text"> =>
    isFetchPdbTextResult(value),
  fetch_active_site_residues: (value): value is RpcMethodResult<"fetch_active_site_residues"> =>
    isFetchActiveSiteResult(value),
  compute_dispersion: (value): value is RpcMethodResult<"compute_dispersion"> =>
    isComputeDispersionResult(value),
  predict_structure_esmfold: (value): value is RpcMethodResult<"predict_structure_esmfold"> =>
    isPredictStructureEsmfoldResult(value),
} satisfies { [K in RpcMethod]: (value: unknown) => value is RpcMethodResult<K> };

export function getRpcResultValidator<K extends RpcMethod>(
  method: K,
): (value: unknown) => value is RpcMethodResult<K> {
  return rpcResultValidators[method];
}
