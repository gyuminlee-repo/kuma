# Workspace Artifact Handoff & MAME Clear All — 구현 계획

**Mode:** shape
**Spec:** `notes/specs/2026-05-13-workspace-artifact-handoff.md`
**Target branch:** `feat/kuma-integration` (MAME 코드 존재)
**Confidence:** Completeness 5/5, Clarity 4/5, Feasibility 4/5 = 13/15

**목표:** Export 시점에 자동 생성되는 `.kuma-workspace.json` 매니페스트로 다단계 워크플로우 산출물을 다음 단계에 자동 prefill. MAME에 Clear All 도입.

**아키텍처:** 프론트엔드 단일 책임 모듈 `src/lib/workspace/` 신규. 기존 export slice가 export 성공 후 `registerArtifacts()` 호출. 입력 컴포넌트는 `useArtifact(type)` 훅으로 prefill. KURO·MAME 공통 `clearWorkspace(appId)`.

**기술 스택:** TypeScript, Zustand, Tauri fs plugin, Vitest, React Testing Library, shadcn/ui.

---

## 파일 매핑

### 생성

| 파일 | 책임 |
|---|---|
| `src/lib/workspace/types.ts` | `AppId`, `ArtifactType`, `ArtifactRef`, manifest 스키마 타입 |
| `src/lib/workspace/manifest.ts` | 매니페스트 read/write/upsert 저수준 (Tauri fs) |
| `src/lib/workspace/api.ts` | `registerArtifacts`, `listArtifacts`, `getLatestArtifact`, `clearWorkspace`, `openWorkspace` |
| `src/lib/workspace/events.ts` | `workspace:updated` 이벤트 emitter (mitt 또는 EventTarget) |
| `src/lib/workspace/useArtifact.ts` | React 훅 |
| `src/lib/workspace/index.ts` | barrel export |
| `src/components/widgets/ArtifactBadge.tsx` | prefill 배지 UI |
| `src/components/mame/dialogs/MameClearAllDialog.tsx` | MAME Clear All 확인 다이얼로그 |
| `tests/workspace/manifest.test.ts` | 매니페스트 IO 테스트 |
| `tests/workspace/api.test.ts` | API 동작 테스트 |
| `tests/workspace/useArtifact.test.tsx` | 훅 테스트 |
| `tests/workspace/clearWorkspace.test.ts` | app 격리 테스트 |
| `tests/components/MameClearAll.test.tsx` | MAME Clear All UI 테스트 |

### 수정

| 파일 | 위치 | 변경 |
|---|---|---|
| `src/store/slices/exportSlice.ts` | `exportExcel` (L339-380), 신규 export 메서드 | export 성공 후 `registerArtifacts` 호출 |
| `src/store/mame/slices/exportSlice.ts` | `exportExcel` (L13-) | MAME export 후 `registerArtifacts` 호출 |
| `src/store/slices/inputSlice.ts` | `evolveproCsvPath` 초기화 경로 | useArtifact fallback 연동 |
| `src/components/panels/*EvolveproInput*.tsx` (실 컴포넌트명 grep) | mount 시 `useArtifact("evolvepro_csv")` 추가 + 배지 표시 |
| `src/components/mame/layout/MameAppLayout.tsx` | 상단 우측 | Clear All 버튼 신규 |
| `src/store/mame/mameAppStore.ts` | 신규 메서드 | `resetAll(): void` 추가 — 각 슬라이스 reset 호출 |
| `src/store/mame/slices/inputSlice.ts` | 메서드 추가 | `reset()` (이미 없으면) |
| `src/store/mame/slices/analysisSlice.ts` | 메서드 추가 | `reset()` |
| `src/store/mame/slices/phaseSlice.ts` | 메서드 추가 | `reset()` |
| `src/store/mame/slices/exportSlice.ts` | 메서드 추가 | `reset()` |
| `src/components/layout/AppLayout.tsx` | L234 `resetAll()` 인접 | `clearWorkspace("kuro")` 추가 호출 |
| `src/locales/en/common.json`, `src/locales/ko/common.json` | i18n 신규 키 (artifact.badge.detected, mame.clearAll.* 등) |
| `.cross-layer-sync.json` | 신규 그룹 추가 — workspace artifact registry 일관성 |

