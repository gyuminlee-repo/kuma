/**
 * autosave.ts — Phase 1: 순수 라이브러리 (UI/store 통합 없음)
 *
 * 공개 API:
 *   scheduleAutosave, flushAutosave, atomicWriteJson,
 *   ensureAutosaveDir, autosavePath, readAutosave
 */

import {
  mkdir,
  rename,
  remove,
  writeTextFile,
  readTextFile,
  exists,
} from "@tauri-apps/plugin-fs";
import { appDataDir } from "@tauri-apps/api/path";

// ─── 상수 ─────────────────────────────────────────────────────────────────

export const DEBOUNCE_MS = 1500;
export const MAX_SKEW_MS = 30_000;
const AUTOSAVE_DIR_NAME = ".autosave";
/** 프로젝트 없이(scratch) 작업할 때 쓰는 앱 데이터 디렉토리 파일명. */
const SCRATCH_FILE_NAME = "kuro-scratch-autosave.json";

// ─── 타입 ─────────────────────────────────────────────────────────────────

export type AutosaveKind = "kuro" | "mame";

/** autosave 라이프사이클 이벤트. UI 상태 인디케이터용. */
export type AutosaveEvent =
  | { kind: AutosaveKind; type: "saving" }
  | { kind: AutosaveKind; type: "saved"; savedAt: string /* ISO */ }
  | { kind: AutosaveKind; type: "error"; error: Error };

type AutosaveListener = (event: AutosaveEvent) => void;

export interface AutosaveTarget {
  /** 프로젝트 루트 절대 경로. */
  projectPath: string | null;
  scratch: boolean;
  /**
   * true면 프로젝트가 없거나 scratch일 때 앱 데이터 디렉토리의 고정 파일에
   * 저장한다 (kind === "kuro" 한정). 미지정이면 기존 동작대로 silent skip.
   */
  scratchFallback?: boolean;
}

export interface AutosaveSnapshot {
  schema: number;
  saved_at: string; // ISO8601
  kuma_version: string;
  [key: string]: unknown;
}

// ─── 내부 상태 ────────────────────────────────────────────────────────────

interface KindState {
  timer: ReturnType<typeof setTimeout> | null;
  lastFlushAt: number;
  /** in-flight write Promise. 직렬 큐: 끝나야 다음 write 실행. */
  inFlight: Promise<void> | null;
  /** 다음 flush에 실행할 task. in-flight 중 새 요청이 오면 덮어씀. */
  pending: (() => Promise<void>) | null;
  /**
   * 타이머가 살아 있는 동안 "타이머 만료 시 실행할 task"를 미리 저장.
   * flushAutosave가 타이머를 취소할 때 이 task를 pending으로 승격시킨다.
   */
  timerTask: (() => Promise<void>) | null;
}

const kindState: Record<AutosaveKind, KindState> = {
  kuro: { timer: null, lastFlushAt: 0, inFlight: null, pending: null, timerTask: null },
  mame: { timer: null, lastFlushAt: 0, inFlight: null, pending: null, timerTask: null },
};

/** ensureAutosaveDir 결과 캐시 (projectPath → dirPath) */
const dirCache = new Map<string, string>();

// ─── 쓰기 차단 게이트 ─────────────────────────────────────────────────────
//
// 두 게이트는 서로 다른 사고를 막으므로 분리해서 유지한다.
//
// 1) writeBlock (kind별, 지속): 자동 저장 파일을 "읽지 못했다"고 확인된 상태.
//    파일이 디스크에 있는데 일시적 잠금(AV 스캔 등)으로 못 읽었을 수 있고,
//    그 위에 빈 store 상태를 덮어쓰면 결과물까지 영구 소실된다. 성공적인
//    재읽기나 사용자 명시 행동(clearAutosaveBlock)이 있기 전까지 쓰기를 막는다.
// 2) hydrationDepth (전역, 일시): 복원이 진행 중인 구간. resetAll이 새 리터럴을
//    넣어 구독자가 즉시 스케줄을 걸지만, 그 시점 스냅샷은 복원 전 빈 상태다.
//    복원이 끝나기 전 디바운스가 만료되면 빈 스냅샷이 디스크에 착지한다.
//
// hydration 게이트만으로는 (1)을 못 막는다. 복원 실패 후 hydration이 끝나면
// 게이트가 풀리고, 첫 키 입력이 빈 상태를 그대로 덮어쓴다.

