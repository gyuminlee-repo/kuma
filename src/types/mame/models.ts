import type { RunQuality } from "./run_quality";
import type { ReactNode } from "react";

export type VerdictClass =
  | "PASS"
  | "AMBIGUOUS"
  | "MIXED"
  | "FRAMESHIFT"
  | "MANY"
  | "LOWDEPTH"
  | "NO_CALL"
  | "WRONG_AA";

export type SidecarStatus = "disconnected" | "connecting" | "ready" | "error";

/**
 * One mix-eligible reference position and the strand split of its minor allele.
 * Mirror of `NoisyPosition` in `kuma_core/mame/models.py`.
 *
 * `position` is 1-based, matching the `{REF}{pos}{QRY}` nucleotide notation the
 * rest of MAME shows. `plus_count` and `minus_count` split the reads supporting
 * the MINOR ALLELE by aligned strand, so they sum to that allele count and not
 * to `depth`; `minor_fraction` is exactly `(plus_count + minus_count) / depth`,
 * and the transported value is rounded for display.
 */
export interface NoisyPosition {
  position: number;
  minor_fraction: number;
  depth: number;
  plus_count: number;
  minus_count: number;
}

export interface VerdictRecord {
  native_barcode: string;
  custom_barcode: string;
  file_size_kb: number;
  read_count: number | null;
  n_mixed_positions: number;
  max_minor_allele_fraction: number;
  /**
   * The noise floor this well ran at: the median minor-allele fraction across
   * its positions. `max_minor_allele_fraction` cannot be read without it --
   * 0.04 is a clean well when ordinary positions sit at 0.03 and a
   * contaminated one when they sit at 0.002.
   *
   * Optional because results persisted before the field was serialized are
   * replayed verbatim; a live sidecar always sends it. `undefined` means the
   * floor is unknown and must be shown as unknown, never as 0.
   */
  median_minor_allele_fraction?: number;
  /**
   * Weak-strand share, `min(plus, minus) / (plus + minus)`, of the minor allele
   * at the position that produced `max_minor_allele_fraction`. A
   * sequence-context sequencing artifact is read off one strand and lands near
   * 0; a real per-clone mixture is read off both. The same both-strands
   * principle is the acceptance rule in ampliCan (Labun et al. 2019,
   * doi:10.1101/gr.244293.118).
   *
   * `undefined` means UNKNOWN: the well had no mix-eligible position, or the
   * result predates the field. `0` is a real measurement saying the minor
   * allele came off one strand only, which is the artifact reading, so the two
   * must never be collapsed. Reported only; no verdict reads it.
   */
  max_minor_allele_strand_share?: number;
  /**
   * The two counts that share divides, present exactly when the share is. In a
   * thin well where nearly every read happened to be one strand, a share of 0
   * means no strand information was available rather than artifact, and only
   * these tell the two apart.
   */
  max_minor_allele_plus_count?: number;
  max_minor_allele_minus_count?: number;
  /**
   * Coverage uniformity and consensus identity, measured off the same
   * per-position depth vector `read_count` summarizes. A well covered evenly at
   * 100x and one averaging 100x with a 200 bp hole report the same depth and are
   * not the same evidence; these five say which one it was.
   *
   * - `depth_cv`: spread of covered depth relative to its own level. 0 is flat.
   * - `depth_p10`: 10th percentile of covered depth, the thin tenth.
   * - `depth_min_covered`: shallowest covered position, never 0 by construction.
   * - `breadth_at_mix_min_depth`: fraction of the WHOLE reference deep enough
   *   for a minor allele to be worth reading. This is the one that exposes a
   *   hole, since the CV only ranges over covered positions.
   * - `consensus_identity`: fraction of CALLED consensus bases matching the
   *   reference.
   *
   * `null` and `undefined` both mean NOT MEASURED and must be rendered as
   * unknown, never as 0: a CV of 0 is a perfectly flat well and an identity of 0
   * is a consensus matching the reference nowhere, both of which are strong
   * readings. The sidecar omits a key it did not measure, and the five are
   * omitted independently -- a well with no reads still reports a real
   * `breadth_at_mix_min_depth` of 0 with the other four absent.
   *
   * Reported only; no verdict, gate or severity rule reads any of them.
   */
  depth_cv?: number | null;
  depth_p10?: number | null;
  depth_min_covered?: number | null;
  breadth_at_mix_min_depth?: number | null;
  consensus_identity?: number | null;
  /**
   * How many mix-eligible positions this well had, i.e. the pool
   * `noisy_positions` was sampled from. `noisy_positions.length <
   * n_eligible_positions` says the sample is truncated, which on a real ONT
   * amplicon it always is: both measured runs filled the ten-position budget in
   * every well. Without it a recurrence tally across wells reads as a census.
   *
   * Optional only because results persisted before this field are replayed
   * verbatim; a live sidecar always sends it, and 0 from a live run is a real
   * answer (nothing eligible).
   */
  n_eligible_positions?: number;
  /**
   * The sample itself, ranked by minor fraction descending with ascending
   * position as the tie-break. Empty when the well had no eligible position.
   */
  noisy_positions?: NoisyPosition[];
  n_low_depth_positions: number;
  consensus_n_fraction: number;
  /**
   * Whether `consensus_n_fraction` means anything for this well. `false` is a
   * consensus written before the covered-scoped N-fraction definition: the
   * number could not be recovered, 0.0 was substituted, and the NO_CALL gate
   * was skipped rather than run against a value that measures something else
   * (`kuma_core/mame/compare/verdict.py`). Reading a substituted 0.0 as a
   * measured 0.0 reports an unmeasurable well as a clean one.
   *
   * Optional for the same replay reason as above. `undefined` is "this result
   * predates the flag", which is distinct from `false`, so it must not be
   * collapsed into either boolean.
   */
  consensus_n_fraction_evaluable?: boolean;
  n_low_quality_bases: number;
  n_input_reads: number | null;
  n_aligned_reads: number | null;
  n_mapq_failed: number;
  n_span_failed: number;
  source_path: string;
  aa_sequence: string;
  observed_nt_changes: string[];
  observed_aa_changes: string[];
  n_no_call_aa: number;
  expected_mutations: string[];
  /**
   * Per-well variant identity assigned by the pipeline (run-layout ground truth
   * in combinatorial-sort runs, else the observation/heuristic grouping result).
   * Authoritative per-well source for the verdict table's mutant-id column.
   * Empty string for legacy payloads persisted before this field existed.
   */
  mutant_id: string;
  verdict: VerdictClass;
  verdict_notes: string;
}