---

## Task 0: 사전 준비 — 올바른 base branch 확인

- [ ] **Step 1: feat/kuma-integration 기반 worktree 재생성**

현재 worktree는 origin/main에서 분기되어 MAME 코드 없음. `$REPO_ROOT` 는 `git rev-parse --show-toplevel` 결과.

```bash
git worktree remove "$REPO_ROOT/.claude/worktrees/workspace-artifact-handoff-spec" --force
git worktree add "$REPO_ROOT/.claude/worktrees/workspace-artifact-handoff" feat/kuma-integration
cd "$REPO_ROOT/.claude/worktrees/workspace-artifact-handoff"
git checkout -b feat/workspace-artifact-handoff
```

- [ ] **Step 2: 스펙·플랜 파일 복사**

스펙·플랜 문서 두 개를 새 worktree로 복사 후 커밋.

- [ ] **Step 3: 의존성 설치 + 베이스라인 테스트**

```bash
pnpm install
pnpm test --run
npx tsc --noEmit
```

예상: 기존 테스트 PASS, 타입 0 에러.

---

## Task 1: 매니페스트 타입 정의

**파일:**
- 생성: `src/lib/workspace/types.ts`
- 테스트: 타입만이므로 별도 테스트 없음 (Task 2에서 함께 검증)

- [ ] **Step 1: 타입 정의 작성**

```ts
// src/lib/workspace/types.ts
export type AppId = "kuro" | "mame" | "primerbench";

export type ArtifactType =
  | "evolvepro_csv"
  | "sdm_primer_xlsx"
  | "mame_consensus_fasta";

export interface ManifestArtifact {
  id: string;
  app: AppId;
  step: string;
  type: ArtifactType;
  path: string;       // relative to manifest dir
  producedAt: string; // ISO-8601
  mtime: string;      // ISO-8601
  sizeBytes: number;
}

export interface WorkspaceManifest {
  schemaVersion: 1;
  workspaceId: string;
  createdAt: string;
  updatedAt: string;
  artifacts: ManifestArtifact[];
}

export interface ArtifactRef extends Omit<ManifestArtifact, "path"> {
  path: string; // absolute, resolved
  stale: boolean;
}

export interface NewArtifact {
  app: AppId;
  step: string;
  type: ArtifactType;
  absolutePath: string;
}

export const SCHEMA_VERSION = 1 as const;
```

- [ ] **Step 2: 타입체크**

```bash
npx tsc --noEmit
```

예상: 0 errors.

- [ ] **Step 3: 커밋**

```bash
git add src/lib/workspace/types.ts
git commit -m "v0.8.3.1: add workspace artifact manifest types"
```

---

## Task 2: 저수준 매니페스트 IO (TDD)

**파일:**
- 생성: `src/lib/workspace/manifest.ts`
- 테스트: `tests/workspace/manifest.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

```ts
// tests/workspace/manifest.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { readManifest, writeManifest, createEmptyManifest } from "@/lib/workspace/manifest";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

