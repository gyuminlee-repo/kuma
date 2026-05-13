# Workspace Artifact Handoff & MAME Clear All

- Date: 2026-05-13
- Status: Draft — pending user review
- Scope: KURO + MAME (primerbench는 미래 확장)

## 1. 목적

다단계 워크플로우(예: KURO Diversity → Design, MAME consensus → 후속 단계)에서 이전 단계가 생성한 파일을 다음 단계가 별도 업로드 없이 자동 인지하여 경로 입력란을 채운다. 사용자 관점에서 "업로드한 것과 동일한 효과"를 제공한다.

추가로 MAME에 KURO와 동일한 Clear All 버튼을 도입하여 워크스페이스 초기화를 통일된 시맨틱으로 처리한다.

## 2. 비목표

- 단계 의존성 그래프(DAG) 정식화
- artifact 버전 히스토리 보존(최신 1개만 유지)
- 외부 프로세스 간 동시 매니페스트 쓰기 락
- 자동 단계 진행 트리거(사용자는 여전히 명시적으로 다음 단계 진입)

## 3. 아키텍처

```
[Step N UI] ── Export All ──┐
                            ├─► 파일 쓰기 (기존 동작 유지)
                            └─► .kuma-workspace.json upsert
                                  artifacts[(app, step, type)] = {path, mtime, ...}

[Step N+1 UI mount] ── useArtifact(type)
                       └─► 매니페스트 lookup → prefill + badge

[Clear All] ── clearWorkspace(appId)
                ├─► slice.reset() (각 앱)
                └─► manifest에서 app 매칭 artifact 제거
```

## 4. 매니페스트

### 4.1 위치

- 사용자가 Export 시 선택한 출력 폴더의 `.kuma-workspace.json`
- 첫 Export 시 자동 생성. 이후 같은 폴더 안 Export·Clear All은 동일 파일을 갱신.
- 앱 시작 시 `~/.kuma/recent.json`에서 최근 워크스페이스 경로 후보를 제시. 사용자가 "워크스페이스 열기"로 활성화.

### 4.2 스키마 (v1)

```json
{
  "schemaVersion": 1,
  "workspaceId": "<uuid>",
  "createdAt": "ISO-8601",
  "updatedAt": "ISO-8601",
  "artifacts": [
    {
      "id": "<uuid>",
      "app": "kuro" | "mame" | "primerbench",
      "step": "diversity" | "design" | "consensus" | "...",
      "type": "evolvepro_csv" | "sdm_primer_xlsx" | "mame_consensus_fasta",
      "path": "<상대 경로 (매니페스트 기준)>",
      "producedAt": "ISO-8601",
      "mtime": "ISO-8601",
      "sizeBytes": 0
    }
  ]
}
```

- `type` enum은 처음에 실제 export 결과물만 정의. 미래용 예약 타입 추가 금지(YAGNI).
- `path`는 상대 경로로 저장하여 폴더 이동에 강건.
- 같은 `(app, step, type)` 조합은 최신 1개만 유지(덮어쓰기).

## 5. 컴포넌트

### 5.1 `src/lib/workspace.ts`

```ts
type AppId = "kuro" | "mame" | "primerbench";
type ArtifactType = "evolvepro_csv" | "sdm_primer_xlsx" | "mame_consensus_fasta";

interface ArtifactRef {
  id: string;
  app: AppId;
  step: string;
  type: ArtifactType;
  path: string;       // absolute, resolved from manifest dir
  producedAt: string;
  mtime: string;
  sizeBytes: number;
  stale: boolean;     // 현재 mtime != 기록 mtime
}

export function registerArtifacts(items: NewArtifact[]): Promise<void>;
export function listArtifacts(filter?: {app?: AppId; type?: ArtifactType}): Promise<ArtifactRef[]>;
export function getLatestArtifact(type: ArtifactType): Promise<ArtifactRef | null>;
export function clearWorkspace(appId: AppId): Promise<void>;
export function openWorkspace(dir: string): Promise<void>;
```

### 5.2 React 훅

```ts
export function useArtifact(type: ArtifactType): ArtifactRef | null;
```