export interface ReplicateResult {
  mutant_id: string;
  selected_plate: string | null;
  selection_reason: string;
  failed: boolean;
  plate_keys: string[];
  // Full verdict dict per native_barcode, serialized by the sidecar
  // (_serialize_replicate). This is the ONLY lossless source for per-plate
  // accent (selected / is_fallback) restoration. The frontend persists +
  // replays the analyze response AS-IS including this field; reconstructing
  // from plate_keys alone silently corrupts well flags.
  plate_verdicts: Record<string, VerdictRecord>;
  is_fallback: boolean;
  fallback_reason: string | null;
}

/**
 * One axis of a barcode workbook, as `BarcodeAxisPrefixes.as_dict` sends it
 * (`kuma_core/mame/ingest/combinatorial_demux.py:443-452`).
 */
export interface BarcodeAxisPrefixes {
  /** `"F"` or `"R"`, but declared `str` on the Python side. */
  axis: string;
  /** The tail that was stripped, uppercase. */
  tail: string;
  tail_length: number;
  barcode_count: number;
  /** One entry per barcode, in barcode-index order. Ragged axes vary. */
  seed_lengths: number[];
}

/**
 * What was cut off the barcode seeds on each axis, and what was left.
 *
 * Mirrors `BarcodePrefixResolution.as_dict`
 * (`kuma_core/mame/ingest/combinatorial_demux.py:487-493`). Every instance
 * describes a file that explained itself; one that does not raises out of
 * `load_barcode_prefixes_with_provenance` rather than reaching this shape.
 */
export interface BarcodePrefixResolution {
  forward: BarcodeAxisPrefixes;
  reverse: BarcodeAxisPrefixes;
  /** One operator-facing paragraph, built at `combinatorial_demux.py:471-485`. */
  note: string;
}

export interface DistributionFileStats {
  min: number;
  p05: number;
  p25: number;
  median: number;
  p75: number;
  p95: number;
  max: number;
  mean: number;
  std: number;
}

export interface DistributionStats {
  n_files: number;
  /**
   * All nine statistics, or nothing at all.
   *
   * `compute_distribution_stats` builds the nine keys unconditionally
   * (`kuma_core/mame/distribution.py:132-142`), so a populated object is never
   * partial. But an empty input list takes the early return at
   * `distribution.py:119-120`, which leaves the field at its
   * `field(default_factory=dict)` default (`distribution.py:39`) and puts `{}`
   * on the wire verbatim (`python-core/sidecar_mame/handlers/analyze.py:2244`).
   *
   * That path is reachable: the empty-records refusal at `analyze.py:1912` is
   * gated on `is_raw`, so a pre-demuxed consensus directory with no consensus
   * FASTA reaches `compute_distribution_stats([])` with nothing to refuse it.
   * The co-occurring signal is `n_files === 0`.
   */
  file_size_kb: DistributionFileStats | Record<string, never>;
  suggested_cutoff_kb: number;
  suggested_method: "median_minus_2sigma" | "p05" | "kneedle" | "fixed_50";
  bimodal: boolean;
}

export interface AnalyzeSummary {
  total: number;
  pass_count: number;
  ambiguous_count: number;
  mixed_count?: number;
  fail_count: number;
}

/**
 * Which of the two well->sample sources an `analyze` run actually scored
 * wells against, mirrored from `python-core/sidecar_mame/handlers/analyze.py`
 * (`layout_source` assignment). An `inferred_draft_layout` result was drafted
 * from whatever `expected` happened to be current at analyze time, not stated
 * by the operator -- the failure shape of the 2026-08
 * mapping-integrity incident (a stale `expected` produced a plausible-looking
 * inferred layout with nothing in the result to say so). Frontend code that
 * persists or replays a well_layout MUST check `source` first: promoting an
 * inferred layout to an explicit one on the next run launders exactly the
 * provenance this field exists to keep (`useAutosaveHydration.ts`).
 */
export interface LayoutProvenance {
  source: "explicit_well_layout" | "inferred_draft_layout";
  expected_path: string;
  /**
   * Wells this run declared as occupied, in plate order, or null when it
   * declared none (which reads as the leading N+1). Stamped onto the result
   * because a selection is what makes an empty well mean "nothing was pipetted
   * here" rather than "the draft ran out", and a result that cannot say which
   * wells were declared cannot be reproduced.
   *
   * Optional: absent on results persisted before this field existed.
   */
  selected_wells?: string[] | null;
  /**
   * Declared wells no sample took, in plate order. Empty for a run that
   * declared none or declared exactly enough.
   *
   * Selecting more wells than the campaign fills is not a mistake (a column
   * that turned out to hold fewer variants than planned says nothing false
   * about the bench), so it runs. It must not run in silence: the placement
   * rule uses the leading wells, and without this the rest read exactly like
   * wells that were never declared at all.
   *
   * Optional for the same reason as `selected_wells`.
   */
  unused_wells?: string[];
  /**
   * Draft occupants the declaration left out, `{well: sample}` in plate order.
   *
   * The placement is anchored to the plate, so leaving a well out of the
   * declaration says the campaign did not fill it, and what the draft put there
   * was never sequenced. Those variants have no verdict anywhere else on the
   * result, so without this the only trace of them is an absence.
   *
   * Optional for the same reason as `selected_wells`.
   */
  excluded_occupants?: Record<string, string>;
}