/** 읽기 실패로 쓰기가 봉인된 kind. 값은 진단용 원인. */
const writeBlock: Record<AutosaveKind, Error | null> = { kuro: null, mame: null };

/**
 * 복원 중첩 깊이. boolean이 아니라 카운터인 이유: 프로젝트 전환 시 새 effect가
 * begin을 부른 뒤 이전 effect의 async 본문이 뒤늦게 end를 부를 수 있고,
 * boolean이면 진행 중인 새 복원의 게이트가 그 시점에 풀린다.
 */
let hydrationDepth = 0;

/** 읽기 실패 등으로 해당 kind의 자동 저장 쓰기를 봉인한다. */
export function blockAutosaveWrites(kind: AutosaveKind, reason: Error): void {
  writeBlock[kind] = reason;
}

/** 봉인 해제. 성공적인 읽기 또는 사용자 명시 행동에서만 호출한다. */
export function clearAutosaveBlock(kind: AutosaveKind): void {
  writeBlock[kind] = null;
}

/** 현재 봉인 원인(없으면 null). */
export function autosaveBlockReason(kind: AutosaveKind): Error | null {
  return writeBlock[kind];
}

/** 복원 시작. 반드시 finally에서 endHydration과 짝을 이룬다. */
export function beginHydration(): void {
  hydrationDepth += 1;
}

/** 복원 종료. */
export function endHydration(): void {
  if (hydrationDepth > 0) hydrationDepth -= 1;
}

/** @internal 테스트·진단용. */
export function isHydrating(): boolean {
  return hydrationDepth > 0;
}

// ─── 옵저버 ──────────────────────────────────────────────────────────────

const listeners = new Set<AutosaveListener>();

/**
 * autosave 이벤트(saving / saved / error) 구독.
 * 반환 함수를 호출하면 구독 해제된다.
 */
