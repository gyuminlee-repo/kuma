/**
 * detectProjectFiles.ts — MAME 프로젝트 디렉토리에서 입력 파일 자동 감지
 *
 * 프로젝트 경로와 그 부모 디렉토리를 스캔하여 MAME 입력으로 쓸 수 있는
 * 후보 파일/폴더 경로를 반환한다. 각 필드는 매칭되지 않으면 undefined.
 *
 * 우선순위:
 *  1. autosave 복원값 (비어있지 않으면 탐지 스킵)
 *  2. mame_context.json (autosave로 채워지지 않은 필드만 적용)
 *  3. readDir 파일시스템 스캔 (mame_context.json 없거나 일부 필드 비었을 때만)
 */

import { readDir, readTextFile } from "@tauri-apps/plugin-fs";
import { join } from "@tauri-apps/api/path";
import { isMameContext, type MameContext } from "@/types/mame/mame_context";

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
  /** MinKNOW sequencing_summary*.txt */
  sequencingSummaryPath?: string;
}

const MINKNOW_DIR_RE = /^\d{8}_\d{4}_/;
const BARCODES_RE = /^(custom_)?barcode[s]?.*\.(xlsx|csv)$/i;
const SAMPLE_MAP_RE = /^(mutant[s]?|sample_map|well_map|plate_map).*\.xlsx$/i;
const REFERENCE_RE = /\.(fa|fasta)$/i;
const EXPECTED_RE = /^(expected|genotype|template).*\.(xlsx|csv)$/i;
const SEQ_SUMMARY_RE = /^sequencing_summary.*\.txt$/i;

type DirEntry = { name?: string; isDirectory: boolean; isFile: boolean };

function joinPath(dir: string, name: string): string {
  const sep = dir.includes("\\") ? "\\" : "/";
  return `${dir.trimEnd().replace(/[/\\]$/, "")}${sep}${name}`;
}

/**
 * mame_context.json을 읽어 파싱 결과를 반환한다.
 * 파일이 없거나 파싱 실패 시 null 반환 (에러 무시).
 */
async function readMameContext(projectPath: string): Promise<MameContext | null> {
  try {
    const contextPath = await join(projectPath, "mame_context.json");
    const text = await readTextFile(contextPath);
    const parsed: unknown = JSON.parse(text);
    if (!isMameContext(parsed)) {
      console.warn("[detectProjectFiles] mame_context.json: invalid schema, falling back to readDir");
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/**
 * mame_context.json의 상대 경로 필드를 절대 경로로 변환한다.
 * join() 실패 시 해당 필드는 undefined로 처리.
 */
async function resolveContextPaths(
  projectPath: string,
  context: MameContext,
): Promise<Pick<DetectedPaths, "customBarcodesPath" | "referencePath" | "sampleMapPath">> {
  const resolved: Pick<DetectedPaths, "customBarcodesPath" | "referencePath" | "sampleMapPath"> = {};

  if (context.custom_barcodes_path) {
    try {
      resolved.customBarcodesPath = await join(projectPath, context.custom_barcodes_path);
    } catch {
      console.warn("[detectProjectFiles] mame_context.json: failed to resolve custom_barcodes_path");
    }
  }
  if (context.reference_path) {
    try {
      resolved.referencePath = await join(projectPath, context.reference_path);
    } catch {
      console.warn("[detectProjectFiles] mame_context.json: failed to resolve reference_path");
    }
  }
  if (context.sample_map_template_path) {
    try {
      resolved.sampleMapPath = await join(projectPath, context.sample_map_template_path);
    } catch {
      console.warn("[detectProjectFiles] mame_context.json: failed to resolve sample_map_template_path");
    }
  }

  return resolved;
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
 * 프로젝트 경로와 그 부모 디렉토리를 스캔하여 후보 경로를 반환한다.
 * 빈 문자열인 현재 autosave 필드만 채운다 (비어있지 않은 값은 건드리지 않음).
 *
 * 우선순위:
 *  1. mame_context.json (autosave 이후 남은 빈 필드를 채움)
 *  2. readDir 스캔 (mame_context.json이 없거나 일부 필드가 여전히 비어있을 때)
 */
export async function detectProjectFiles(projectPath: string): Promise<DetectedPaths> {
  const sep = projectPath.includes("\\") ? "\\" : "/";
  const parentPath = projectPath.includes(sep)
    ? projectPath.slice(0, projectPath.lastIndexOf(sep))
    : projectPath;

  const detected: DetectedPaths = {};

  // ── mame_context.json 우선 처리
  const mameContext = await readMameContext(projectPath);
  if (mameContext) {
    const contextPaths = await resolveContextPaths(projectPath, mameContext);
    if (contextPaths.customBarcodesPath) {
      detected.customBarcodesPath = contextPaths.customBarcodesPath;
    }
    if (contextPaths.referencePath) {
      detected.referencePath = contextPaths.referencePath;
    }
    if (contextPaths.sampleMapPath) {
      detected.sampleMapPath = contextPaths.sampleMapPath;
    }
  }

  // ── readDir 스캔 (inputDir, expectedPath, sequencingSummaryPath는 mame_context.json에 없으므로 항상 실행)

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
        // MinKNOW run 폴더 안의 sequencing_summary*.txt 탐색
        if (!detected.sequencingSummaryPath) {
          const runEntries = await safeReadDir(fullPath);
          for (const re of runEntries) {
            if (re.name && re.isFile && SEQ_SUMMARY_RE.test(re.name)) {
              detected.sequencingSummaryPath = joinPath(fullPath, re.name);
              break;
            }
          }
        }
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
        if (!detected.sequencingSummaryPath && SEQ_SUMMARY_RE.test(entry.name)) {
          detected.sequencingSummaryPath = fullPath;
        }
      }
    }
  }

  return detected;
}