/**
 * Records that arrived from wells the run layout does not name.
 *
 * Reported, never a refusal. A declared-empty well producing reads is the same
 * signal as barcode crosstalk, and the count alone does not say which it is.
 */
export interface OffLayoutRecords {
  count: number;
  wells: { well: string; records: number }[];
}

/**
 * The six stray-read signals `kuma_core/mame/qc/contamination.py` reports, in
 * the order the panel shows them: the two well-scoped counts first (they name
 * wells an operator can go and look at), then the two run-wide rates, then the
 * two that need a replicate axis.
 */
export const CONTAMINATION_SIGNAL_NAMES = [
  "unused_index_reads",
  "unexpected_well_reads",
  "ambiguity_rate",
  "chimera_rate",
  "leak_well_sharing",
  "plate_yield_skew",
] as const;

export type ContaminationSignalName = (typeof CONTAMINATION_SIGNAL_NAMES)[number];

/** One well that carried reads the layout did not ask for. */
export interface ContaminationLeakWell {
  well: string;
  reads: number;
  /** Only on `leak_well_sharing`: how many plate copies saw reads here. */
  replicates_with_reads?: number;
  /** Only on `leak_well_sharing`: the per-copy counts, in plate order. */
  per_replicate?: number[];
  label?: "shared_across_replicates" | "single_replicate";
}

/**
 * One signal: a measurement, or the reason there is none.
 *
 * `state` is the discriminator and it must be read first. An `unavailable`
 * signal carries NO `value`, deliberately: a question that could not be asked
 * has no answer, and a 0 in its place would read as a clean plate. The UI must
 * therefore never fall back to `value ?? 0`.
 */
export interface ContaminationSignal {
  state: "ok" | "unavailable";
  /** Present iff `state === "ok"`. A read count, a 0..1 rate, or a well count. */
  value?: number;
  /** Present iff `state === "unavailable"`. A sentence, already phrased for display. */
  reason?: string;
  /** `unused_index_reads`, `unexpected_well_reads`, `leak_well_sharing`. */
  wells?: ContaminationLeakWell[];
  /** `leak_well_sharing`: where the stray reads sit relative to the copies. */
  label?: "shared_across_replicates" | "single_replicate";
  ambiguous_dropped?: number;
  passed_coverage?: number;
  chimera_splits?: number;
  assigned_reads?: number;
  shared_reads?: number;
  single_replicate_reads?: number;
  /** `plate_yield_skew`: the assigned-read total of each plate copy. */
  per_replicate?: { plate: string; assigned_reads: number }[];
}

/**
 * What the demux matrix says about reads that landed outside the campaign
 * (`kuma_core/mame/qc/contamination.py`).
 *
 * Raw-run only: the handler omits the key entirely in consensus-dir mode, which
 * never demuxed and so has no matrix to read. Absent therefore means "this run
 * could not measure it", never "this run measured nothing".
 *
 * `occupancy_source` is `layout_provenance.source` verbatim. Every signal is
 * measured against the occupied wells, so a reader who does not know whether
 * those wells were declared by the operator or inferred from `expected` cannot
 * weigh any of the numbers.
 */
export interface ContaminationReport {
  occupancy_source: LayoutProvenance["source"];
  occupied_wells: number;
  /** Plate copies scored. 0 for a pooled run, which has no replicate axis. */
  replicates: number;
  plate_names: string[];
  signals: Record<ContaminationSignalName, ContaminationSignal>;
}

/**
 * Whole-run mapping sanity check (`kuma_core/mame/qc/mapping_integrity.py`).
 * `suspect` is a signal to surface prominently, not a hard failure: the run
 * already finished and the workbook the operator has may be the only record
 * of what was actually pipetted. Rates are 0..1 fractions, not percentages.
 */
export interface MappingIntegrity {
  wells_considered: number;
  self_match: number;
  cross_match: number;
  self_rate: number;
  cross_rate: number;
  suspect: boolean;
}

/**
 * Unit directories found in the ingested folder that the run recorded there did
 * not produce, i.e. output an earlier run left behind when the same export
 * folder was reused (`kuma_core/mame/ingest/unit_manifest.py`).
 *
 * They are excluded from the verdicts and left untouched on disk: removing a
 * previous run output is the operator's call, so this reports and stops there.
 *
 * `names` may be empty, and empty is not the same as the whole field being
 * absent. Present with no names says the folder carried a run manifest and
 * holds nothing stale. Absent says there was no manifest to check against,
 * which is the case for a directory somebody else sorted and pointed MAME at
 * directly, where every subdirectory is meant to be read and "stale" has no
 * meaning. Zero-filling the absent case would claim a check nobody ran.
 *
 * `run_dir` and `written_at` describe the run that DID own the folder, so the
 * operator can tell which of their runs the leftovers belong to.
 */
export interface StaleUnits {
  names: string[];
  run_dir: string;
  written_at: string;
}

/**
 * The thresholds an `analyze` run was actually judged against, mirrored from
 * `python-core/sidecar_mame/handlers/analyze.py` (`compare_params`). Every
 * per-well number on `VerdictRecord` is a measurement; this is what each one
 * was compared to. Without it a reader cannot say why `read_count = 22`
 * failed, because the backend default applies whenever the caller omits the
 * field -- which is exactly what happens for `min_read_count`
 * (`src/store/mame/slices/inputSlice.ts` never sends it, so the backend
 * default of 30 governs and the store has no value to show).
 *
 * These are the only thresholds reported, because they are the only ones the
 * handler resolves from caller params and hands to the pipeline. The
 * classifier's indel and frameshift windows sit at their dataclass defaults on
 * every run, so they are absent here rather than reported as decisions nobody
 * made.
 *
 * Note what is NOT here: `minFilteredDepth` (store state, value 15) is a
 * display filter for the plate view and gates nothing. It must never be
 * rendered as a threshold a verdict was judged against.
 */
