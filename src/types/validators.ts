import type {
  AlternativesResult,
  CancelDesignResult,
  ComputeDispersionResult,
  DesignResult,
  EvolveproLoadResult,
  ExportMappingResult,
  ExportOrderResult,
  ExportResult,
  FetchActiveSiteResult,
  FetchDomainsResult,
  FetchInterfaceResiduesResult,
  FetchPdbTextResult,
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
  WorkspaceData,
} from "./models";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
    isNumber(value.opt_size) &&
    isNumber(value.min_size) &&
    isNumber(value.max_size) &&
    isNumber(value.min_gc) &&
    isNumber(value.max_gc) &&
    isNumber(value.salt_monovalent) &&
    isNumber(value.salt_divalent) &&
    isNumber(value.dntp_conc) &&
    isNumber(value.dna_conc) &&
    isNumber(value.max_tm_diff) &&
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
    isRecordOf(value.results, isBenchmarkResult)
  );
}

function isCancelDesignResult(value: unknown): value is CancelDesignResult {
  return (
    isRecord(value) &&
    isBoolean(value.cancelled) &&
    isOptional(value.active_design, isBoolean)
  );
}

const rpcResultValidators = {
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
  export_echo_mapping_dry_run: (value): value is RpcMethodResult<"export_echo_mapping_dry_run"> =>
    typeof value === "object" && value !== null &&
    Array.isArray((value as { rows?: unknown }).rows) &&
    typeof (value as { total?: unknown }).total === "number" &&
    typeof (value as { transfer_vol?: unknown }).transfer_vol === "number",
  export_janus_mapping_dry_run: (value): value is RpcMethodResult<"export_janus_mapping_dry_run"> =>
    typeof value === "object" && value !== null &&
    Array.isArray((value as { rows?: unknown }).rows) &&
    typeof (value as { total?: unknown }).total === "number" &&
    typeof (value as { transfer_vol?: unknown }).transfer_vol === "number",
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
  search_uniprot: (value): value is RpcMethodResult<"search_uniprot"> =>
    isSearchUniprotResult(value),
  check_structures_available: (value): value is RpcMethodResult<"check_structures_available"> =>
    isStructureAvailabilityResult(value),
  fetch_structure: (value): value is RpcMethodResult<"fetch_structure"> =>
    isStructureResult(value),
  fetch_interface_residues: (value): value is RpcMethodResult<"fetch_interface_residues"> =>
    isFetchInterfaceResiduesResult(value),
  run_benchmark: (value): value is RpcMethodResult<"run_benchmark"> =>
    isRunBenchmarkResult(value),
  cancel_design: (value): value is RpcMethodResult<"cancel_design"> =>
    isCancelDesignResult(value),
  // Phase 3: Settings
  settings_load: (value): value is RpcMethodResult<"settings_load"> =>
    typeof value === "object" && value !== null && "settings" in value,
  settings_save: (value): value is RpcMethodResult<"settings_save"> =>
    typeof value === "object" && value !== null && "ok" in value && "path" in value,
  preview_evolvepro_source: (value): value is RpcMethodResult<"preview_evolvepro_source"> =>
    typeof value === "object" && value !== null &&
    "sheets" in value && "headers" in value && "rows" in value,
  // G001: 3D Analysis panel RPCs
  fetch_pdb_text: (value): value is RpcMethodResult<"fetch_pdb_text"> =>
    isFetchPdbTextResult(value),
  fetch_active_site_residues: (value): value is RpcMethodResult<"fetch_active_site_residues"> =>
    isFetchActiveSiteResult(value),
  compute_dispersion: (value): value is RpcMethodResult<"compute_dispersion"> =>
    isComputeDispersionResult(value),
} satisfies { [K in RpcMethod]: (value: unknown) => value is RpcMethodResult<K> };

export function getRpcResultValidator<K extends RpcMethod>(
  method: K,
): (value: unknown) => value is RpcMethodResult<K> {
  return rpcResultValidators[method];
}