export function onAutosaveEvent(listener: AutosaveListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function emit(event: AutosaveEvent): void {
  for (const l of listeners) l(event);
}

// ─── 경로 헬퍼 ────────────────────────────────────────────────────────────

/** OS 경로 구분자. Tauri IPC는 절대 경로를 그대로 받으므로 `/`로 통일. */
function joinPath(...segments: string[]): string {
  return segments
    .map((s, i) => (i === 0 ? s.replace(/[/\\]+$/, "") : s.replace(/^[/\\]+/, "")))
    .join("/");
}

/**
 * 자동 저장 파일 경로. .autosave/<kind>.json
 */
export function autosavePath(projectPath: string, kind: AutosaveKind): string {
  return joinPath(projectPath, AUTOSAVE_DIR_NAME, `${kind}.json`);
}

// ─── 디렉토리 보장 ────────────────────────────────────────────────────────

/**
 * `.autosave/` 디렉토리 보장(없으면 mkdir). 한 번 만들면 캐시.
 */
export async function ensureAutosaveDir(projectPath: string): Promise<string> {
  const cached = dirCache.get(projectPath);
  if (cached !== undefined) return cached;

  const dirPath = joinPath(projectPath, AUTOSAVE_DIR_NAME);
  const alreadyExists = await exists(dirPath);
  if (!alreadyExists) {
    await mkdir(dirPath, { recursive: true });
  }
  dirCache.set(projectPath, dirPath);
  return dirPath;
}

/**
 * scratch 자동 저장 파일 경로 (앱 데이터 디렉토리 / kuro-scratch-autosave.json).
 * 디렉토리는 첫 실행에 없을 수 있으므로 recursive mkdir로 보장한다.
 */
export async function scratchAutosavePath(): Promise<string> {
  const baseDir = await appDataDir();
  const alreadyExists = await exists(baseDir);
  if (!alreadyExists) {
    await mkdir(baseDir, { recursive: true });
  }
  return joinPath(baseDir, SCRATCH_FILE_NAME);
}

/**
 * target + kind 조합에서 실제 저장 파일 경로를 정한다.
 * 우선순위: 실제 프로젝트 > scratch fallback > skip(null).
 * scratch fallback은 kuro 전용 (mame 자동 저장 동작은 그대로 유지).
 */
async function resolveTargetPath(
  target: AutosaveTarget,
  kind: AutosaveKind,
): Promise<string | null> {
  if (target.projectPath !== null && !target.scratch) {
    await ensureAutosaveDir(target.projectPath);
    return autosavePath(target.projectPath, kind);
  }
  if (target.scratchFallback === true && kind === "kuro") {
    return await scratchAutosavePath();
  }
  return null;
}

/** 저장 대상이 존재하는지(= silent skip 대상이 아닌지) 판정. */
function hasWritableTarget(target: AutosaveTarget, kind: AutosaveKind): boolean {
  if (target.projectPath !== null && !target.scratch) return true;
  return target.scratchFallback === true && kind === "kuro";
}

// ─── Atomic write ────────────────────────────────────────────────────────

/**
 * 단일 atomic write (tmp 경로 쓰기 → rename).
 * tmp 쓰기 실패 시 원본 보존, throw.
 */
export async function atomicWriteJson(filePath: string, data: unknown): Promise<void> {
  const tmpPath = `${filePath}.tmp`;
  await writeTextFile(tmpPath, JSON.stringify(data, null, 2));
  await rename(tmpPath, filePath);
}

// ─── readAutosave ────────────────────────────────────────────────────────

/**
 * readAutosave 반환 타입.
 * - ok: 정상 파싱 (schema <= currentSchema)
 * - missing: 파일이 존재하지 않음 (침묵 처리 가능)
 * - read_failed: 파일 유무를 확인 못 했거나 열지 못함. missing과 반드시 구분해야
 *   한다. 디스크에는 멀쩡한 스냅샷이 있는데 일시적 잠금으로 못 읽은 경우가
 *   여기 들어오며, missing으로 뭉개면 그 위에 빈 상태가 덮어써진다.
 * - corrupted: JSON 파싱 실패. 파일을 .bad-<ts>로 rename 후 backupPath 반환
 * - schema_too_new: snapshot.schema > currentSchema
 */
export type ReadAutosaveResult =
  | { status: "ok"; snapshot: AutosaveSnapshot }
  | { status: "missing" }
  | { status: "read_failed"; error: Error; filePath: string }
  | { status: "corrupted"; backupPath: string }
  | { status: "schema_too_new"; foundSchema: number };

/**
 * 자동 저장 파일 읽기.
 * - 파일 없음 → missing
 * - 존재 확인·열기 실패 → read_failed
 * - JSON 파싱 실패 → .bad-<ts> rename 후 corrupted
 * - snapshot.schema > currentSchema → schema_too_new
 * - 그 외 → ok (schema < currentSchema 마이그레이션은 호출자 책임)
 */
export async function readAutosave(
  projectPath: string,
  kind: AutosaveKind,
  currentSchema: number,
): Promise<ReadAutosaveResult> {
  return await readAutosaveFile(autosavePath(projectPath, kind), currentSchema);
}

/**
 * scratch(프로젝트 없음) 자동 저장 파일 읽기. 규칙은 readAutosave와 동일.
 * 앱 데이터 디렉토리 접근 자체가 실패하면 read_failed다. 경로를 못 구했다는
 * 것은 "파일이 없다"는 증거가 아니므로 missing으로 강등하지 않는다.
 */
export async function readScratchAutosave(
  currentSchema: number,
): Promise<ReadAutosaveResult> {
  let filePath: string;
  try {
    filePath = await scratchAutosavePath();
  } catch (err) {
    const error = err instanceof Error ? err : new Error(String(err));
    console.warn("[autosave] scratch path resolution failed:", error);
    return { status: "read_failed", error, filePath: SCRATCH_FILE_NAME };
  }
  return await readAutosaveFile(filePath, currentSchema);
}

/**
 * scratch 스냅샷 파일 삭제. 프로젝트로 승격한 뒤 같은 스냅샷이 다음 신규
 * 프로젝트로 다시 새어 나가지 않게 한다. 파일이 없으면 no-op.
 */
export async function deleteScratchAutosave(): Promise<void> {
  const filePath = await scratchAutosavePath();
  if (!(await exists(filePath))) return;
  await remove(filePath);
}

async function readAutosaveFile(
  filePath: string,
  currentSchema: number,
): Promise<ReadAutosaveResult> {
  let fileExists: boolean;
  try {
    fileExists = await exists(filePath);
  } catch (err) {
    const error = err instanceof Error ? err : new Error(String(err));
    console.warn(`[autosave] existence check failed: ${filePath}`, error);
    return { status: "read_failed", error, filePath };
  }
  if (!fileExists) return { status: "missing" };

  let text: string;
  try {
    text = await readTextFile(filePath);
  } catch (err) {
    const error = err instanceof Error ? err : new Error(String(err));
    console.warn(`[autosave] read failed: ${filePath}`, error);
    return { status: "read_failed", error, filePath };
  }

  let parsed: AutosaveSnapshot;
  try {
    parsed = JSON.parse(text) as AutosaveSnapshot;
  } catch {
    const isoTs = new Date().toISOString().replace(/[:.]/g, "-");
    const backupPath = `${filePath}.bad-${isoTs}`;
    try {
      await rename(filePath, backupPath);
    } catch {
      console.warn(`[autosave] Failed to rename corrupted file: ${filePath}`);
    }
    return { status: "corrupted", backupPath };
  }

  if (parsed.schema > currentSchema) {
    return { status: "schema_too_new", foundSchema: parsed.schema };
  }

  return { status: "ok", snapshot: parsed };
}

// ─── 직렬 큐 실행 ────────────────────────────────────────────────────────

/**
 * in-flight가 끝난 뒤 pending task를 실행. pending이 없으면 종료.
 * 직렬성 보장: 같은 kind 내에서는 동시 write 없음.
 */
function drainQueue(kind: AutosaveKind): void {
  const state = kindState[kind];
  if (state.inFlight !== null) return; // already running
  if (state.pending === null) return; // nothing pending

  const task = state.pending;
  state.pending = null;

  emit({ kind, type: "saving" });

  state.inFlight = task()
    .then(() => {
      emit({ kind, type: "saved", savedAt: new Date().toISOString() });
    })
    .catch((err: unknown) => {
      const error = err instanceof Error ? err : new Error(String(err));
      console.warn(`[autosave] Write failed (${kind}):`, error);
      emit({ kind, type: "error", error });
      throw error;
    })
    .finally(() => {
      state.inFlight = null;
      // 실행 도중 새 pending이 쌓였으면 연속 실행
      drainQueue(kind);
    });
}

// ─── scheduleAutosave ─────────────────────────────────────────────────────

/**
 * 1.5초 디바운스 + 30초 강제 flush + 직렬 큐.
 * 저장 대상이 없으면(프로젝트 없음 + scratchFallback 미지정) silent skip.
 */
export function scheduleAutosave(
  target: AutosaveTarget,
  kind: AutosaveKind,
  buildSnapshot: () => AutosaveSnapshot,
): void {
  if (!hasWritableTarget(target, kind)) return;
  // 읽지 못한 스냅샷 위에 덮어쓰지 않는다.
  if (writeBlock[kind] !== null) return;
  // 복원 중에는 스냅샷이 아직 빈 상태다. 여기서 스케줄이 걸리면 복원이 끝나기
  // 전에 디바운스가 만료돼 빈 스냅샷이 디스크에 착지한다.
  if (hydrationDepth > 0) return;

  const resolvedTarget: AutosaveTarget = { ...target };
  const state = kindState[kind];
  const now = Date.now();

  // 기존 디바운스 타이머 취소
  if (state.timer !== null) {
    clearTimeout(state.timer);
    state.timer = null;
  }

  const snapshot = buildSnapshot();
  const task = async (): Promise<void> => {
    const filePath = await resolveTargetPath(resolvedTarget, kind);
    if (filePath === null) return;
    await atomicWriteJson(filePath, snapshot);
  };

  const enqueue = (): void => {
    state.lastFlushAt = Date.now();
    state.timerTask = null;
    state.pending = task;
    drainQueue(kind);
  };

  // 30초 강제 flush: 마지막 flush 이후 MAX_SKEW_MS 초과 시 즉시 실행
  const elapsed = now - state.lastFlushAt;
  if (state.lastFlushAt > 0 && elapsed >= MAX_SKEW_MS) {
    enqueue();
    return;
  }

  // 타이머 등록. timerTask에 미리 저장해 flushAutosave가 즉시 승격 가능하게 함.
  state.timerTask = task;
  state.timer = setTimeout(() => {
    state.timer = null;
    enqueue();
  }, DEBOUNCE_MS);
}

// ─── flushAutosave ────────────────────────────────────────────────────────

/**
 * 디바운스 큐를 즉시 flush. close 직전, 탭 전환 직전 등에서 사용.
 * 반환 Promise는 in-flight 쓰기까지 모두 끝나야 resolve.
 *
 * writeBlock/hydrationDepth 게이트는 여기서 적용하지 않는다. 이미 큐에 들어간
 * task는 게이트가 걸리기 전 상태(= 유효한 스냅샷)를 들고 있고, 대상 경로도
 * 그 시점 target으로 고정돼 있다. 그것까지 버리면 직전 편집분이 사라진다.
 * 두 게이트는 "새 스케줄"만 막는다.
 */
export async function flushAutosave(
  target: AutosaveTarget,
  kind?: AutosaveKind,
): Promise<void> {
  const requested: AutosaveKind[] = kind !== undefined ? [kind] : ["kuro", "mame"];
  const kinds = requested.filter((k) => hasWritableTarget(target, k));
  if (kinds.length === 0) return;

  await Promise.all(
    kinds.map(async (k) => {
      const state = kindState[k];

      // 대기 중인 타이머가 있으면 즉시 pending으로 승격
      if (state.timer !== null) {
        clearTimeout(state.timer);
        state.timer = null;
        if (state.timerTask !== null) {
          state.lastFlushAt = Date.now();
          state.pending = state.timerTask;
          state.timerTask = null;
        }
        drainQueue(k);
      }

      // in-flight + pending 모두 끝날 때까지 대기
      await waitForDrain(k);
    }),
  );
}

/** in-flight + pending 체인이 완전히 빌 때까지 대기 */
async function waitForDrain(kind: AutosaveKind): Promise<void> {
  const state = kindState[kind];
  // 최대 반복 횟수: 무한 루프 방지
  for (let i = 0; i < 100; i++) {
    if (state.inFlight === null && state.pending === null) break;
    if (state.inFlight !== null) {
      try {
        await state.inFlight;
      } catch {
        // 실패해도 drain 완료로 간주
      }
    }
    // inFlight가 끝난 뒤 pending이 새로 시작됐을 수 있으므로 다시 확인
    if (state.pending !== null) {
      drainQueue(kind);
    }
  }
}

// ─── 테스트 전용: 상태 초기화 ────────────────────────────────────────────

/** @internal 단위 테스트에서만 사용. 전역 상태를 초기 값으로 되돌림. */
export function _resetStateForTest(): void {
  for (const k of ["kuro", "mame"] as AutosaveKind[]) {
    const state = kindState[k];
    if (state.timer !== null) clearTimeout(state.timer);
    state.timer = null;
    state.lastFlushAt = 0;
    state.inFlight = null;
    state.pending = null;
    state.timerTask = null;
  }
  writeBlock.kuro = null;
  writeBlock.mame = null;
  hydrationDepth = 0;
  dirCache.clear();
  listeners.clear();
}