export interface CompareParams {
  /**
   * Fallback volume gate, in KB. Applies only to wells that carry no
   * `read_count` at all; a well with real depth is judged by `min_read_count`
   * and never by this.
   */
  min_file_size_kb: number;
  /**
   * Read-depth gate. `null` means the caller disabled it, and then the
   * file-size proxy above is the only depth gate that ran.
   */
  min_read_count: number | null;
  /** Consensus N-fraction ceiling (a 0..1 fraction). `null` disables the gate. */
  max_consensus_n_fraction: number | null;
  /**
   * AA-change count above which a well is MANY. An excess gate, not an
   * absolute one: a well is never MANY when it carries no more changes than
   * its own design calls for.
   */
  many_mutation_cutoff: number;
  /**
   * What `min_read_count` is multiplied by to get the depth a MIXED call needs
   * before it is reported as contamination rather than as LOWDEPTH.
   */
  mixed_confident_depth_factor: number;
  /**
   * That product, resolved by the backend using the classifier's own rule.
   * `null` when `min_read_count` is `null`, in which case the floor does not
   * apply. Read this instead of multiplying the two fields, so the rule lives
   * in one place.
   */
  mixed_confident_read_count: number | null;
}

/**
 * Demux yield reported by the analyze response. Raw-run mode only: the handler
 * derives every field from the demux it just ran and omits the keys entirely in
 * consensus-dir mode (`python-core/sidecar_mame/handlers/analyze.py`, raw-run
 * branch). Absent fields must stay absent in the UI rather than be defaulted to
 * a number, so a zero-result explanation never shows a count the backend did
 * not report: a 0 would read as "every read was rejected", the opposite of
 * "this mode never counted".
 *
 * The three gate counters narrow a zero-verdict run to a cause, and only in
 * combination (`DemuxStats` names, kept verbatim):
 *   total_reads      reads read out of `fastq_pass/`
 *   passed_mapq      reads that cleared the MAPQ gate; 0 against a non-zero
 *                    total_reads is the signature of a mismatched reference
 *   passed_coverage  of those, the reads that also cleared the coverage gate;
 *                    0 against a non-zero passed_mapq is the signature of a
 *                    whole-construct reference met with amplicon reads
 */
export interface AnalyzeYield {
  assigned_reads?: number;
  wells_with_reads?: number;
  total_reads?: number;
  passed_mapq?: number;
  passed_coverage?: number;
  /**
   * Why reads that cleared the alignment gates still failed to reach a well
   * (`DemuxStats` in `kuma_core/mame/ingest/combinatorial_demux.py`). The seven
   * partition the demux `ambiguous_dropped` total: every failed alignment hit
   * is charged to exactly one of them, and a hit that failed on both barcode
   * axes goes to `drop_both_axes` alone rather than being split.
   *
   * The short-window pair is keyed on the READ END, not on the F/R axis,
   * because the window is cut from the read and it is the 3' end of the read
   * that comes up short on real runs. Which axis that lands on is decided by
   * strand, so an axis-keyed pair would split one phenomenon in two and each
   * half would read as half a problem. That reasoning lives in full in the
   * `DemuxStats` docstring.
   *
   * Optional for the same reason as every field above: absent means the run
   * could not measure it (consensus-dir mode never demuxes, and a per-NB
   * resume off a marker predating the breakdown omits all seven), never that
   * the count was zero.
   */
  drop_short_window_read_5p?: number;
  drop_short_window_read_3p?: number;
  drop_no_barcode_f?: number;
  drop_no_barcode_r?: number;
  drop_ambiguous_tie_f?: number;
  drop_ambiguous_tie_r?: number;
  drop_both_axes?: number;
}

/**
 * Resume split reported by the demux this run drove
 * (`kuma_core/mame/ingest/combinatorial_demux.py`, per-NB path). A "unit" is
 * one native barcode's output dir, reseeded from its completion marker instead
 * of being re-demuxed when the marker's reference/parameter fingerprint matches
 * this run (`marker_inputs_match`).
 *
 * Reuse is already gated on that fingerprint, so this is provenance, not a
 * correctness warning: it is the only place the operator can see that part of
 * the result predates this run. Absent (not zero-filled) in consensus-dir and
 * single-pool modes, which have no per-unit markers, for the same reason the
 * `AnalyzeYield` counters are absent there.
 */
export interface DemuxResume {
  reused_units: number;
  recomputed_units: number;
}