describe("manifest IO", () => {
  let dir: string;
  beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "ws-")); });

  it("returns null when manifest absent", async () => {
    expect(await readManifest(dir)).toBeNull();
  });

  it("writes and reads roundtrip", async () => {
    const m = createEmptyManifest();
    await writeManifest(dir, m);
    const back = await readManifest(dir);
    expect(back?.workspaceId).toBe(m.workspaceId);
    expect(back?.schemaVersion).toBe(1);
  });

  it("backs up corrupt manifest and returns null", async () => {
    writeFileSync(join(dir, ".kuma-workspace.json"), "{ not json");
    expect(await readManifest(dir)).toBeNull();
    const ls = (await import("node:fs/promises")).readdir;
    const files = await ls(dir);
    expect(files.some(f => f.startsWith(".kuma-workspace.json.bak-"))).toBe(true);
  });

  it("rejects schemaVersion mismatch by returning null", async () => {
    writeFileSync(
      join(dir, ".kuma-workspace.json"),
      JSON.stringify({ schemaVersion: 99, workspaceId: "x", artifacts: [] }),
    );
    expect(await readManifest(dir)).toBeNull();
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

```bash
pnpm vitest run tests/workspace/manifest.test.ts
```

예상: FAIL — module not found.

- [ ] **Step 3: 구현**

```ts
// src/lib/workspace/manifest.ts
import { readFile, writeFile, rename } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import type { WorkspaceManifest } from "./types";
import { SCHEMA_VERSION } from "./types";

const MANIFEST_FILE = ".kuma-workspace.json";

export function createEmptyManifest(): WorkspaceManifest {
  const now = new Date().toISOString();
  return {
    schemaVersion: SCHEMA_VERSION,
    workspaceId: randomUUID(),
    createdAt: now,
    updatedAt: now,
    artifacts: [],
  };
}

export async function readManifest(dir: string): Promise<WorkspaceManifest | null> {
  const path = join(dir, MANIFEST_FILE);
  if (!existsSync(path)) return null;
  try {
    const raw = await readFile(path, "utf-8");
    const parsed = JSON.parse(raw) as WorkspaceManifest;
    if (parsed.schemaVersion !== SCHEMA_VERSION) return null;
    return parsed;
  } catch {
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    await rename(path, `${path}.bak-${ts}`).catch(() => {});
    return null;
  }
}

export async function writeManifest(dir: string, m: WorkspaceManifest): Promise<void> {
  const path = join(dir, MANIFEST_FILE);
  m.updatedAt = new Date().toISOString();
  await writeFile(path, JSON.stringify(m, null, 2), "utf-8");
}

export const MANIFEST_FILENAME = MANIFEST_FILE;
```

- [ ] **Step 4: 실행 → 통과 확인**

```bash
pnpm vitest run tests/workspace/manifest.test.ts
```

예상: PASS (4 tests).

- [ ] **Step 5: 커밋**

```bash
git add src/lib/workspace/manifest.ts tests/workspace/manifest.test.ts
git commit -m "v0.8.3.1: workspace manifest IO with corruption backup"
```

> 주: 실제 런타임은 Tauri fs plugin 또는 sidecar 경유가 필요할 수 있음. 노드 fs로 테스트, 런타임 호출은 Task 3에서 어댑터 결정.

---

## Task 3: FS 어댑터 (Tauri ↔ Node)

**파일:**
- 생성: `src/lib/workspace/fs.ts`
- 테스트: `tests/workspace/fs.test.ts`

- [ ] **Step 1: 어댑터 인터페이스 결정**

기존 코드베이스에서 fs 추상화 검색:

```bash
grep -rn "tauri-apps/plugin-fs\|invoke.*fs" src/ | head
```

발견된 패턴 따름. 없으면 신규:

```ts
export interface WorkspaceFs {
  readTextFile(path: string): Promise<string | null>;
  writeTextFile(path: string, content: string): Promise<void>;
  rename(from: string, to: string): Promise<void>;
  stat(path: string): Promise<{ mtimeMs: number; size: number } | null>;
}
```

- [ ] **Step 2: Node 구현 + Tauri 구현 (분기)**

`vite.env`에 따라 적절한 구현 export. 환경별 mock은 `test-setup.ts`에서 처리.

- [ ] **Step 3: 테스트 + 커밋**

```bash
pnpm vitest run tests/workspace/fs.test.ts
git commit -m "v0.8.3.1: workspace fs adapter for tauri+node"
```

---

## Task 4: API 레이어 — registerArtifacts (TDD)

**파일:**
- 생성: `src/lib/workspace/api.ts`
- 테스트: `tests/workspace/api.test.ts`

- [ ] **Step 1: 실패 테스트**

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { openWorkspace, registerArtifacts, listArtifacts, getLatestArtifact } from "@/lib/workspace/api";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("workspace api", () => {
  let dir: string;
  beforeEach(async () => {
    dir = mkdtempSync(join(tmpdir(), "ws-api-"));
    await openWorkspace(dir);
  });

  it("registers and lists artifacts", async () => {
    const file = join(dir, "out.csv"); writeFileSync(file, "a,b\n");
    await registerArtifacts([{ app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: file }]);
    const list = await listArtifacts({ type: "evolvepro_csv" });
    expect(list).toHaveLength(1);
    expect(list[0].path).toBe(file);
    expect(list[0].stale).toBe(false);
  });

  it("upserts same (app,step,type) keeping only latest", async () => {
    const f1 = join(dir, "a.csv"); writeFileSync(f1, "1");
    const f2 = join(dir, "b.csv"); writeFileSync(f2, "2");
    await registerArtifacts([{ app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f1 }]);
    await registerArtifacts([{ app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f2 }]);
    const list = await listArtifacts();
    expect(list).toHaveLength(1);
    expect(list[0].path).toBe(f2);
  });

  it("getLatestArtifact returns null when none", async () => {
    expect(await getLatestArtifact("evolvepro_csv")).toBeNull();
  });

  it("marks stale when mtime changed since register", async () => {
    const f = join(dir, "c.csv"); writeFileSync(f, "x");
    await registerArtifacts([{ app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f }]);
    await new Promise(r => setTimeout(r, 20));
    writeFileSync(f, "y");
    const latest = await getLatestArtifact("evolvepro_csv");
    expect(latest?.stale).toBe(true);
  });

  it("removes artifact when file missing", async () => {
    const f = join(dir, "d.csv"); writeFileSync(f, "x");
    await registerArtifacts([{ app: "kuro", step: "diversity", type: "evolvepro_csv", absolutePath: f }]);
    (await import("node:fs/promises")).unlink(f);
    expect(await listArtifacts()).toHaveLength(0);
  });
});
```

- [ ] **Step 2: FAIL 확인**
- [ ] **Step 3: 구현 — `src/lib/workspace/api.ts`**

```ts
import { randomUUID } from "node:crypto";
import { stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { relative, resolve, isAbsolute } from "node:path";
import { readManifest, writeManifest, createEmptyManifest } from "./manifest";
import { emit } from "./events";
import type {
  AppId, ArtifactType, ArtifactRef, NewArtifact,
  ManifestArtifact, WorkspaceManifest,
} from "./types";

let activeDir: string | null = null;

export async function openWorkspace(dir: string): Promise<void> {
  if (!isAbsolute(dir)) throw new Error("workspace dir must be absolute");
  activeDir = dir;
  if (!(await readManifest(dir))) {
    await writeManifest(dir, createEmptyManifest());
  }
}

function requireDir(): string {
  if (!activeDir) throw new Error("workspace not opened");
  return activeDir;
}

function key(a: { app: AppId; step: string; type: ArtifactType }): string {
  return `${a.app}::${a.step}::${a.type}`;
}

async function loadOrCreate(dir: string): Promise<WorkspaceManifest> {
  return (await readManifest(dir)) ?? createEmptyManifest();
}

export async function registerArtifacts(items: NewArtifact[]): Promise<void> {
  const dir = requireDir();
  const m = await loadOrCreate(dir);
  const now = new Date().toISOString();
  for (const it of items) {
    const st = await stat(it.absolutePath);
    const rel = relative(dir, it.absolutePath);
    const entry: ManifestArtifact = {
      id: randomUUID(),
      app: it.app, step: it.step, type: it.type,
      path: rel,
      producedAt: now,
      mtime: new Date(st.mtimeMs).toISOString(),
      sizeBytes: st.size,
    };
    m.artifacts = m.artifacts.filter(a => key(a) !== key(entry));
    m.artifacts.push(entry);
  }
  await writeManifest(dir, m);
  emit("workspace:updated");
}

export async function listArtifacts(
  filter?: { app?: AppId; type?: ArtifactType }
): Promise<ArtifactRef[]> {
  const dir = requireDir();
  const m = await loadOrCreate(dir);
  const live: ManifestArtifact[] = [];
  const refs: ArtifactRef[] = [];
  let changed = false;
  for (const a of m.artifacts) {
    const abs = resolve(dir, a.path);
    if (!existsSync(abs)) { changed = true; continue; }
    if (filter?.app && a.app !== filter.app) { live.push(a); continue; }
    if (filter?.type && a.type !== filter.type) { live.push(a); continue; }
    const st = await stat(abs);
    const currentMtime = new Date(st.mtimeMs).toISOString();
    refs.push({ ...a, path: abs, stale: currentMtime !== a.mtime });
    live.push(a);
  }
  if (changed) {
    m.artifacts = live;
    await writeManifest(dir, m);
    emit("workspace:updated");
  }
  return refs;
}

export async function getLatestArtifact(type: ArtifactType): Promise<ArtifactRef | null> {
  const items = await listArtifacts({ type });
  if (items.length === 0) return null;
  return items.sort((a, b) => b.producedAt.localeCompare(a.producedAt))[0];
}

export async function clearWorkspace(appId: AppId): Promise<void> {
  const dir = requireDir();
  const m = await loadOrCreate(dir);
  const before = m.artifacts.length;
  m.artifacts = m.artifacts.filter(a => a.app !== appId);
  if (m.artifacts.length !== before) {
    await writeManifest(dir, m);
    emit("workspace:updated");
  }
}
```

Invariants:
- 모든 mutating 호출은 `writeManifest` 후 `emit("workspace:updated")`
- 경로 변환: 저장 시 `relative(dir, abs)`, 읽기 시 `resolve(dir, rel)`
- upsert key = `(app, step, type)` — 동일 키 최신 1건만 유지

- [ ] **Step 4: PASS** (5 tests)
- [ ] **Step 5: 커밋**

```bash
git commit -m "v0.8.3.1: workspace artifact registry api (register/list/getLatest/clear)"
```

---

## Task 5: useArtifact 훅 (TDD)

**파일:**
- 생성: `src/lib/workspace/useArtifact.ts`
- 테스트: `tests/workspace/useArtifact.test.tsx`

- [ ] **Step 1: 실패 테스트** — 매니페스트 mock 하고 hook이 prefill·stale·없음을 반환하는지 검증
- [ ] **Step 2: FAIL**
- [ ] **Step 3: 구현**

```ts
import { useEffect, useState } from "react";
import { getLatestArtifact } from "./api";
import { subscribe } from "./events";
import type { ArtifactRef, ArtifactType } from "./types";

export function useArtifact(type: ArtifactType): ArtifactRef | null {
  const [ref, setRef] = useState<ArtifactRef | null>(null);
  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      const v = await getLatestArtifact(type);
      if (alive) setRef(v);
    };
    refresh();
    const off = subscribe("workspace:updated", refresh);
    return () => { alive = false; off(); };
  }, [type]);
  return ref;
}
```

- [ ] **Step 4: PASS**
- [ ] **Step 5: 커밋**: `v0.8.3.1: useArtifact react hook with workspace event subscription`

---

## Task 6: ArtifactBadge UI

**파일:**
- 생성: `src/components/widgets/ArtifactBadge.tsx`
- 테스트: `tests/components/ArtifactBadge.test.tsx`

- [ ] **Step 1-4: TDD**

```tsx
export function ArtifactBadge({ artifact }: { artifact: ArtifactRef }) {
  const variant = artifact.stale ? "warning" : "secondary";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant={variant}>
          {t("artifact.badge.detected", { step: artifact.step })}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        <div>{artifact.path}</div>
        {artifact.stale && <div>{t("artifact.badge.staleHint")}</div>}
      </TooltipContent>
    </Tooltip>
  );
}
```

- [ ] **Step 5: 커밋**: `v0.8.3.1: ArtifactBadge widget with stale state`

---

## Task 7: KURO export slice 연동

**파일:**
- 수정: `src/store/slices/exportSlice.ts` (L339-380 `exportExcel`, L496-525 `exportFasta` 등)
- 테스트: `src/store/slices/exportSlice.test.ts` 확장

- [ ] **Step 1: 실패 테스트** — `exportExcel` 호출 후 `getLatestArtifact("sdm_primer_xlsx")`가 해당 파일 반환
- [ ] **Step 2: FAIL**
- [ ] **Step 3: 구현** — export 성공 분기에서 `registerArtifacts([{ app: "kuro", step: "design", type: "sdm_primer_xlsx", absolutePath: filepath }])`
- [ ] **Step 4: PASS**
- [ ] **Step 5: 커밋**: `v0.8.3.1: kuro export slice registers artifacts to workspace manifest`

---

## Task 8: KURO EvolveproCsv 입력 prefill

**파일:**
- 수정: `src/components/panels/...` (실 파일은 grep `evolveproCsvPath` 사용처)
- 테스트: `tests/components/evolveproCsvPrefill.test.tsx`

- [ ] **Step 1-5: 표준 TDD 사이클**

**우선순위 (verifier 지적 반영):**
1. 사용자 수동 override (`userOverridden === true`) → 가장 강함, prefill 차단
2. workspace artifact (`useArtifact("evolvepro_csv")`) → 최우선 소스
3. 기존 zustand persist 상태 `evolveproCsvPath` → fallback (앱 재시작 시 마지막 사용 경로 유지)
4. 빈값

```tsx
const artifact = useArtifact("evolvepro_csv");
const [userOverridden, setUserOverridden] = useState(false);
const evolveproCsvPath = useAppStore(s => s.evolveproCsvPath);
const setEvolveproCsvPath = useAppStore(s => s.setEvolveproCsvPath);

