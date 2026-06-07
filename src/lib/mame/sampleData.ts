import type {
  AnalyzeSummary,
  ReplicateResult,
  VerdictRecord,
  WellEntry,
} from "@/types/mame/models";

export function sampleVerdicts(): VerdictRecord[] {
  const base: Omit<
    VerdictRecord,
    | "source_path"
    | "file_size_kb"
    | "read_count"
    | "n_mixed_positions"
    | "max_minor_allele_fraction"
    | "n_low_depth_positions"
    | "consensus_n_fraction"
    | "n_low_quality_bases"
    | "n_input_reads"
    | "n_aligned_reads"
    | "n_mapq_failed"
    | "n_span_failed"
    | "observed_nt_changes"
  >[] = [
    { native_barcode: "barcode1", custom_barcode: "1_1", verdict: "PASS", verdict_notes: "", aa_sequence: "MSTTS", observed_aa_changes: ["V5F"], expected_mutations: ["V5F"] },
    { native_barcode: "barcode2", custom_barcode: "1_2", verdict: "PASS", verdict_notes: "", aa_sequence: "MSTTS", observed_aa_changes: ["K53N"], expected_mutations: ["K53N"] },
    { native_barcode: "barcode3", custom_barcode: "1_3", verdict: "WRONG_AA", verdict_notes: "observed V5S, expected V5F", aa_sequence: "MSTSS", observed_aa_changes: ["V5S"], expected_mutations: ["V5F"] },
    { native_barcode: "barcode4", custom_barcode: "1_4", verdict: "AMBIGUOUS", verdict_notes: "mixed trace", aa_sequence: "MSTTS", observed_aa_changes: [], expected_mutations: ["T10A"] },
    { native_barcode: "barcode5", custom_barcode: "2_1", verdict: "FRAMESHIFT", verdict_notes: "insertion at pos 15", aa_sequence: "MSTT", observed_aa_changes: [], expected_mutations: ["L12I"] },
    { native_barcode: "barcode6", custom_barcode: "2_2", verdict: "PASS", verdict_notes: "", aa_sequence: "MSTTS", observed_aa_changes: ["Q80R"], expected_mutations: ["Q80R"] },
    { native_barcode: "barcode7", custom_barcode: "2_3", verdict: "MANY", verdict_notes: "6 unexpected changes", aa_sequence: "MSTTS", observed_aa_changes: ["A1G", "B2C", "D3E"], expected_mutations: ["V5F"] },
    { native_barcode: "barcode8", custom_barcode: "3_1", verdict: "LOWDEPTH", verdict_notes: "coverage 12x", aa_sequence: "", observed_aa_changes: [], expected_mutations: ["R100K"] },
  ];
  return base.map((v, i) => ({
    ...v,
    source_path: `/mock/NB0${Math.floor(i / 3) + 1}/${v.custom_barcode}.fasta`,
    file_size_kb: 120 + i * 4,
    read_count: null,
    n_mixed_positions: v.verdict === "AMBIGUOUS" ? 1 : 0,
    max_minor_allele_fraction: v.verdict === "AMBIGUOUS" ? 0.49 : 0,
    n_low_depth_positions: v.verdict === "LOWDEPTH" ? 12 : 0,
    consensus_n_fraction: v.verdict === "LOWDEPTH" ? 0.08 : 0,
    n_low_quality_bases: v.verdict === "LOWDEPTH" ? 24 : 0,
    n_input_reads: 160 + i * 8,
    n_aligned_reads: 155 + i * 7,
    n_mapq_failed: i % 3,
    n_span_failed: i % 2,
    observed_nt_changes: [],
  }));
}

export function sampleReplicates(): ReplicateResult[] {
  return [
    { mutant_id: "V5F", selected_plate: "barcode1", selection_reason: "only_pass", failed: false, plate_keys: ["barcode1"], is_fallback: false, fallback_reason: null },
    { mutant_id: "K53N", selected_plate: "barcode2", selection_reason: "best_pass", failed: false, plate_keys: ["barcode2"], is_fallback: false, fallback_reason: null },
    { mutant_id: "Q80R", selected_plate: "barcode6", selection_reason: "only_pass", failed: false, plate_keys: ["barcode6"], is_fallback: false, fallback_reason: null },
    { mutant_id: "T10A", selected_plate: null, selection_reason: "all_failed", failed: true, plate_keys: ["barcode4"], is_fallback: false, fallback_reason: null },
    { mutant_id: "L12I", selected_plate: null, selection_reason: "all_failed", failed: true, plate_keys: ["barcode5"], is_fallback: false, fallback_reason: null },
    { mutant_id: "R100K", selected_plate: null, selection_reason: "all_lowdepth", failed: true, plate_keys: ["barcode8"], is_fallback: false, fallback_reason: null },
  ];
}

export function sampleSummary(): AnalyzeSummary {
  return { total: 8, pass_count: 3, ambiguous_count: 1, fail_count: 3 };
}

export function sampleWells(): WellEntry[] {
  const rows = ["A", "B", "C", "D", "E", "F", "G", "H"];
  const verdicts = ["PASS", "PASS", "WRONG_AA", "AMBIGUOUS", "FRAMESHIFT", "PASS", "MANY", "LOWDEPTH"] as const;
  const out: WellEntry[] = [];
  for (let rowIdx = 0; rowIdx < rows.length; rowIdx++) {
    for (let col = 1; col <= 12; col++) {
      const v = verdicts[(rowIdx + col) % verdicts.length];
      out.push({
        well: `${rows[rowIdx]}${col}`,
        barcode: `${col}_${rowIdx + 1}`,
        native_barcode: `barcode${(rowIdx * 12 + col) % 24}`,
        verdict: v,
        mutant_id: v === "PASS" ? ["V5F", "K53N", "Q80R"][col % 3] : "—",
        selected: rowIdx === 0 && col <= 3,
        notes: v === "WRONG_AA" ? "observed V5S" : "",
        is_fallback: false,
        fallback_reason: null,
      });
    }
  }
  return out;
}