export interface AnalyzeResult extends AnalyzeYield {
  verdicts: VerdictRecord[];
  replicates: ReplicateResult[];
  output_path: string;
  summary: AnalyzeSummary;
  distribution_stats: DistributionStats;
  /**
   * Distinct designed mutant_ids, sorted. The denominator recovery (재현율) is
   * measured against; a live sidecar always sends it. Optional on the type
   * only because a result persisted before the field existed is replayed
   * verbatim, and there recovery reads as n/a rather than as 0 %.
   */
  designed_mutant_ids?: string[];
  reference_resolution?: {
    readonly path: string;
    readonly extracted: boolean;
    readonly span_start: number | null;
    readonly span_end: number | null;
    readonly original_length: number;
    readonly cds_start: number;
    readonly cds_end: number;
    readonly note: string;
  };
  /**
   * What became of the pick list this run wrote beside its workbook.
   * Optional on the type because a snapshot persisted before the field existed
   * is replayed verbatim; a live sidecar always sends it.
   */
  janus_autosave?: JanusAutosaveResult;
  /**
   * Which well->sample source this run scored against, and the files it came
   * from. A live sidecar always sends it; optional on the type only because a
   * result persisted before this field existed is replayed verbatim on
   * restart and has no value to fall back to.
   */
  layout_provenance?: LayoutProvenance;
  /**
   * Whole-run mapping sanity check. Same optionality reasoning as
   * `layout_provenance`: always sent by a live sidecar, absent on results
   * persisted before this field existed.
   */
  mapping_integrity?: MappingIntegrity;
  stale_units?: StaleUnits;
  /**
   * The thresholds this run was judged against. Same optionality reasoning as
   * the two above: always sent by a live sidecar, absent on results persisted
   * before this field existed. When it is absent the UI has no threshold and
   * must say so rather than fall back to a literal -- a hardcoded 30 would
   * keep reading as correct long after the backend default moved.
   */
  compare_params?: CompareParams;
  /**
   * Reads from wells the layout does not name. Same optionality reasoning as
   * `layout_provenance`.
   */
  off_layout_records?: OffLayoutRecords;
  /**
   * Whether the run could have produced a scorable plate, with the numbers and
   * the provenance of every threshold behind that. Optional only for results
   * persisted before the block existed; every current run carries it, including
   * a clean one (severity null).
   */
  run_quality?: RunQuality;
  /**
   * Stray-read signals read off the demux matrix. Optional for TWO reasons,
   * unlike the fields above: a result persisted before the key existed, AND a
   * consensus-dir run, which never demuxed and so has no matrix. Both read as
   * "not measured"; neither may be shown as zero.
   */
  contamination?: ContaminationReport;
  /**
   * How much of this result was reseeded from a previous run's demux output.
   * Optional for two independent reasons: the sidecar omits it outside per-NB
   * raw-run mode, and a result persisted before this field existed replays
   * without it.
   */
  demux_resume?: DemuxResume;
  /**
   * What was cut off the barcode seeds, and how much seed was left.
   *
   * Optional for one reason only, and it is not the usual persisted-snapshot
   * one: the sidecar SPREADS the key in
   * (`python-core/sidecar_mame/handlers/analyze.py:2395-2399`) and omits it
   * entirely when no barcode workbook was read, so it is absent rather than
   * null on every non-raw path. A run that did read one always carries it.
   */
  barcode_prefix_resolution?: BarcodePrefixResolution;
}

/**
 * Parameters for the `load_analyze_result` RPC (Phase 1 contract). Mirrors the
 * `analyze` response shape so the persisted result can be replayed verbatim to
 * re-inject the sidecar SidecarState on restart. `replicates[].plate_verdicts`
 * MUST be carried through for lossless plate-accent restoration.
 */
export interface LoadAnalyzeResultRequest {
  verdicts: VerdictRecord[];
  replicates: ReplicateResult[];
  output_path: string;
  run_meta?: Record<string, unknown> | null;
  /**
   * The recovery denominator, replayed so a restored run can report recovery
   * (재현율) instead of n/a. Unlike the three fields below this one IS stored
   * by the sidecar (`SidecarState.last_designed_mutant_ids`), so omitting it
   * silently disables recovery for the rest of the session.
   */
  designed_mutant_ids?: string[] | null;
  summary?: AnalyzeSummary | null;
  distribution_stats?: DistributionStats | null;
  /**
   * Accepted so a persisted response can be replayed verbatim. Like `summary`
   * and `distribution_stats` it is not stored by the sidecar: re-injecting
   * state does not re-run the classifier, so there is nothing for a threshold
   * to govern. The displayed values come from the persisted snapshot, not
   * from this call's response.
   */
  compare_params?: CompareParams | null;
}

/** Ack returned by `load_analyze_result`. Counts only; store data comes from
 *  the persisted file, not this response. */
export interface LoadAnalyzeResultResponse {
  restored: true;
  verdict_count: number;
  replicate_count: number;
}

export interface WellEntry {
  well: string;
  barcode: string;
  native_barcode: string;
  verdict: VerdictClass;
  mutant_id: string;
  selected: boolean;
  notes: string;
  is_fallback: boolean;
  fallback_reason: string | null;
}

export interface AnalysisParams {
  input_dir: string;
  reference: string;
  expected: string;
  output: string;
  mode: "amplicon" | "plasmid";
  ingest_mode: "barcode" | "amplicon";
  cds_start: number;
  cds_end: number;
  min_file_size_kb: number;
  min_read_count?: number | null;
  max_consensus_n_fraction?: number | null;
  many_cutoff: number;
  // Raw-run folded analyze: when input_dir is a MinKNOW run folder (contains
  // fastq_pass/), the backend demuxes internally before analyzing. These names
  // are byte-identical to the Pydantic raw-run fields. `reference` above is
  // reused as reference_fasta.
  custom_barcodes_xlsx?: string;
  native_barcodes?: string[] | null;
  coverage_fraction?: number;
  edit_dist_ratio?: number;
  chimera_split?: boolean;
  demux_output_dir?: string;
  mapq_threshold?: number;
  trim_flank_bp?: number;
}

export interface JsonRpcError {
  code: number;
  message: string;
}

export interface JsonRpcResponse<T = unknown> {
  jsonrpc: "2.0";
  id?: number;
  result?: T;
  error?: JsonRpcError;
}

export interface JsonRpcNotification<T = unknown> {
  jsonrpc: "2.0";
  method: string;
  params?: T;
}

export interface ProgressNotification {
  value: number;
  message: string;
}

/**
 * Does an expected workbook agree with its own primer plate sheet?
 *
 * Wire shape of `plate_order_payload` in
 * `python-core/sidecar_mame/handlers/barcode_package.py`, returned as-is by the
 * `check_plate_order` RPC. `examples` carries at most 5 disagreeing wells.
 */
