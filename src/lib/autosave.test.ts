/**
 * autosave.test.ts — Phase 1 단위 테스트
 *
 * @tauri-apps/plugin-fs 전체를 mock 처리하고,
 * 디바운스·직렬 큐·scratch skip·flushAutosave 동작을 검증한다.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ─── plugin-fs mock ───────────────────────────────────────────────────────

const mockWriteTextFile = vi.fn<(path: string, data: string) => Promise<void>>();
const mockRename = vi.fn<(oldPath: string, newPath: string) => Promise<void>>();
const mockMkdir = vi.fn<(path: string, opts?: { recursive?: boolean }) => Promise<void>>();
const mockExists = vi.fn<(path: string) => Promise<boolean>>();
const mockReadTextFile = vi.fn<(path: string) => Promise<string>>();
const mockRemove = vi.fn<(path: string) => Promise<void>>();

vi.mock("@tauri-apps/plugin-fs", () => ({
  writeTextFile: (...args: Parameters<typeof mockWriteTextFile>) => mockWriteTextFile(...args),
  rename: (...args: Parameters<typeof mockRename>) => mockRename(...args),
  mkdir: (...args: Parameters<typeof mockMkdir>) => mockMkdir(...args),
  exists: (...args: Parameters<typeof mockExists>) => mockExists(...args),
  readTextFile: (...args: Parameters<typeof mockReadTextFile>) => mockReadTextFile(...args),
  remove: (...args: Parameters<typeof mockRemove>) => mockRemove(...args),
}));

// ─── 모듈 import (mock 등록 후) ──────────────────────────────────────────

import {
  scheduleAutosave,
  flushAutosave,
  atomicWriteJson,
  autosavePath,
  readAutosave,
  onAutosaveEvent,
  blockAutosaveWrites,
  clearAutosaveBlock,
  beginHydration,
  endHydration,
  _resetStateForTest,
  DEBOUNCE_MS,
  type AutosaveTarget,
  type AutosaveSnapshot,
  type AutosaveEvent,
} from "./autosave";

// ─── 헬퍼 ────────────────────────────────────────────────────────────────

// 테스트 전용 프로젝트 경로: 환경변수 또는 fallback (절대 경로 하드코딩 금지)
const PROJECT_PATH =
  (typeof process !== "undefined" && process.env["TEST_PROJECT_PATH"]) ||
  "/tmp/kuma-autosave-test-project";

function makeTarget(overrides?: Partial<AutosaveTarget>): AutosaveTarget {
  return { projectPath: PROJECT_PATH, scratch: false, ...overrides };
}

function makeSnapshot(label = "snap"): AutosaveSnapshot {
  return {
    schema: 1,
    saved_at: new Date().toISOString(),
    kuma_version: "0.1.4",
    label,
  };
}

// ─── 설정 ─────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers();
  _resetStateForTest();
  mockWriteTextFile.mockResolvedValue(undefined);
  mockRename.mockResolvedValue(undefined);
  mockMkdir.mockResolvedValue(undefined);
  mockExists.mockResolvedValue(true); // .autosave 디렉토리가 이미 있다고 가정
  mockRemove.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

// ─── 테스트 케이스 ────────────────────────────────────────────────────────

describe("scheduleAutosave", () => {
  it("TC1: 1.5초 디바운스 후 atomic write를 정확히 1회 호출한다", async () => {
    const target = makeTarget();
    scheduleAutosave(target, "kuro", () => makeSnapshot("single"));

    // 디바운스 전: write 없음
    expect(mockWriteTextFile).not.toHaveBeenCalled();

    // DEBOUNCE_MS 경과
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    // 비동기 Promise flush
    await Promise.resolve();
    await Promise.resolve();

    // writeTextFile(tmp) + rename 각 1회
    expect(mockWriteTextFile).toHaveBeenCalledTimes(1);
    expect(mockRename).toHaveBeenCalledTimes(1);

    // tmp 경로가 .tmp 접미사를 가지는지 확인
    const tmpArg = mockWriteTextFile.mock.calls[0][0];
    expect(tmpArg).toMatch(/\.tmp$/);
  });

  it("TC2: 1.5초 안에 같은 kind 3번 호출하면 마지막 payload 한 번만 저장한다", async () => {
    const target = makeTarget();

    scheduleAutosave(target, "kuro", () => makeSnapshot("first"));
    await vi.advanceTimersByTimeAsync(500);

    scheduleAutosave(target, "kuro", () => makeSnapshot("second"));
    await vi.advanceTimersByTimeAsync(500);

    scheduleAutosave(target, "kuro", () => makeSnapshot("third"));

    // 마지막 호출로부터 DEBOUNCE_MS 경과
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    await Promise.resolve();
    await Promise.resolve();

    // write는 1회만
    expect(mockWriteTextFile).toHaveBeenCalledTimes(1);
    expect(mockRename).toHaveBeenCalledTimes(1);

    // payload가 "third"인지 검증
    const written = JSON.parse(mockWriteTextFile.mock.calls[0][1] as string) as AutosaveSnapshot;
    expect(written.label).toBe("third");
  });

  it("TC3: target.scratch === true → 어떤 호출도 silent skip (write 0회)", async () => {
    const target = makeTarget({ scratch: true });
    scheduleAutosave(target, "kuro", () => makeSnapshot());

    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS * 2);
    await Promise.resolve();

    expect(mockWriteTextFile).not.toHaveBeenCalled();
    expect(mockRename).not.toHaveBeenCalled();
  });

  it("TC4: target.projectPath === null → 동일 silent skip (write 0회)", async () => {
    const target = makeTarget({ projectPath: null });
    scheduleAutosave(target, "mame", () => makeSnapshot());

    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS * 2);
    await Promise.resolve();

    expect(mockWriteTextFile).not.toHaveBeenCalled();
    expect(mockRename).not.toHaveBeenCalled();
  });
});

describe("쓰기 게이트", () => {
  it("TC3b: 읽기 실패로 봉인된 kind는 스케줄이 걸리지 않는다", async () => {
    const target = makeTarget();
    blockAutosaveWrites("kuro", new Error("locked by another process"));

    scheduleAutosave(target, "kuro", () => makeSnapshot("must-not-land"));
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS * 2);
    await Promise.resolve();

    expect(mockWriteTextFile).not.toHaveBeenCalled();

    // 봉인 해제 후에는 다시 저장된다.
    clearAutosaveBlock("kuro");
    scheduleAutosave(target, "kuro", () => makeSnapshot("lands"));
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    await Promise.resolve();
    await Promise.resolve();

    expect(mockWriteTextFile).toHaveBeenCalledTimes(1);
  });

  it("TC3c: 복원 중에는 스케줄이 걸리지 않고, 끝난 뒤 다시 걸린다", async () => {
    const target = makeTarget();
    beginHydration();

    scheduleAutosave(target, "kuro", () => makeSnapshot("empty-during-hydration"));
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS * 2);
    await Promise.resolve();

    expect(mockWriteTextFile).not.toHaveBeenCalled();

    endHydration();
    scheduleAutosave(target, "kuro", () => makeSnapshot("after-hydration"));
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
    await Promise.resolve();
    await Promise.resolve();

    expect(mockWriteTextFile).toHaveBeenCalledTimes(1);
    const written = JSON.parse(mockWriteTextFile.mock.calls[0][1] as string) as AutosaveSnapshot;
    expect(written.label).toBe("after-hydration");
  });

  it("TC3d: 중첩 복원에서 안쪽 end가 바깥 게이트를 풀지 않는다", async () => {
    const target = makeTarget();
    beginHydration();
    beginHydration();
    endHydration();

    scheduleAutosave(target, "kuro", () => makeSnapshot());
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS * 2);
    await Promise.resolve();

    expect(mockWriteTextFile).not.toHaveBeenCalled();
    endHydration();
  });
});

describe("readAutosave 읽기 실패", () => {
  it("TC3e: readTextFile 실패는 missing이 아니라 read_failed다", async () => {
    mockExists.mockResolvedValue(true);
    mockReadTextFile.mockRejectedValue(new Error("EBUSY"));

    const result = await readAutosave(PROJECT_PATH, "kuro", 2);

    expect(result.status).toBe("read_failed");
    if (result.status === "read_failed") {
      expect(result.error.message).toBe("EBUSY");
      expect(result.filePath).toBe(autosavePath(PROJECT_PATH, "kuro"));
    }
  });

  it("TC3f: 파일이 없으면 그대로 missing이다", async () => {
    mockExists.mockResolvedValue(false);

    const result = await readAutosave(PROJECT_PATH, "kuro", 2);

    expect(result.status).toBe("missing");
  });
});

describe("flushAutosave", () => {
  it("TC5: flushAutosave가 디바운스 큐를 즉시 비우고 모든 write가 끝난 뒤 resolve한다", async () => {
    const target = makeTarget();

    // kuro + mame 각각 schedule (타이머 등록)
    scheduleAutosave(target, "kuro", () => makeSnapshot("kuro-payload"));
    scheduleAutosave(target, "mame", () => makeSnapshot("mame-payload"));

    // 아직 타이머 미경과 상태에서 flush
    expect(mockWriteTextFile).not.toHaveBeenCalled();

    // 실시간 타이머로 전환하고 flush 호출
    vi.useRealTimers();
    await flushAutosave(target);

    expect(mockWriteTextFile).toHaveBeenCalledTimes(2);
    expect(mockRename).toHaveBeenCalledTimes(2);
  });
});

describe("atomicWriteJson", () => {
  it("TC6: tmp → rename 시퀀스로 동작하며 호출 순서와 인자를 검증한다", async () => {
    const filePath = `${PROJECT_PATH}/.autosave/kuro.json`;
    const data: AutosaveSnapshot = {
      schema: 1,
      saved_at: "2026-04-28T00:00:00Z",
      kuma_version: "0.1.4",
    };

    vi.useRealTimers();
    await atomicWriteJson(filePath, data);

    // writeTextFile이 rename보다 먼저 호출돼야 함
    const writeOrder = mockWriteTextFile.mock.invocationCallOrder[0];
    const renameOrder = mockRename.mock.invocationCallOrder[0];
    expect(writeOrder).toBeLessThan(renameOrder);

    // writeTextFile 인자: (tmp 경로, JSON 문자열)
    expect(mockWriteTextFile).toHaveBeenCalledWith(`${filePath}.tmp`, expect.any(String));

    // rename 인자: (tmp 경로, 원본 경로)
    expect(mockRename).toHaveBeenCalledWith(`${filePath}.tmp`, filePath);

    // JSON 내용이 올바른지
    const written = JSON.parse(mockWriteTextFile.mock.calls[0][1] as string) as AutosaveSnapshot;
    expect(written.schema).toBe(1);
    expect(written.kuma_version).toBe("0.1.4");
  });
});

describe("readAutosave", () => {
  it("TC7: 손상 JSON 파일을 .bad-<ts>로 rename하고 corrupted를 반환한다", async () => {
    vi.useRealTimers();

    const filePath = autosavePath(PROJECT_PATH, "kuro");
    mockExists.mockResolvedValue(true);
    mockReadTextFile.mockResolvedValue("{ this is not valid json !!!");

    const result = await readAutosave(PROJECT_PATH, "kuro", 1);

    expect(result.status).toBe("corrupted");
    if (result.status !== "corrupted") return; // type narrowing

    // rename이 호출됐는지, 원본 경로가 oldPath인지
    expect(mockRename).toHaveBeenCalledTimes(1);
    const [oldPath, badPath] = mockRename.mock.calls[0] as [string, string];
    expect(oldPath).toBe(filePath);
    expect(badPath).toMatch(/\.bad-/);

    // bad 경로에 연도가 포함돼 있는지 (타임스탬프 형식 검증)
    expect(badPath).toMatch(/\d{4}/);
    expect(result.backupPath).toBe(badPath);
  });

  it("파일이 존재하지 않으면 missing을 반환한다", async () => {
    vi.useRealTimers();
    mockExists.mockResolvedValue(false);

    const result = await readAutosave(PROJECT_PATH, "mame", 1);
    expect(result.status).toBe("missing");
    expect(mockReadTextFile).not.toHaveBeenCalled();
  });

  it("정상 JSON이고 schema 일치하면 ok + 파싱된 스냅샷을 반환한다", async () => {
    vi.useRealTimers();
    const snapshot: AutosaveSnapshot = {
      schema: 1,
      saved_at: "2026-04-28T10:00:00Z",
      kuma_version: "0.1.4",
      input: { sequence_path: "relative/path.gb" },
    };
    mockExists.mockResolvedValue(true);
    mockReadTextFile.mockResolvedValue(JSON.stringify(snapshot));

    const result = await readAutosave(PROJECT_PATH, "kuro", 1);
    expect(result.status).toBe("ok");
    if (result.status !== "ok") return;
    expect(result.snapshot).toEqual(snapshot);
    expect(mockRename).not.toHaveBeenCalled();
  });

  it("TC8: schema_too_new — snapshot.schema > currentSchema이면 schema_too_new를 반환한다", async () => {
    vi.useRealTimers();
    const snapshot: AutosaveSnapshot = {
      schema: 99,
      saved_at: "2026-04-28T10:00:00Z",
      kuma_version: "99.0.0",
    };
    mockExists.mockResolvedValue(true);
    mockReadTextFile.mockResolvedValue(JSON.stringify(snapshot));

    const result = await readAutosave(PROJECT_PATH, "kuro", 1);
    expect(result.status).toBe("schema_too_new");
    if (result.status !== "schema_too_new") return;
    expect(result.foundSchema).toBe(99);
    // 파일 rename 없음 (파일 보존)
    expect(mockRename).not.toHaveBeenCalled();
  });

  it("TC9: schema < currentSchema이면 ok로 반환한다 (마이그레이션은 호출자 책임)", async () => {
    vi.useRealTimers();
    const snapshot: AutosaveSnapshot = {
      schema: 1,
      saved_at: "2026-04-28T10:00:00Z",
      kuma_version: "0.1.0",
    };
    mockExists.mockResolvedValue(true);
    mockReadTextFile.mockResolvedValue(JSON.stringify(snapshot));

    // currentSchema = 2 (미래 버전의 앱이 구 스냅샷 읽는 상황)
    const result = await readAutosave(PROJECT_PATH, "kuro", 2);
    expect(result.status).toBe("ok");
    if (result.status !== "ok") return;
    expect(result.snapshot.schema).toBe(1);
    expect(mockRename).not.toHaveBeenCalled();
  });
});

describe("onAutosaveEvent (observer)", () => {
  it("TC10: 옵저버가 saving → saved 순서로 호출되고 savedAt이 ISO 문자열이다", async () => {
    vi.useRealTimers();

    const received: AutosaveEvent[] = [];
    const unsub = onAutosaveEvent((ev) => received.push(ev));

    const target = makeTarget();
    scheduleAutosave(target, "kuro", () => makeSnapshot("observer-test"));

    await flushAutosave(target, "kuro");

    unsub();

    // saving 이벤트가 먼저, saved 이벤트가 뒤에 와야 함
    expect(received.length).toBeGreaterThanOrEqual(2);
    const savingIdx = received.findIndex((e) => e.type === "saving");
    const savedIdx = received.findIndex((e) => e.type === "saved");
    expect(savingIdx).toBeGreaterThanOrEqual(0);
    expect(savedIdx).toBeGreaterThanOrEqual(0);
    expect(savingIdx).toBeLessThan(savedIdx);

    // saved 이벤트의 savedAt이 ISO 형식인지 확인
    const savedEv = received[savedIdx];
    if (savedEv.type !== "saved") throw new Error("narrowing");
    expect(savedEv.savedAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);

    // 구독 해제 후 추가 이벤트 없음
    const prevCount = received.length;
    scheduleAutosave(target, "kuro", () => makeSnapshot("after-unsub"));
    await flushAutosave(target, "kuro");
    expect(received.length).toBe(prevCount);
  });
});
