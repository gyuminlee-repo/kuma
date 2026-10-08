/**
 * Project-scoped persisted state for the Step 1 Barcode Setup form.
 *
 * The form used to live under one global key that `resetMameAll` removed on
 * every project open, so reopening a project always showed an empty form, and
 * between opens one project's FASTA and seeds showed up in any other project.
 * Keyed by project path the way the Step 3 EVOLVEpro builder is
 * (`buildEvolveproFormStorage.ts`): opening a project reads its own row, and
 * only Clear All removes it.
 */

export const BARCODE_SETUP_LEGACY_STORAGE_KEY = "kuma:mame:barcodeSetup";
const STORAGE_VERSION = 1;

export interface BarcodeSetupFormState {
  fastaPath: string;
  topology: "linear" | "circular";
  geneStart: string;
  geneEnd: string;
  geneName: string;
  polymerase: "Q5" | "Taq" | "Phusion" | "KOD";
  overhangMin: string;
  overhangMax: string;
  bindingMinLen: string;
  bindingMaxLen: string;
  tmMin: string;
  tmMax: string;
  requireGcClamp: boolean;
  barcodeSeedsPath: string;
  outputDir: string;
}

export const BARCODE_SETUP_DEFAULT_STATE: BarcodeSetupFormState = {
  fastaPath: "",
  topology: "linear",
  geneStart: "",
  geneEnd: "",
  geneName: "",
  polymerase: "Q5",
  overhangMin: "20",
  overhangMax: "60",
  bindingMinLen: "18",
  bindingMaxLen: "35",
  tmMin: "55.0",
  tmMax: "68.0",
  requireGcClamp: true,
  barcodeSeedsPath: "",
  outputDir: "",
};

const PATH_KEYS = ["fastaPath", "barcodeSeedsPath", "outputDir"] as const;

export function barcodeSetupStorageKey(projectPath: string): string {
  return `${BARCODE_SETUP_LEGACY_STORAGE_KEY}:v${STORAGE_VERSION}:${encodeURIComponent(projectPath)}`;
}

function stringOr(p: Record<string, unknown>, key: string, fallback: string): string {
  return typeof p[key] === "string" ? (p[key] as string) : fallback;
}

/** Validates a stored record field by field; anything unusable takes its default. */
function readState(p: Record<string, unknown>): BarcodeSetupFormState {
  const d = BARCODE_SETUP_DEFAULT_STATE;
  const polymerase =
    p.polymerase === "Q5" || p.polymerase === "Taq" || p.polymerase === "Phusion" || p.polymerase === "KOD"
      ? p.polymerase
      : d.polymerase;
  const topology = p.topology === "linear" || p.topology === "circular" ? p.topology : d.topology;
  return {
    fastaPath: stringOr(p, "fastaPath", d.fastaPath),
    topology,
    geneStart: stringOr(p, "geneStart", d.geneStart),
    geneEnd: stringOr(p, "geneEnd", d.geneEnd),
    geneName: stringOr(p, "geneName", d.geneName),
    polymerase,
    // Legacy keys: the parameters used to be flankMin/flankMax, where
    // flankMin was the GAP between primer and gene and flankMax was the
    // overhang past the gene boundary. overhangMax measures the same
    // quantity flankMax did, so a stored flankMax carries over. flankMin has
    // no counterpart on the overhang axis (the gap is now a fixed >= 0
    // invariant), so a stored flankMin is dropped for the new default.
    overhangMin: stringOr(p, "overhangMin", d.overhangMin),
    overhangMax:
      typeof p.overhangMax === "string"
        ? p.overhangMax
        : stringOr(p, "flankMax", d.overhangMax),
    bindingMinLen: stringOr(p, "bindingMinLen", d.bindingMinLen),
    bindingMaxLen: stringOr(p, "bindingMaxLen", d.bindingMaxLen),
    tmMin: stringOr(p, "tmMin", d.tmMin),
    tmMax: stringOr(p, "tmMax", d.tmMax),
    requireGcClamp: typeof p.requireGcClamp === "boolean" ? p.requireGcClamp : d.requireGcClamp,
    barcodeSeedsPath: stringOr(p, "barcodeSeedsPath", d.barcodeSeedsPath),
    outputDir: stringOr(p, "outputDir", d.outputDir),
  };
}

function pathBelongsToProject(path: string, projectPath: string): boolean {
  const normalizedPath = path.replace(/\\/g, "/").replace(/\/+$/, "");
  const normalizedProject = projectPath.replace(/\\/g, "/").replace(/\/+$/, "");
  if (/^(?:[a-z]:\/|\/\/)/i.test(normalizedProject)) {
    return normalizedPath.toLowerCase().startsWith(`${normalizedProject.toLowerCase()}/`);
  }
  return normalizedPath.startsWith(`${normalizedProject}/`);
}

/**
 * Whether the old global record can be adopted by this project.
 *
 * Same rule as the EVOLVEpro builder: adopted only when every path it names
 * lies inside the project. A record that names no path at all (parameters
 * only) carries nothing that could belong to another project, so it is
 * adopted too. A record pointing elsewhere is left for the project it belongs
 * to rather than shown here.
 */
function legacyBelongsToProject(p: Record<string, unknown>, projectPath: string): boolean {
  return PATH_KEYS.map((key) => stringOr(p, key, ""))
    .filter(Boolean)
    .every((path) => pathBelongsToProject(path, projectPath));
}

function parseRecord(raw: string | null): Record<string, unknown> | null {
  if (!raw) return null;
  const parsed: unknown = JSON.parse(raw);
  return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : null;
}

/** Loads this project's form. No project means defaults and nothing persisted. */
export function loadBarcodeSetupForm(projectPath?: string | null): BarcodeSetupFormState {
  if (!projectPath) return BARCODE_SETUP_DEFAULT_STATE;
  try {
    const scoped = parseRecord(localStorage.getItem(barcodeSetupStorageKey(projectPath)));
    if (scoped) return readState(scoped);
    const legacy = parseRecord(localStorage.getItem(BARCODE_SETUP_LEGACY_STORAGE_KEY));
    if (!legacy || !legacyBelongsToProject(legacy, projectPath)) {
      return BARCODE_SETUP_DEFAULT_STATE;
    }
    const imported = readState(legacy);
    saveBarcodeSetupForm(imported, projectPath);
    if (localStorage.getItem(barcodeSetupStorageKey(projectPath))) {
      localStorage.removeItem(BARCODE_SETUP_LEGACY_STORAGE_KEY);
    }
    return imported;
  } catch {
    return BARCODE_SETUP_DEFAULT_STATE;
  }
}

export function saveBarcodeSetupForm(state: BarcodeSetupFormState, projectPath?: string | null): void {
  if (!projectPath) return;
  try {
    localStorage.setItem(barcodeSetupStorageKey(projectPath), JSON.stringify(state));
  } catch {
    // 저장 실패 시 무시: 현재 폼은 그대로 쓸 수 있다.
  }
}

/** Clear All: forget this project's form, and the old global record with it. */
export function clearBarcodeSetupForm(projectPath?: string | null): void {
  try {
    if (projectPath) localStorage.removeItem(barcodeSetupStorageKey(projectPath));
    localStorage.removeItem(BARCODE_SETUP_LEGACY_STORAGE_KEY);
  } catch {
    // localStorage may be unavailable (SSR, sandbox); ignore.
  }
}