export interface PlateOrderReport {
  comparable: boolean;
  mismatched: boolean;
  /** "Fwd List" | "Fwd Plate"; null when the check found no plate sheet. */
  plate_sheet: string | null;
  examples: { well: string; plate: string; expected: string }[];
  missing_from_expected: string[];
  absent_from_plate: string[];
}

/**
 * How much a plate disagreement costs on the run being set up.
 *
 * Only "blocking" is produced. A workbook whose primer plate sheet and
 * `expected_mutations` describe different plates does not record which of the
 * two was pipetted, so the run is refused until the workbook is replaced.
 *
 * "info" remains in the union for responses from a sidecar built before
 * 2026-08-05, which downgraded the finding when a well layout
 * supplied the coordinates. The frontend does not act on the value it receives
 * (see `selectPlateOrderSeverity`), so such a response still blocks.
 */
export type PlateOrderSeverity = "blocking" | "info";

/**
 * A `PlateOrderReport` carrying the severity the run applies to it.
 *
 * `validate_inputs` grades it server-side (`_plate_order_finding` in
 * `python-core/sidecar_mame/handlers/analyze.py`); the frontend grades the
 * ungraded `check_plate_order` response the same way.
 */
export interface PlateOrderFinding extends PlateOrderReport {
  severity: PlateOrderSeverity;
}

/**
 * What the barcode workbook contains, read back so the operator can confirm it.
 *
 * `forward_count` and `reverse_count` are the seeds each axis carries and
 * `wells` is how many wells they can name between them (the in-range
 * combinations). Display only: which axis is the plate row and which way the
 * plate fills are properties of how the barcodes were prepared, so there is no
 * control here and no value to choose.
 */
export interface BarcodeAxisCounts {
  forward_count: number;
  reverse_count: number;
  wells: number;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  /**
   * Present only when there is something to report: the workbook could be
   * compared and its sheets disagree. `valid` is false and `errors` carries the
   * same fact in words; this field is the structured form the notice renders
   * (which wells, which sheet, what is missing).
   */
  plate_order?: PlateOrderFinding;
  /**
   * Absent when no barcode workbook was supplied or it could not be read, so a
   * previously shown line has to be cleared rather than left standing.
   */
  barcode_axes?: BarcodeAxisCounts;
  /**
   * Present only when this project carries a `sample_map_template.xlsx` from
   * before the sample map was removed. `"differs"` means the file and the
   * layout this run would use name different plates, which is also an entry in
   * `errors`; `"matches"` is a one-time notice that the two agree and the file
   * can be deleted.
   */
  legacy_sample_map?: LegacySampleMapFinding;
}

/** A pre-removal sample map, compared against the layout that replaced it. */
export interface LegacySampleMapFinding {
  path: string;
  status: "matches" | "differs";
  /** Up to ten wells where the two disagree. */
  differences: { well: string; file: string; draft: string }[];
  wells_compared: number;
}

export interface ExportResult {
  output_path: string;
}

export type JanusExportFormat = "csv" | "xlsx";

/**
 * Destination-well assignment strategy for the Janus mapping export.
 *
 * - "compact" (default): dest_well is assigned sequentially from A1 in priority
 *   order, leaving no gaps on the destination plate. A cell stock plate is a
 *   new plate, so filling it from the front is the normal case.
 * - "source": dest_well mirrors the source plate position.
 *
 * Mirrors the ``dest_layout`` param of the ``export_janus_mapping`` RPC
 * (python-core/sidecar_mame/handlers/export.py).
 */
export type JanusDestLayout = "source" | "compact";

/**
 * Column set written to the file.
 *
 * - "device" (default): the instrument-native worksheet columns transcribed
 *   from the workbook the lab imports (`name | type | no | Asp. Rack |
 *   Asp. Posi | Dsp. Rack | Dsp. Posi | volume`).
 * - "legacy5": the kuma-internal columns (`name | source_plate | source_well |
 *   dest_well | priority_score`).
 *
 * The first was called "device9" while the sheet had nine columns, one of them
 * a liquid class. The lab replaced that sheet with an eight column one, so the
 * count came out of the name rather than being corrected to another number that
 * would age the same way. A stored "device9" is promoted on load
 * (`src/lib/mame/janusSettings.ts`) and the sidecar accepts it too.
 */
export type JanusOutputSchema = "device" | "legacy5";

/**
 * Plate NAMES written into `Asp. Rack`, keyed by the plate label the export
 * writes (`nb_label`: "sort_barcode07" -> "NB07"), so a key is looked up with
 * the same string the row carries.
 *
 * Names rather than deck numbers because the JANUS software matches labware by
 * name. Nothing in the panel fills this map: the sidecar generates the names
 * from the plates of the run, in the same plate order that used to decide rack
 * numbers, and the row preview is where the operator reads them back.
 */
export type JanusSourceRacks = Record<string, string>;

/**
 * Everything both the export and the preview resolve their behaviour from.
 *
 * Mirrors ``JanusSettings`` (kuma_core/mame/export/janus_mapping.py). The RPC
 * layer takes the same fields in snake_case; `src/lib/mame/janus.ts` does the
 * conversion in one place so the two calls cannot drift.
 */
export interface JanusExportSettings {
  destLayout: JanusDestLayout;
  /** Verdict classes to keep. Default: PASS only. */
  includeVerdicts: VerdictClass[];
  /** Keep fallback picks (off by default: a fallback pick is not verified). */
  includeFallback: boolean;
  outputSchema: JanusOutputSchema;
  /** Dispense volume in µL (instrument sheet only). */
  volume: number;
  /** `type` column value (instrument sheet only). */
  sampleType: string;
  /**
   * Liquid class, recorded with the run and written to no file. The instrument
   * sheet has no column for it, and the file format is followed exactly, so the
   * value describes how the run was pipetted without reaching the robot.
   */
  liquidClass: string;
  /**
   * Overrides only, and the panel offers no way to set one: the sidecar
   * generates the plate names from the plates of the run. An empty map is the
   * shipped default and leaves those generated names in force.
   */
  sourceRacks: JanusSourceRacks;
  /** `null` leaves the destination plate name to the sidecar. */
  destRack: string | null;
}

