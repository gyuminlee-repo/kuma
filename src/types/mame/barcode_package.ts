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
  /** Gene name used in output filenames. Default: "egfp". */
  gene_name?: string
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
}
