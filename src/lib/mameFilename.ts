// Store-free filename helpers. Kept import-free so modules in the store graph
// (e.g. mame/inputSlice) can use defaultMameExportFilename without dragging in
// the app store, which would create a module-eval import cycle.
export const UNINFORMATIVE = new Set(["", "orf1", "unknown", "none", "cds", "gene"]);

export function sanitize(token: string): string {
  return token.replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
}

export function datePrefix(): string {
  const d = new Date();
  const yy = String(d.getFullYear()).slice(2);
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yy}${mm}${dd}`;
}

function stemFromFilename(path: string): string {
  const base = path.split(/[\\/]/).pop() ?? "";
  return base.replace(/\.[^.]+$/, "");
}

function informativePathToken(path: string): string {
  const stem = stemFromFilename(path);
  if (!stem || UNINFORMATIVE.has(stem.toLowerCase())) return "";
  return sanitize(stem);
}

export function defaultMameExportFilename(opts: {
  referencePath?: string;
  inputDir?: string;
  verdictCount?: number;
}): string {
  const sourceToken =
    informativePathToken(opts.referencePath ?? "") ||
    informativePathToken(opts.inputDir ?? "") ||
    "seq";
  const tokens = [datePrefix(), sourceToken, "MAME"];
  if ((opts.verdictCount ?? 0) > 0) tokens.push(`${opts.verdictCount}verdicts`);
  return `${tokens.join("_")}.xlsx`;
}