/** Resolved settings echoed back by the sidecar, in RPC (snake_case) form. */
export interface JanusResolvedSettings {
  dest_layout: JanusDestLayout;
  include_verdicts: VerdictClass[];
  include_fallback: boolean;
  output_schema: JanusOutputSchema;
  volume: number;
  sample_type: string;
  liquid_class: string;
  /** The operator's overrides, echoed back unchanged. */
  source_racks: JanusSourceRacks;
  /** The operator's override, echoed back unchanged; `null` means generated. */
  dest_rack: string | null;
  /** Header of the file this policy writes, in order. */
  columns: string[];
  /** The plate names the file carries: overrides applied on top of the generated ones. */
  resolved_source_racks?: JanusSourceRacks;
  resolved_dest_rack?: string;
}

/**
 * Why a clone was left out of the pick.
 *
 * - "failed": the picker marked the replicate failed.
 * - "no_selection": no plate was selected.
 * - "missing_verdict": the selected plate carries no verdict record.
 * - "verdict_class": the verdict is outside `includeVerdicts`.
 * - "fallback": the pick is a fallback and `includeFallback` is off.
 */
export type JanusExclusionReason =
  | "failed"
  | "no_selection"
  | "missing_verdict"
  | "verdict_class"
  | "fallback";

export interface JanusExcludedEntry {
  mutant_id: string;
  reason: JanusExclusionReason;
  /** Verdict of the selected plate; empty when no plate was selected. */
  verdict: VerdictClass | "";
  /** Plate label (`nb_label`, e.g. "NB07"); empty when no plate was selected. */
  selected_plate: string;
  is_fallback: boolean;
}

export interface JanusExportResult {
  output_path: string;
  format: JanusExportFormat;
  row_count: number;
  excluded: JanusExcludedEntry[];
  excluded_count: number;
  /** What the written file left blank or derived. */
  warnings: JanusPreviewError[];
  settings: JanusResolvedSettings;
}

/** One row of the Janus mapping, exactly as it is written to the export file. */
export interface JanusPreviewRow {
  name: string;
  source_plate: string;
  source_well: string;
  dest_well: string;
  priority_score: number;
}

/**
 * Validation problem codes returned by the dry-run preview.
 *
 * Mirrors the ``code`` field of ``build_janus_preview_rows``
 * (kuma_core/mame/export/janus_mapping.py).
 */
export type JanusPreviewErrorCode =
  | "unresolved_well"
  | "plate_capacity"
  | "duplicate_dest_well"
  | "missing_liquid_class"
  | "derived_source_rack"
  | "autosave_failed";

/**
 * "error" withholds the file; "warning" names a value that shipped blank or
 * derived, which is never a reason to produce no file.
 */
export type JanusFindingSeverity = "error" | "warning";

export interface JanusPreviewError {
  code: JanusPreviewErrorCode;
  severity: JanusFindingSeverity;
  message: string;
  mutant_ids: string[];
}

/**
 * Result of the ``export_janus_mapping_dry_run`` RPC.
 *
 * The export path fails fast on the same three problems; the preview collects
 * them so every problem is visible before a file is written.
 */
export interface JanusPreviewResult {
  rows: JanusPreviewRow[];
  /** Blocks the export. */
  errors: JanusPreviewError[];
  /** Never blocks: what shipped blank (liquid class) or derived (rack numbers). */
  warnings: JanusPreviewError[];
  row_count: number;
  /** Clones left out of the pick, with the reason for each. */
  excluded: JanusExcludedEntry[];
  excluded_count: number;
  /** The policy these rows were built with, echoed back for display. */
  settings: JanusResolvedSettings;
}

/**
 * Outcome of writing a Janus file: the pick list analyze writes automatically
 * at the end of a run (``_autosave_janus`` via ``_autosave_picks`` in
 * `python-core/sidecar_mame/handlers/analyze.py`, format always `"csv"`), or
 * the instrument mapping a manual export from `JanusMappingPanel` writes
 * (`setJanusMappingAutosave`, format follows the operator's format choice).
 * The automatic path never raises: a file that could not be written is a fact
 * to report, not a reason to lose the run.
 *
 * - "saved": the file exists at `output_path` and carries `row_count` rows.
 * - "skipped": nothing was selected, so no file was written (an empty pick
 *   list reads like a finished plate). Only the automatic path produces this;
 *   a manual export with nothing to write disables the Export button instead.
 * - "failed": `errors` says why.
 *
 * `warnings` never changes the status: a blank liquid class and rack numbers
 * derived from the run are reported, not enforced.
 */
export interface JanusAutosaveResult {
  status: "saved" | "skipped" | "failed";
  output_path: string | null;
  format: JanusExportFormat;
  row_count: number;
  excluded: JanusExcludedEntry[];
  excluded_count: number;
  errors: JanusPreviewError[];
  warnings: JanusPreviewError[];
}

export type RunReportFormat = "html" | "pdf";

export interface RunReportResult {
  output_path: string;
  format: RunReportFormat;
  weasyprint_available: boolean;
  fallback_to_html: boolean;
}

export interface PlateDataResult {
  wells: WellEntry[];
}

export interface ScreenTab {
  id: "input" | "verdict" | "plate" | "export";
  label: string;
  content?: ReactNode;
}

// ── A9: Cross-talk detection types ──────────────────────────────────────────

