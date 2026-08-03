/**
 * TypeScript mirror of sidecar_mame generate_mame_package RPC interface.
 *
 * Keep in sync with:
 *   - python-core/sidecar_mame/handlers/barcode_package.py (handle_generate_mame_package)
 *   - kuma_core/mame/ingest/barcode_package.py (generate_mame_package return type)
 */

/** Parameters for the generate_mame_package RPC method. */
export interface GenerateMamePackageParams {
  /** Path to sequence file (.fa / .fasta / .fna / .gb / .gbk / .gbff / .dna). */
  fasta_path: string
  /** 0-based inclusive gene start within CDS. */
  gene_start: number
  /** 0-based exclusive gene end within CDS. */
  gene_end: number
  /** Path to barcode seeds xlsx (fwd_1..12, rev_1..8). */
  barcode_seeds_path: string
  /** Destination directory for outputs (created if absent). */
  output_dir: string
  /** Project root for mame_context.json. */
  project_root: string
  /** Input-derived or explicitly entered gene name used in output filenames. */
  gene_name: string
  /** Polymerase preset for Tm calculation. Default: "Q5". */
  polymerase?: string
  /** Minimum flank length (nt). Default: 100. */
  flank_min?: number
  /** Maximum flank length (nt). Default: 400. */
  flank_max?: number
  /** Minimum binding region length (nt). Default: 18. */
  binding_min_len?: number
  /** Maximum binding region length (nt). Default: 35. */
  binding_max_len?: number
  /** Minimum melting temperature (degC). Default: 55.0. */
  tm_min?: number
  /** Maximum melting temperature (degC). Default: 68.0. */
  tm_max?: number
  /** Require GC clamp on 3-prime end. Default: true. */
  require_gc_clamp?: boolean
  /**
   * Optional variant list. When set, sample_map_template.xlsx is pre-filled with
   * a draft placement (one variant per well in column-major order, WT control
   * last) instead of headers only. The draft still needs verification against
   * the physical plate.
   *
   * A KURO results xlsx carrying an expected_mutations sheet is detected and
   * read with its own strict reader. Any other workbook or csv is read as a
   * plain list, one variant per row, in file order.
   */
  expected_mutations_path?: string
  /**
   * Sheet holding the variant list. Only needed for a non-KURO file whose sheet
   * cannot be inferred; ignored for KURO exports.
   */
  variant_sheet?: string
  /**
   * Column holding the variant labels. Only needed when the header is not a
   * recognised name (variant, mutation, mutant_id, ...) and the sheet has more
   * than one column.
   */
  variant_column?: string
}

/** Parameters for the inspect_variant_source RPC method. */
export interface InspectVariantSourceParams {
  /** Variant list to inspect (xlsx or csv). */
  path: string
}

/**
 * What a variant list offers, so the UI can present sheet and column pickers
 * instead of rejecting an unfamiliar layout.
 */
export interface VariantSourceInfo {
  /** True when this is a KURO export and needs no column mapping. */
  is_kuro_export: boolean
  /** Sheet names in workbook order. Empty for csv. */
  sheets: string[]
  /** Headers per sheet. csv uses the single key "". */
  headers: Record<string, string[]>
  /** Column the backend would pick on its own, when it can pick one. */
  suggested_column: string | null
}

/** Result of the generate_mame_package RPC method. */
export interface MamePackageResult {
  /** Absolute path to generated barcodes xlsx. */
  barcodes_xlsx: string
  /** Absolute path to generated amplicon FASTA. */
  amplicon_fa: string
  /** Absolute path to generated sample map template xlsx. */
  sample_map_template: string
  /** Absolute path to generated mame context JSON. */
  context_json: string
  /** Non-critical warnings from primer design. */
  warnings: string[]
  /** Computed PCR amplicon length (bp) from primer binding positions, or null if unresolved. */
  amplicon_length: number | null
  /** Pre-filled data rows in sample_map_template (0 = header only, or preserved). */
  sample_map_prefilled_rows: number
  /**
   * True when an existing sample_map_template.xlsx already held well
   * assignments and was left untouched rather than regenerated.
   */
  sample_map_preserved: boolean
}
