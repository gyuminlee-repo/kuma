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
  LoadStructureFileResult,
  WorkspaceData,
} from "./models";

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
 * a result those guards cover (the two that do return lists,
 * `list_polymerases` and `list_organisms`, go through `isArrayOf` instead).
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

function isOrganismSummary(
  value: unknown,
): value is { key: string; name: string; taxid: number } {
  return (
    isRecord(value) &&
    isString(value.key) &&
    isString(value.name) &&
    isNumber(value.taxid)
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
    isOptional(value.error_msg, isString)
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
    isOptionalNullable(value.step_stats, isEvolveproStepStats)
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
    isString(value.selectedGene)
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
      Array.isArray(value.rounds) &&
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
    isOptionalNullable(value.error_detail, isString)
  );
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
    Array.isArray(value.interface_positions) &&
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
    isBoolean(value.has_annotation)
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
    isOptional(value.consent_interpro, isBoolean)
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
    isArrayOf(value, isOrganismSummary),
  load_fasta: (value): value is RpcMethodResult<"load_fasta"> =>
    isSequenceInfo(value),
  parse_mutations_text: (value): value is RpcMethodResult<"parse_mutations_text"> =>
    isParseMutationsResult(value),
  design_sdm_primers: (value): value is RpcMethodResult<"design_sdm_primers"> =>
    isDesignResult(value),
  load_evolvepro_csv: (value): value is RpcMethodResult<"load_evolvepro_csv"> =>
    isEvolveproLoadResult(value),
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
    typeof value === "object" && value !== null &&
    Array.isArray((value as { success?: unknown }).success) &&
    Array.isArray((value as { failed?: unknown }).failed) &&
    typeof (value as { output_dir?: unknown }).output_dir === "string",
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
    isRecord(value) && isSettingsBundle(value.settings),
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