export interface CrossTalkCandidate {
  /** Well label, e.g. "A1", "B6". */
  well: string;
  /** Custom barcode label assigned to the well, e.g. "1_1", "1_2". */
  custom_barcode: string;
  /** Observed read count for this well. */
  read_count: number;
  /** Mean read count of orthogonal neighbors. */
  neighbor_avg: number;
  /** Z-score vs the entire plate-wide distribution. */
  z_score: number;
  severity: "low" | "medium" | "high";
  note: string;
}

// ── A8: Run health panel types ───────────────────────────────────────────────

export interface RunHealthBreakdown {
  pass: number;
  ambiguous: number;
  mixed: number;
  frameshift: number;
  many: number;
  lowdepth: number;
  no_call: number;
  wrong_aa: number;
  fail: number;
  fallback: number;
  total: number;
}

export interface RunHealthThroughputPoint {
  time_h: number;
  reads_per_sec: number;
}

export interface RunHealthData {
  per_plate_summary: Record<string, RunHealthBreakdown>;
  /** Keys: min, p05, p25, median, p75, p95, max, mean, std */
  file_size_distribution: Record<string, number>;
  suggested_cutoff_kb: number;
  bimodal: boolean;
  suggested_method: "median_minus_2sigma" | "p05" | "kneedle" | "fixed_50";
  pore_yield_pct: number | null;
  throughput_timeline: RunHealthThroughputPoint[] | null;
  barcode_distribution: Record<string, number> | null;
  cross_talk_candidates: CrossTalkCandidate[];
  /** Outcome of the cross-talk check itself. An empty candidate list means "no
   *  anomalies" only when this is "ok". Optional for payloads written before the
   *  field existed (treated as "ok"). */
  cross_talk_status?: "not_run" | "insufficient_data" | "ok";

  recovered_mutants: number | null;
  total_mutants: number | null;
  recovery_rate: number | null;
}

// ── A1/A3: Demux and quality-filter types (R6.5) ────────────────────────────

export interface DemuxFilterStats {
  n_input: number;
  n_passed: number;
  n_failed_qscore: number;
  n_failed_length: number;
  n_failed_barcode: number;
}

export interface AmpliconLengthDistributionSummary {
  min: number;
  median: number;
  max: number;
  peak_count: number;
  peak_ratio: number;
  /** Read length percentiles over the same sampled vector the modal peak came
   *  from (kuma_core/mame/ingest/quality_filter.py `_percentiles`). min/median/max
   *  cannot tell a tight amplicon from a smear around the same centre, and the
   *  smear is what a failed PCR looks like; p10/p90 bracket the bulk without
   *  being set by the single 200 kb read that decides `max`.
   *  Optional because a project saved before these existed carries none, and a
   *  missing percentile is not a read of length 0. */
  p10?: number;
  p25?: number;
  p75?: number;
  p90?: number;
}

export interface AmpliconLengthEstimate {
  detected_length: number;
  n_sample_reads: number;
  confidence: "high" | "medium" | "low";
  distribution_summary: AmpliconLengthDistributionSummary;
}

// ── A4/A5: Consensus calling statistics per well ────────────────────────────

export interface WellConsensusStats {
  /** Length of the consensus sequence (== reference length). */
  consensus_seq_length: number;
  /** Total reads for this well entering the alignment step. */
  n_input_reads: number;
  /** Reads that passed MAPQ filter and full-span filter. */
  n_aligned: number;
  /** Same as n_aligned (conservative — mappy does not expose pre-filter counts). */
  n_passed_filter: number;
  /** Mean per-position read depth across the reference. */
  mean_depth: number;
}

export interface DemuxAndFilterResult {
  output_dir: string;
  n_input_reads: number;
  n_assigned: number;
  n_unassigned: number;
  per_well_counts: Record<string, number>;
  filter_stats: DemuxFilterStats | null;
  backend: "cutadapt" | "python";
  amplicon_length_estimate: AmpliconLengthEstimate | null;
  length_filter_mode: "target_window" | "fixed_range" | "none";
  /** Number of native barcode subdirs auto-detected from fastq_dir.
   *  Null when nb_dirs was explicitly provided or single-NB fallback occurred. */
  auto_detected_nb_count?: number | null;
  /** Basenames (e.g. "barcode01") of auto-detected NB subdirs. Null in the
   *  same cases as auto_detected_nb_count. */
  auto_detected_nb_names?: string[] | null;
  /** Per-well consensus calling statistics.
   *  Null when reference_fasta was not provided (legacy demux-only mode). */
  consensus_stats?: Record<string, WellConsensusStats> | null;
  /** True when A4/A5 alignment+consensus pipeline was executed. */
  consensus_pipeline?: boolean;
}

export interface DemuxAndFilterParams {
  fastq_dir: string;
  custom_barcodes?: Record<string, string>;
  custom_barcodes_path?: string;
  output_dir: string;
  /** Path to reference FASTA for alignment + consensus calling (A4/A5).
   *  When provided, output per-well FASTA files are single-record consensus
   *  sequences compatible with analyze(). */
  reference_fasta?: string;
  error_tolerance?: number;
  use_cutadapt?: boolean;
  sequencing_summary?: string;
  min_qscore?: number;
  length_min?: number;
  length_max?: number;
  target_length?: number | null;
  length_tolerance_bp?: number;
  auto_detect_length?: boolean;
  min_barcode_score?: number;
  linked_trim?: boolean;
  rev_primer_universal?: string | null;
  normalize_headers?: boolean;
  nb_dirs?: string[];
  /** Keep intermediate raw-read FASTA files after consensus calling. Default false. */
  save_intermediate_reads?: boolean;
  /** MAPQ threshold for alignment filter. Default 25. */
  min_mapq?: number;
  /** Minimum per-position depth for consensus base call. Default 1. */
  min_consensus_depth?: number;
}
