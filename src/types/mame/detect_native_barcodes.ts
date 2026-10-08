/**
 * TypeScript mirror of the ``mame.detect_native_barcodes`` RPC handler.
 *
 * Keep in sync with:
 *   - kuma_core/mame/ingest/demux.py  (NativeBarcodeUsage, detect_used_native_barcodes)
 *   - python-core/sidecar_mame/handlers/detect_native_barcodes.py (response dict)
 *   - python-core/sidecar_mame/models.py (DetectNativeBarcodesParams)
 */

/** Per-native-barcode read-volume usage entry. */
export interface NativeBarcodeUsage {
  /** MinKNOW barcode dir name (e.g. "barcode06"). */
  name: string
  /** Output subdir name derived from name (e.g. "sort_barcode06"). */
  sort_barcode_name: string
  /** Total on-disk size of all FASTQ(.gz) under the barcode dir, in bytes. */
  fastq_bytes: number
  /** fastq_bytes expressed in megabytes. */
  fastq_mb: number
  /** Fraction of total fastq_bytes across all native-barcode dirs. */
  share: number
  /** True when share meets min_share (this barcode was actually used). */
  is_used: boolean
}

/** Parameters for the mame.detect_native_barcodes RPC method. */
export interface DetectNativeBarcodesParams {
  /** Root of a MinKNOW run directory (must contain fastq_pass/). */
  minknow_run_dir: string
  /** Minimum share for a barcode to count as used. Default 0.05. */
  min_share?: number
}

/** Result of a mame.detect_native_barcodes RPC call. */
export interface DetectNativeBarcodesResult {
  /** Resolved path to the fastq_pass/ directory that was scanned. */
  fastq_pass: string
  /** Effective min_share threshold applied. */
  min_share: number
  /** Per-native-barcode usage entries, sorted by fastq_bytes descending. */
  native_barcodes: NativeBarcodeUsage[]
  /** Number of barcodes flagged is_used. */
  used_count: number
  /** Total number of native-barcode dirs detected. */
  total_count: number
}