- 입력 컴포넌트 mount 시 호출. 매니페스트 변경 이벤트(`workspace:updated`) 구독.
- 사용자가 수동 경로를 입력했으면 prefill 건너뜀.

### 5.3 Export 훅 연동

- `exportSlice.exportAll()` 응답의 파일 목록을 `registerArtifacts(...)`로 변환·등록.
- 사이드카 응답에 이미 `outputPath` 등이 있으므로 별도 RPC 추가 불필요. 프론트엔드 측 후처리만.

### 5.4 UI — Prefill Badge

- 입력 필드(경로 텍스트 또는 Browse 컴포넌트) 우측에 shadcn `<Badge variant="secondary">` 표시
- 텍스트: `Step <step> 출력 자동 감지`
- Hover 시 툴팁에 전체 경로 표시
- Stale 시 `variant="warning"` + 툴팁 "Export 이후 파일이 변경됨"
- 파일 부재 시 prefill 생략 + 해당 artifact 매니페스트에서 제거

### 5.5 Clear All — MAME 신규

- 위치: MAME 메인 페이지 상단 우측 (KURO와 동일 관례)
- 컴포넌트: shadcn `<Button variant="ghost">` 빨간 텍스트
- 동작: 확인 다이얼로그 → `clearWorkspace("mame")` → 각 MAME 슬라이스 `reset()` 호출
- 진행 중 잡이 있으면 잡 취소 확인을 우선 표시 후 진행
- 다이얼로그 문구: "MAME 워크스페이스를 초기화합니다. 출력 파일 자체는 디스크에 남습니다."

### 5.6 Clear All — KURO 리팩토링

- 기존 KURO Clear All의 슬라이스 reset 로직 유지
- 추가로 `clearWorkspace("kuro")` 호출하여 매니페스트의 KURO artifact 정리
- 공통 유틸로 추출하여 중복 제거

## 6. 에러 처리

| 시나리오 | 처리 |
|---|---|
| 매니페스트 JSON 파싱 실패 | `.kuma-workspace.json.bak-<ts>`로 백업 후 신규 생성. 비차단 토스트로 알림 |
| `schemaVersion` 불일치 | 마이그레이션 함수 적용. 현재 v1만 존재 |
| 등록된 path 부재 | listArtifacts 시 자동 제거. prefill 생략 |
| 등록 중 디스크 오류 | Export는 성공 처리, manifest 갱신 실패만 로그 + 토스트 |
| 동시 쓰기 | 단일 프로세스 내 직렬화. 멀티 프로세스는 last-write-wins(허용) |

## 7. 마이그레이션

- 기존 KURO 사용자: 매니페스트 없음 → 첫 Export부터 자동 생성. 기존 동작에 영향 없음.
- 기존 EVOLVEpro CSV 로드 경로(`evolveproCsvPath` 영구 저장)는 유지. prefill은 매니페스트 우선, fallback으로 기존 경로 사용.

## 8. 테스트

- `tests/workspace.test.ts`: register / list / getLatest / clear / stale 감지
- `tests/clearWorkspace.test.ts`: app 격리(KURO Clear → MAME artifact 보존)
- `tests/useArtifact.test.tsx`: prefill / 수동 override / stale 배지 / 파일 부재 정리
- `tests/mame-clear-all.test.tsx`: 다이얼로그 → reset → manifest 정리 흐름

## 9. 첫 적용 대상 (이번 마일스톤)

1. KURO Diversity → Design 단계 전환 (`evolvepro_csv`)
2. MAME Clear All 버튼 + 기본 매니페스트 인프라

이후 마일스톤에서 MAME consensus → 후속 단계, KURO Design → Export 등 점진 확장.

## 10. 작문·코드 규칙 준수

- 절대 경로 하드코딩 금지 — manifest 자체가 상대 경로 저장
- 상태 메시지·라벨은 i18n locale 키 경유
- 과학 용어(EVOLVEpro, CDS 등)는 영문 유지
- TypeScript: `as any` 금지, 명시 타입
- 커밋 형식: `vX.X.X: workspace artifact handoff + mame clear all`
