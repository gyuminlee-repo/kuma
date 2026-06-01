import { invoke } from "@tauri-apps/api/core";

/**
 * Input validation for the EVOLVEpro run form.
 *
 * A (Round CSV/XLSX): column header check + Variant pattern check for first 20 rows.
 *   For .xlsx/.xls the binary cannot be parsed in TS without a heavy dep, so the
 *   check is skipped (returns ok) and validation defers to the Python pipeline.
 * B (WT FASTA): header (>) present, sequence uses canonical AA alphabet.
 * D (Top N): integer in [0, 1000], NaN rejected.
 * C (Output dir): write probe via Rust command, executed on submit.
 *
 * File reads use the `read_text_head` Tauri command (Rust-side) instead of the
 * fs plugin to avoid granting a filesystem-wide capability scope.
 */

export interface ValidationResult {
  ok: boolean;
  message?: string;
}

const AA_ALPHABET = /^[ACDEFGHIKLMNPQRSTVWY*]+$/i;
// WT, S29I (letter+digits+letter), 29I (digits+letter), allow * for stop codons
const VARIANT_PATTERN = /^(WT|[A-Z*]?\d+[A-Z*])$/;

const HEAD_BYTES = 64 * 1024;

async function readHead(path: string): Promise<string> {
  return await invoke<string>("read_text_head", { path, maxBytes: HEAD_BYTES });
}

function parseCsvHeader(line: string): string[] {
  // minimal CSV header split, no quoted-field support (sufficient for column-name probe)
  return line.split(/[,\t;]/).map((c) => c.trim().replace(/^"|"$/g, ""));
}

export async function validateRoundCsv(path: string): Promise<ValidationResult> {
  if (!path) return { ok: false, message: "No file selected." };
  const lower = path.toLowerCase();
  if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) {
    // binary format, defer to backend
    return { ok: true };
  }
  let text: string;
  try {
    text = await readHead(path);
  } catch (e) {
    return { ok: false, message: `Cannot read file: ${String(e)}` };
  }
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length === 0) return { ok: false, message: "Empty file." };

  const header = parseCsvHeader(lines[0]).map((h) => h.toLowerCase());
  const hasVariant = header.includes("variant");
  const hasActivity = header.includes("activity");
  if (!hasVariant || !hasActivity) {
    return {
      ok: false,
      message: `Missing required columns. Need 'Variant' and 'activity', found: ${header.join(", ")}`,
    };
  }
  const variantIdx = header.indexOf("variant");

  const probe = lines.slice(1, 21);
  for (let i = 0; i < probe.length; i++) {
    const cols = parseCsvHeader(probe[i]);
    const v = cols[variantIdx];
    if (!v) continue;
    if (!VARIANT_PATTERN.test(v)) {
      return {
        ok: false,
        message: `Row ${i + 2}: Variant '${v}' does not match WT / S29I / 29I pattern.`,
      };
    }
  }
  return { ok: true };
}

export async function validateFasta(path: string): Promise<ValidationResult> {
  if (!path) return { ok: false, message: "No file selected." };
  let text: string;
  try {
    text = await readHead(path);
  } catch (e) {
    return { ok: false, message: `Cannot read file: ${String(e)}` };
  }
  const lines = text.split(/\r?\n/);
  const headers = lines.filter((l) => l.startsWith(">"));
  if (headers.length === 0) {
    return { ok: false, message: "No FASTA header (>) found." };
  }
  const seqChars = lines
    .filter((l) => !l.startsWith(">") && l.length > 0)
    .join("")
    .replace(/\s/g, "");
  if (seqChars.length === 0) {
    return { ok: false, message: "FASTA contains no sequence data." };
  }
  if (!AA_ALPHABET.test(seqChars)) {
    const bad = seqChars
      .toUpperCase()
      .split("")
      .find((c) => !/[ACDEFGHIKLMNPQRSTVWY*]/.test(c));
    return { ok: false, message: `Invalid amino acid character: '${bad}'.` };
  }
  return { ok: true };
}

export function validateTopN(value: number | string): ValidationResult {
  const raw = typeof value === "string" ? value.trim() : value;
  if (raw === "" || raw === null || raw === undefined) {
    return { ok: false, message: "Top N must be a number." };
  }
  const n = typeof raw === "string" ? Number(raw) : raw;
  if (Number.isNaN(n)) return { ok: false, message: "Top N must be a number." };
  if (!Number.isInteger(n)) return { ok: false, message: "Top N must be an integer." };
  if (n < 0 || n > 1000) return { ok: false, message: "Top N must be between 0 and 1000." };
  return { ok: true };
}

export async function validateOutputDir(path: string): Promise<ValidationResult> {
  if (!path) return { ok: false, message: "No output directory selected." };
  try {
    await invoke<void>("probe_writable_dir", { path });
    return { ok: true };
  } catch (e) {
    return { ok: false, message: `Output directory is not writable: ${String(e)}` };
  }
}
