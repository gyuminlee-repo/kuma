import { useAppStore } from "../store/appStore";

const UNINFORMATIVE = new Set(["", "orf1", "unknown", "none", "cds", "gene"]);

function sanitize(token: string): string {
  return token.replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
}

function datePrefix(): string {
  const d = new Date();
  const yy = String(d.getFullYear()).slice(2);
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yy}${mm}${dd}`;
}

function extractFromHeader(header: string): string {
  if (!header) return "";
  const first = header.trim().replace(/^>/, "").split(/\s+/)[0] ?? "";
  const sp = first.match(/^(?:sp|tr)\|([A-Z0-9]+)\|/i);
  if (sp?.[1]) return sp[1];
  return first;
}

function stemFromPath(path: string): string {
  if (!path) return "";
  const base = path.split(/[\\/]/).pop() ?? "";
  return base.replace(/\.[^.]+$/, "");
}

function geneToken(): string {
  const s = useAppStore.getState();
  const selected = s.seqInfo?.genes.find((g) => String(g.cds_start) === s.selectedGene);
  const geneName = selected?.gene ?? "";
  if (geneName && !UNINFORMATIVE.has(geneName.toLowerCase())) return sanitize(geneName);

  const acc = s.uniprotAccession;
  if (acc) return sanitize(acc);

  const headerTok = extractFromHeader(s.seqInfo?.header ?? "");
  if (headerTok && !UNINFORMATIVE.has(headerTok.toLowerCase())) return sanitize(headerTok);

  const stem = stemFromPath(s.fastaPath);
  if (stem) return sanitize(stem);

  return "seq";
}

function mutToken(): string {
  const n = useAppStore.getState().designResults.length;
  return n > 0 ? `${n}mut` : "";
}

export interface FilenameOpts {
  target: string;
  ext: string;
  plate?: { index: number; total: number };
}

export function defaultExportFilename(opts: FilenameOpts): string {
  const tokens = [datePrefix(), geneToken(), opts.target];
  const m = mutToken();
  if (m) tokens.push(m);
  if (opts.plate && opts.plate.total > 1) {
    tokens.push(`p${opts.plate.index}of${opts.plate.total}`);
  }
  return `${tokens.join("_")}.${opts.ext}`;
}
