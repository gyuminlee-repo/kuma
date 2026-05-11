import { useAppStore } from "../store/appStore";
import type { KumaProject } from "../state/projectContext";

const UNINFORMATIVE = new Set(["", "orf1", "unknown", "none", "cds", "gene"]);

export function sanitize(token: string): string {
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

function fullDateStamp(): string {
  const d = new Date();
  const yyyy = String(d.getFullYear());
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}${mm}${dd}`;
}

/**
 * Save Workspace 다이얼로그의 defaultPath를 조립한다.
 * - 활성 프로젝트(non-scratch)가 있으면: `<project.path>/<name>_<YYYYMMDD>.<kind>.workspace.json`
 * - scratch 또는 null이면: `<name>_<YYYYMMDD>.<kind>.workspace.json` (파일명만)
 */
export function buildWorkspaceDefaultPath(
  project: KumaProject,
  kind: "kuro" | "mame",
): string {
  const yyyymmdd = fullDateStamp();
  const name = project?.name ? sanitize(project.name) : "scratch";
  const filename = `${name}_${yyyymmdd}.${kind}.workspace.json`;
  if (project && !project.scratch && project.path) {
    return `${project.path}/${filename}`;
  }
  return filename;
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