useEffect(() => {
  if (userOverridden) return;
  if (artifact && artifact.path !== evolveproCsvPath) {
    setEvolveproCsvPath(artifact.path);  // 매니페스트가 persist 보다 우선
  }
}, [artifact, userOverridden, evolveproCsvPath, setEvolveproCsvPath]);

const onBrowse = () => { setUserOverridden(true); /* open dialog ... */ };
```

UI: `artifact && !userOverridden` 조건으로 `<ArtifactBadge artifact={artifact} />` 렌더. `userOverridden` 일 때는 일반 경로 텍스트만 표시.

- [ ] **커밋**: `v0.8.3.2: kuro evolvepro csv input auto-prefill from workspace`

---

## Task 9: MAME export slice 연동

**파일:**
- 수정: `src/store/mame/slices/exportSlice.ts`
- 테스트: `tests/mame/exportSlice.test.ts`

- [ ] **Step 1-5: TDD** — `exportExcel` 후 `registerArtifacts([{ app: "mame", step: "analysis", type: ..., absolutePath: path }])` 검증
- [ ] **커밋**: `v0.8.3.3: mame export slice registers artifacts`

---

## Task 10: MAME slice reset() 메서드

**파일:**
- 수정: `src/store/mame/slices/inputSlice.ts`, `analysisSlice.ts`, `phaseSlice.ts`, `exportSlice.ts`
- 수정: `src/store/mame/mameAppStore.ts` — `resetAll()` 추가

- [ ] **Step 0: 사전 audit (verifier 지적 반영)**

```bash
grep -n "reset\|clearResults\|initialState\|persist\|localStorage" \
  src/store/mame/slices/{inputSlice,analysisSlice,phaseSlice,exportSlice}.ts
