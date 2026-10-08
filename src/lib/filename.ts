import { useAppStore } from "../store/appStore";
import type { KumaProject } from "../state/projectContext";
import {
  UNINFORMATIVE,
  sanitize,
  datePrefix,
  defaultMameExportFilename,
} from "./mameFilename";

export { sanitize, defaultMameExportFilename };

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
