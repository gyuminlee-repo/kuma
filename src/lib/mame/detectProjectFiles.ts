/**
 * detectProjectFiles.ts — MAME 프로젝트 디렉토리에서 입력 파일 자동 감지
 *
 * 프로젝트 경로와 그 부모 디렉토리를 스캔하여 MAME 입력으로 쓸 수 있는
 * 후보 파일/폴더 경로를 반환한다. 각 필드는 매칭되지 않으면 undefined.
 *
 * 우선순위:
 *  1. autosave 복원값 (비어있지 않으면 탐지 스킵)
 *  2. 자동 탐지
 *  3. 수동 입력
 */

import { readDir } from "@tauri-apps/plugin-fs";

export interface DetectedPaths {
  /** MinKNOW run 디렉토리 (YYYYMMDD_HHMM_* 패턴) */
  inputDir?: string;
  /** custom barcodes xlsx/csv */
  customBarcodesPath?: string;
  /** mutants/well-map xlsx → sample_map_path */
  sampleMapPath?: string;
  /** reference FASTA (.fa / .fasta) */
  referencePath?: string;
  /** expected genotype xlsx */
  expectedPath?: string;
}

const MINKNOW_DIR_RE = /^\d{8}_\d{4}_/;
const BARCODES_RE = /^(custom_)?barcode[s]?.*\.(xlsx|csv)$/i;
const SAMPLE_MAP_RE = /^(mutant[s]?|sample_map|well_map|plate_map).*\.xlsx$/i;
const REFERENCE_RE = /\.(fa|fasta)$/i;
const EXPECTED_RE = /^(expected|genotype|template).*\.(xlsx|csv)$/i;

type DirEntry = { name?: string; isDirectory: boolean; isFile: boolean };

function joinPath(dir: string, name: string): string {
  const sep = dir.includes("\\") ? "\\" : "/";
  return `${dir.trimEnd().replace(/[/\\]$/, "")}${sep}${name}`;
}

/** dir を shallow スキャンして DirEntry 配列を返す。失敗時は [] */
async function safeReadDir(dir: string): Promise<DirEntry[]> {
  try {
    return (await readDir(dir)) as DirEntry[];
  } catch {
    return [];
  }
}

/**
 * プロジェクトパスとその親ディレクトリをスキャンして後보 경로を返す.
 * 빈 문자열인 현재 autosave 필드만 채운다 (비어있지 않은 값은 건드리지 않음).
 */
export async function detectProjectFiles(projectPath: string): Promise<DetectedPaths> {
  const sep = projectPath.includes("\\") ? "\\" : "/";
  const parentPath = projectPath.includes(sep)
    ? projectPath.slice(0, projectPath.lastIndexOf(sep))
    : projectPath;

  const detected: DetectedPaths = {};

  // 프로젝트 디렉토리 스캔 (barcodes, sample map, reference, expected)
  const projectEntries = await safeReadDir(projectPath);
  for (const entry of projectEntries) {
    if (!entry.name) continue;
    const fullPath = joinPath(projectPath, entry.name);
    if (entry.isFile) {
      if (!detected.customBarcodesPath && BARCODES_RE.test(entry.name)) {
        detected.customBarcodesPath = fullPath;
      }
      if (!detected.sampleMapPath && SAMPLE_MAP_RE.test(entry.name)) {
        detected.sampleMapPath = fullPath;
      }
      if (!detected.referencePath && REFERENCE_RE.test(entry.name)) {
        detected.referencePath = fullPath;
      }
      if (!detected.expectedPath && EXPECTED_RE.test(entry.name)) {
        detected.expectedPath = fullPath;
      }
    }
  }

  // 부모 디렉토리 스캔 (MinKNOW run dirs + 프로젝트 디렉토리에 없는 파일 보완)
  if (parentPath !== projectPath) {
    const parentEntries = await safeReadDir(parentPath);
    for (const entry of parentEntries) {
      if (!entry.name) continue;
      const fullPath = joinPath(parentPath, entry.name);
      if (entry.isDirectory && !detected.inputDir && MINKNOW_DIR_RE.test(entry.name)) {
        detected.inputDir = fullPath;
      }
      if (entry.isFile) {
        if (!detected.customBarcodesPath && BARCODES_RE.test(entry.name)) {
          detected.customBarcodesPath = fullPath;
        }
        if (!detected.sampleMapPath && SAMPLE_MAP_RE.test(entry.name)) {
          detected.sampleMapPath = fullPath;
        }
        if (!detected.referencePath && REFERENCE_RE.test(entry.name)) {
          detected.referencePath = fullPath;
        }
        if (!detected.expectedPath && EXPECTED_RE.test(entry.name)) {
          detected.expectedPath = fullPath;
        }
      }
    }
  }

  return detected;
}