```

확인 사항:
- `phaseSlice` 가 `localStorage` 또는 zustand `persist` 미들웨어로 영속화되는가? → 그렇다면 `reset()` 은 in-memory state 만 초기화하고 영속 키는 별도 `clearPersistedPhase()` 헬퍼로 분리.
- `analysisSlice` 에 이미 `clearResults` 류가 있으면 새 `reset()` 은 그것을 호출하고 입력 상태까지 함께 초기화.
- `inputSlice` 에 file handle / blob URL revoke 필요 항목 있으면 reset 내부에서 정리.

audit 결과를 Task 10 본문 위에 한 단락으로 기록한 뒤 Step 1로 진행.

- [ ] **Step 1: 슬라이스 reset 테스트** — 각 슬라이스 변경 후 `reset()` 호출 시 `initialState` 와 deep-equal 인지
- [ ] **Step 2: FAIL**
- [ ] **Step 3: 각 슬라이스에 `reset: () => set(initialState)` 추가** (persist 슬라이스는 in-memory 만)
- [ ] **Step 4: `mameAppStore.resetAll()` 구현** — 각 슬라이스 reset aggregate + persist 슬라이스의 영속 키 명시적 삭제
- [ ] **Step 5: 커밋**: `v0.8.3.4: mame slice reset methods and resetAll aggregator`

---

## Task 11: MAME Clear All 다이얼로그 + 버튼

**파일:**
- 생성: `src/components/mame/dialogs/MameClearAllDialog.tsx`
- 수정: `src/components/mame/layout/MameAppLayout.tsx`
- 테스트: `tests/components/MameClearAll.test.tsx`

- [ ] **Step 1: 실패 UI 테스트**

```tsx
it("Clear All button opens dialog, confirms, resets store and clears workspace artifacts", async () => {
  // setup MAME store with sample data + register MAME artifact
  // render layout
  // click "Clear All"
  // confirm dialog
  // expect mame store reset + listArtifacts({app:"mame"}) empty + kuro artifact preserved
});
```

- [ ] **Step 2: FAIL**
- [ ] **Step 3: 구현**

```tsx
export function MameClearAllDialog({ open, onOpenChange }) {
  const onConfirm = async () => {
    useMameAppStore.getState().resetAll();
    await clearWorkspace("mame");
    onOpenChange(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>{t("mame.clearAll.title")}</DialogTitle>
        <DialogDescription>{t("mame.clearAll.description")}</DialogDescription>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <Button variant="destructive" onClick={onConfirm}>{t("common.clearAll")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

`MameAppLayout` 상단 우측에 버튼 추가, KURO `AppLayout` 의 Clear All 배치(L300-311)와 동일 패턴.

- [ ] **Step 4: PASS**
- [ ] **Step 5: 커밋**: `v0.8.3.4: mame clear all button and dialog`

---

## Task 12: KURO Clear All에 clearWorkspace 통합

**파일:**
- 수정: `src/components/layout/AppLayout.tsx` (L234 인접)
- 테스트: `tests/components/KuroClearAll.test.tsx`

- [ ] **Step 1-5: TDD** — KURO Clear All 클릭 후 KURO artifact만 매니페스트에서 제거, MAME artifact 보존

```ts
useAppStore.getState().resetAll();
await clearWorkspace("kuro");
```

- [ ] **커밋**: `v0.8.3.4: kuro clear all clears workspace kuro artifacts`

---

## Task 13: i18n locale 키

**파일:**
- 수정: `src/locales/en/common.json`, `src/locales/ko/common.json`, 기타 활성 locale

- [ ] **Step 1: 신규 키 추가**

```json
{
  "artifact": {
    "badge": {
      "detected": "Step {{step}} output auto-detected",
      "staleHint": "File changed since export"
    }
  },
  "mame": {
    "clearAll": {
      "title": "Clear All",
      "description": "Resets the MAME workspace. Exported files remain on disk."
    }
  }
}
```

KO:
```json
{
  "artifact": {
    "badge": {
      "detected": "Step {{step}} 출력 자동 감지",
      "staleHint": "Export 이후 파일이 변경됨"
    }
  },
  "mame": {
    "clearAll": {
      "title": "Clear All",
      "description": "MAME 워크스페이스를 초기화합니다. 출력 파일은 디스크에 남습니다."
    }
  }
}
```

- [ ] **Step 2: i18n 가드 통과**

```bash
pnpm i18n:guard 2>/dev/null || pnpm test -- i18n
```

- [ ] **Step 3: 커밋**: `v0.8.3.5: i18n keys for artifact badge and mame clear all`

---

## Task 14: cross-layer-sync 그룹 등록

**파일:**
- 수정: `.cross-layer-sync.json`

- [ ] **Step 1: 신규 그룹 추가**

```json
{
  "id": "workspace-artifact-registry",
  "files": [
    "src/lib/workspace/types.ts",
    "src/lib/workspace/api.ts",
    "src/store/slices/exportSlice.ts",
    "src/store/mame/slices/exportSlice.ts"
  ],
  "symbols": ["registerArtifacts", "ArtifactType", "AppId"],
  "note": "Export slices must call registerArtifacts using ArtifactType enum",
  "severity": "warning"
}
```

- [ ] **Step 2: `pnpm sync:check` 통과**
- [ ] **Step 3: 커밋**: `v0.8.3.5: cross-layer-sync group for workspace artifact registry`

---

## Task 15: 통합 E2E 시나리오 테스트

**파일:**
- 생성: `tests/workspace/handoff.e2e.test.ts`

- [ ] **Step 1: 시나리오 테스트**

```ts
it("KURO export -> KURO design input auto-prefill round trip", async () => {
  // 1. open workspace dir
  // 2. mock-render diversity panel, set evolveproCsvPath via simulated Export
  // 3. unmount design panel, remount
  // 4. expect evolveproCsvPath prefilled with badge visible
});

it("MAME Clear All preserves KURO artifacts", async () => {
  // register kuro + mame artifacts
  // call clearWorkspace("mame")
  // listArtifacts has only kuro item
});
```

- [ ] **Step 2-4: PASS**
- [ ] **Step 5: 커밋**: `v0.8.3.5: e2e handoff scenarios for workspace artifact pipeline`

---

## Task 16: 최종 검증 + 문서

- [ ] **Step 1: 전체 테스트**

```bash
pnpm test --run
pnpm vitest run
npx tsc --noEmit
cd src-tauri && cargo check
pnpm sync:check
```

예상: 0 failures.

- [ ] **Step 2: UPDATE-NOTES 갱신**

`UPDATE-NOTES.md` / `UPDATE-NOTES.ko.md`에 v0.8.3 항목 추가:
- "Workspace artifact handoff: previous-step exports auto-prefill next-step inputs"
- "MAME Clear All button"

- [ ] **Step 3: README 갱신**

`docs/` 또는 README의 workflow 섹션에 매니페스트 동작 기재.

- [ ] **Step 4: codex review 실행**

```bash
/codex:review
```

예상: `.codex-review-passed` 생성.

- [ ] **Step 5: 최종 커밋 + 푸시**

```bash
git add -A
git commit -m "v0.8.3.0: workspace artifact handoff feature complete"
git push -u origin feat/workspace-artifact-handoff
```

---

## 의존성 그래프

```
T0 (worktree) → T1 (types) → T2 (manifest IO) → T3 (fs adapter) → T4 (api)
                                                                   ├→ T5 (useArtifact)
                                                                   ├→ T7 (kuro export)
                                                                   ├→ T9 (mame export)
                                                                   └→ T10 (mame reset)
                                                                         │
                                                                         ├→ T6 (badge) → T8 (kuro prefill UI)
                                                                         ├→ T11 (mame clear all)
                                                                         └→ T12 (kuro clear all)
                            T13 (i18n) → T14 (sync) → T15 (e2e) → T16 (verify)
```

병렬 가능: T7/T9, T11/T12, T13/T14.

---

## 리스크·완화

| 리스크 | 완화 |
|---|---|
| Tauri fs plugin 사용 패턴 미확정 | Task 3에서 기존 패턴 grep 후 결정. 없으면 node fs로 시작하고 sidecar RPC 경유로 후속 마이그레이션 |
| MAME 슬라이스 분리 패턴이 KURO와 다름 | Task 10 시작 전 `src/store/mame/slices/*.ts` 전체 읽고 reset 패턴 매칭 |
| 매니페스트 위치 (Export 폴더 vs 워크스페이스 루트) 사용자 혼란 | 첫 Export 시 토스트로 "워크스페이스 매니페스트 생성됨: <path>" 알림 |
| 기존 `evolveproCsvPath` 영구 저장과 충돌 | Task 8 prefill 로직에서 매니페스트 > 영구저장 > 빈값 우선순위 |
