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
  writeTextFile,
  readTextFile,
  exists,
} from "@tauri-apps/plugin-fs";

// ─── 상수 ─────────────────────────────────────────────────────────────────

export const DEBOUNCE_MS = 1500;
export const MAX_SKEW_MS = 30_000;
const AUTOSAVE_DIR_NAME = ".autosave";

// ─── 타입 ─────────────────────────────────────────────────────────────────

export type AutosaveKind = "kuro" | "mame";

export interface AutosaveTarget {
  /** 프로젝트 루트 절대 경로. null 또는 scratch면 모든 호출이 silent skip. */
  projectPath: string | null;
  scratch: boolean;
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
 * - missing: 파일 없음
 * - corrupted: JSON 파싱 실패. 파일을 .bad-<ts>로 rename 후 backupPath 반환
 * - schema_too_new: snapshot.schema > currentSchema
 */
export type ReadAutosaveResult =
  | { status: "ok"; snapshot: AutosaveSnapshot }
  | { status: "missing" }
  | { status: "corrupted"; backupPath: string }
  | { status: "schema_too_new"; foundSchema: number };

/**
 * 자동 저장 파일 읽기.
 * - 파일 없음 → missing
 * - JSON 파싱 실패 → .bad-<ts> rename 후 corrupted
 * - snapshot.schema > currentSchema → schema_too_new
 * - 그 외 → ok (schema < currentSchema 마이그레이션은 호출자 책임)
 */
export async function readAutosave(
  projectPath: string,
  kind: AutosaveKind,
  currentSchema: number,
): Promise<ReadAutosaveResult> {
  const filePath = autosavePath(projectPath, kind);
  const fileExists = await exists(filePath);
  if (!fileExists) return { status: "missing" };

  let text: string;
  try {
    text = await readTextFile(filePath);
  } catch {
    return { status: "missing" };
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
  if (state.inFlight !== null) return; // 이미 실행 중
  if (state.pending === null) return; // 할 일 없음

  const task = state.pending;
  state.pending = null;

  state.inFlight = task()
    .catch((err: unknown) => {
      console.warn(`[autosave] Write failed (${kind}):`, err);
      throw err;
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
 * scratch / projectPath null이면 silent skip.
 */
export function scheduleAutosave(
  target: AutosaveTarget,
  kind: AutosaveKind,
  buildSnapshot: () => AutosaveSnapshot,
): void {
  if (target.scratch || target.projectPath === null) return;

  const projectPath = target.projectPath;
  const state = kindState[kind];
  const now = Date.now();

  // 기존 디바운스 타이머 취소
  if (state.timer !== null) {
    clearTimeout(state.timer);
    state.timer = null;
  }

  const snapshot = buildSnapshot();
  const task = async (): Promise<void> => {
    await ensureAutosaveDir(projectPath);
    const filePath = autosavePath(projectPath, kind);
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
 */
export async function flushAutosave(
  target: AutosaveTarget,
  kind?: AutosaveKind,
): Promise<void> {
  if (target.scratch || target.projectPath === null) return;

  const kinds: AutosaveKind[] = kind !== undefined ? [kind] : ["kuro", "mame"];

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
  dirCache.clear();
}
