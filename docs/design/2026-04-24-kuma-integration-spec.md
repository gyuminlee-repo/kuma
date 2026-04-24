# kuma — KURO + mame 통합 앱 설계 스펙

**작성일**: 2026-04-24
**저자**: brainstorming 세션 결과
**상태**: 설계 완료, 구현 계획 대기

---

## 1. 배경과 목적

kuro(primer 설계)와 mame(Nanopore NGS 판정)는 동일한 실험 파이프라인의 연속된 두 단계다.

- 현재: 두 앱이 별개 Tauri 데스크톱 앱으로 배포. 사용자는 kuro에서 `expected_mutations.xlsx`를 수동 export → 수 주 뒤 실험/시퀀싱 완료 → mame에 수동 업로드.
- 마찰: 어떤 kuro export가 어떤 mame 분석에 대응하는지 사용자가 직접 관리해야 함. 프로젝트 수가 늘수록 파일 관리 부담 증가.
- 목표: 두 도구를 한 앱(`kuma`)으로 통합해 **시간차를 가로지르는 프로젝트 연속성**을 제공.

두 앱 모두 Tauri v2 + React 19 + Python sidecar로 스택이 동일해 통합 비용이 낮다.

## 2. 범위

### In scope
- 새 private repo `kuma` 생성 (kuro 기반으로 이식)
- 단일 Tauri 앱, 상단 탭 UI로 `Kuro`(primer 설계) / `Mame`(NGS 분석) 전환
- 프로젝트 폴더 기반 워크플로: 설계→분석 세션 간 연속성
- 기존 kuro workspace(`.kuro.json`) 및 mame 입력 포맷 호환 (scratch 모드)
- xlsx 메타 시그니처로 파일 출처 자동 인식
- 공유 Python 유틸 점진 추출

### Out of scope
- 실시간 데이터 브릿지 (사용 패턴상 불필요, 시간차 수 주)
- 클라우드 동기화/협업 기능 (사용자가 root 폴더를 Dropbox에 둘 수는 있음)
- kuro/mame 기능 자체의 변경 또는 리팩토링
- 고양이 마스코트/서사적 UX (이름만 코드네임으로 차용)
- 웹/모바일 버전

## 3. 핵심 설계 결정

### 3.1 Repository
- 새 private repo `kuma` 생성
- 베이스: kuro repo 복제(히스토리 보존), mame는 `apps/mame/`로 이식
- 기존 kuro/mame repo는 README에 통합 안내 추가 후 archive

### 3.2 UX 방향
- **제품명 `kuma` 전면 노출**: 앱 타이틀바·윈도우 제목·시작 화면 로고·About 다이얼로그 모두 `kuma`. kuro + mame 합성어임이 제품 아이덴티티.
- **탭 라벨은 `Kuro` / `Mame`**: 기능명(Design/Analyze) 대신 두 서브도구의 이름을 그대로 탭 라벨로 사용. 기존 kuro·mame 사용자가 즉시 인식 가능.
- **담백하게**: 마스코트 일러스트·고양이 이모지·"두 고양이가 친하게 지내요" 같은 서사 카피는 사용하지 않음. 이름만 쓰고 장식은 배제.
- 각 탭 내부 UI는 기존 kuro/mame를 거의 그대로 유지 (학습·이식 비용 최소)
- 스크린샷 상단 형태: `kuma` 브랜드 + `Kuro` / `Mame` 탭 → 논문·랩미팅에서도 직관적

### 3.3 Python sidecar 전략
- **두 sidecar 유지 + lazy-spawn** (탭 활성화 시 해당 sidecar만 구동)
- 공유 유틸(config 경로, 로깅, 에러 포맷)은 `kuma_core.shared`로 점진 추출
- 완전 통합(단일 프로세스)은 당분간 미채택. 근거:
  - kuro/mame 간 실시간 데이터 공유 없음 (시간차 커서 in-memory 이점 無)
  - 의존성 충돌 리스크(primer3 + pysam + Bio + numpy 동시 번들)
  - PyInstaller 바이너리 2개 유지가 통합 1개보다 디버깅 단순

### 3.4 프로젝트 모델
- **Projects root 1회 설정**(Zotero 패턴): 첫 실행 시 `~/Documents/kuma/` 기본값 제안, Settings에서 변경 가능
- 이후 모든 프로젝트는 root 하위에 자동 생성, 경로 다이얼로그 반복 안 함
- scratch 모드(`.kuro.json` 단일 파일 저장·로드) 병존 — 기존 kuro 사용자 호환

### 3.5 버전 전략
- kuma v0.1.0부터 새로 시작
- 릴리스 노트에 kuro·mame 계보 명시
- 기존 repo에는 "kuma로 통합되었습니다" 안내

## 4. 프로젝트 파일 구조

### 4.1 폴더 레이아웃
```
{projects_root}/
└── Sample_42/
    ├── kuma.project.json          ← 프로젝트 메타
    ├── design/
    │   ├── workspace.kuro.json    ← 기존 KURO workspace 포맷 그대로
    │   └── expected_mutations.xlsx ← __kuma_meta__ 시트 포함
    └── analysis/
        ├── consensus/             ← 사용자가 드롭한 FASTA
        └── verdict.xlsx           ← mame 결과
```

### 4.2 `kuma.project.json` 스키마 (schema v1)
```json
{
  "schema": 1,
  "project_id": "uuid-v4",
  "name": "Sample_42",
  "created_at": "2026-04-24T12:52+09:00",
  "updated_at": "2026-04-24T12:52+09:00",
  "stage": "design_complete",
  "kuro_workspace": "design/workspace.kuro.json",
  "expected_mutations": "design/expected_mutations.xlsx",
  "analysis_input": "analysis/consensus/",
  "analysis_output": "analysis/verdict.xlsx",
  "last_opened_tab": "kuro"
}
```

- `stage` 허용값: `draft` | `design_complete` | `analyzing` | `done`
- 파일 경로는 프로젝트 폴더 기준 상대 경로
- 필드가 가리키는 파일이 없어도 정상(아직 생성 전일 수 있음)

### 4.3 xlsx 메타 시그니처
KURO가 `expected_mutations.xlsx` export 시 숨김 시트 `__kuma_meta__` 추가:

| key | value |
|---|---|
| project_id | uuid-v4 |
| kuma_version | 0.1.0 |
| kuro_module_version | 0.x.y |
| exported_at | ISO 8601 |

- mame가 xlsx 드롭 시 이 시트 읽어서 `project_id` 매칭
- 매칭 프로젝트 발견 시 "Sample_42 프로젝트로 로드하시겠어요?" 제안
- 프로젝트 폴더 없어도 (파일만 옮겨다닌 경우) 출처는 인식 가능

### 4.4 앱 설정 파일
`~/.kuma/config.json`:
```json
{
  "projects_root": "/Users/.../Documents/kuma",
  "recent_projects": [
    {"path": "...", "name": "Sample_42", "last_opened": "..."}
  ]
}
```

## 5. UI 구조

### 5.1 시작 화면 (앱 실행 시)
- `+ 새 프로젝트` 버튼 → 이름 입력 → `{root}/{name}/` 생성 → `Kuro` 탭 자동 오픈
- 최근 프로젝트 리스트 (root 스캔 + recent.json 병합)
  - 각 항목: 이름 · 단계 뱃지 · 마지막 열람 날짜
- `파일 열기` (scratch 모드, 단일 `.kuro.json` 로드)
- Settings 진입점 (projects root 경로 변경)

### 5.2 메인 화면
- 상단 탭바: `Kuro` / `Mame` (현재 프로젝트가 열려있을 때)
- 우상단: 현재 프로젝트 이름, 단계 뱃지, 저장 상태
- 탭 내부는 기존 kuro/mame UI 그대로

### 5.3 온보딩 (첫 실행 1회)
- "kuma는 프로젝트를 어디에 저장할까요?"
- 기본값 `~/Documents/kuma/` 제안, 변경 가능
- 결정 후 `~/.kuma/config.json` 생성

## 6. 아키텍처

```
+-----------------------------+
| Tauri shell (React + Vite)  |
| ├── 시작 화면 (프로젝트 리스트) |
| ├── Kuro 탭 (기존 KURO UI)    |
| └── Mame 탭 (기존 mame UI)    |
+-----------------------------+
         ↓ JSON-RPC (lazy)
+------------------+  +------------------+
| kuro sidecar     |  | mame sidecar     |
| (python-core)    |  | (python-core)    |
+------------------+  +------------------+
         ↓                      ↓
  (공유) kuma_core.shared: config, 로깅, 프로젝트 경로 해석

+-----------------------------+
| Project Layer (Tauri Rust)  |
| ├── project CRUD             |
| ├── xlsx 메타 read/write     |
| └── recent/root config       |
+-----------------------------+
```

- Project Layer는 Rust 쪽에 둬서 두 sidecar 어느 쪽도 프로젝트 모델을 몰라도 되게 함
- sidecar는 "이 경로의 파일 읽어/써" 수준의 I/O만 지시받음

## 7. 이식 작업 순서 (Kuro-first)

각 단계 끝마다 앱이 돌아가는 상태를 유지한다.

1. **Repo 세팅** (0.5일)
   - kuro repo를 새 private repo `kuma`로 push (히스토리 보존)
   - 패키지명·제품명·아이콘 일괄 변경 (`kuro` → `kuma`, 메인 탭은 `Kuro`)
   - 빌드 통과 확인

2. **프로젝트 레이어 추가** (1일)
   - Rust 측: `kuma.project.json` CRUD, projects root 설정, recent list
   - 시작 화면 컴포넌트 (새 프로젝트 / 최근 / 파일 열기)
   - 온보딩 다이얼로그
   - 기존 KURO workspace 저장·로드 로직은 그대로 유지 (scratch 모드)

3. **Mame 이식** (1일)
   - mame repo 전체를 `apps/mame/`로 복사 (히스토리는 git subtree 또는 단순 복사 후 CHANGELOG에 계보 기록)
   - `python-core/`는 `kuma_core/mame/`로 재배치
   - PyInstaller sidecar 빌드 설정 통합 (바이너리 2개)
   - Mame UI를 React 라우트로 붙임 (아직 탭 없이 독립 접근)
   - 빌드 통과 확인

4. **탭 UI 통합** (0.5일)
   - 상단 탭바 추가 (`Kuro` / `Mame`)
   - 프로젝트 열려있을 때만 탭 노출
   - 탭 전환 시 sidecar lazy-spawn + 이전 상태 유지
   - xlsx 메타 시그니처 read/write 추가

5. **Shared 유틸 추출** (0.5-1일)
   - `kuma_core.shared` 패키지 생성
   - 중복 config 경로 해석, 로깅, 에러 포맷 이동
   - 양쪽에서 import 전환
   - 테스트 통과 확인

**총 작업량**: 3.5-4일 (예측).

## 8. 호환성과 마이그레이션

- **기존 `.kuro.json` 파일**: kuma의 scratch 모드에서 그대로 로드 가능
- **기존 mame 입력 xlsx** (메타 시트 없음): 드롭하면 경고 없이 scratch 모드로 분석 (기존 동작과 동일)
- **기존 kuro/mame repo**: README에 "kuma로 통합됨" 배너 추가 후 archive (삭제 X)

## 9. 에러 처리와 엣지 케이스

- **Projects root가 사라짐/이동**: 앱 시작 시 존재 확인. 없으면 재설정 다이얼로그.
- **동명 프로젝트 생성**: 자동 suffix (`Sample_42`, `Sample_42_2`)
- **잘못된 `kuma.project.json`**: schema 검증 실패 시 "손상된 프로젝트 파일" 표시, 무시하고 앱 기동 계속
- **xlsx 메타 시트 있으나 해당 project_id 프로젝트 없음**: "출처 프로젝트를 찾을 수 없습니다. scratch 모드로 진행할까요?" 다이얼로그
- **schema 버전 미래값**: "이 프로젝트는 최신 kuma에서 만들어졌습니다. 앱을 업데이트하세요." 메시지
- **탭 전환 중 sidecar 스폰 실패**: 해당 탭 영역에 에러 메시지, 다른 탭 작업은 영향 없음
- **양쪽 sidecar 동시 활성화 시 메모리 압박**: 미사용 탭 sidecar를 N분 후 자동 종료 (정책 미정, v0.2 고려)

## 10. 테스트 전략

- **단위**: 프로젝트 파일 CRUD, xlsx 메타 read/write, projects root 경로 해석
- **통합**: 시나리오 "새 프로젝트 → KURO 설계 → xlsx 생성 → 앱 재시작 → mame 탭에서 해당 프로젝트 열기 → scratch 드롭으로도 project_id 인식"
- **호환성**: 기존 `.kuro.json` 로드, 메타 시트 없는 xlsx 드롭
- **회귀**: 기존 kuro/mame 자체 테스트 슈트 (`tests/`, `vitest`, `pytest`) 통과 유지

## 11. 릴리스

- kuma v0.1.0: 위 1-5 단계 완료 시점
- 릴리스 노트 구조:
  - 상단: "kuro v0.x, mame v0.x를 통합한 첫 릴리스입니다"
  - 변경사항: 프로젝트 레이어 추가, 탭 UI
  - 마이그레이션 가이드: 기존 사용자가 무엇을 해야 하는지
- private repo이므로 릴리스도 private

## 12. 구현 상세 (verifier 리뷰 반영)

### 12.1 최종 디렉토리 구조
```
kuma/
├── src/                             ← React 앱 (기존 kuro/src 베이스)
│   ├── App.tsx                      ← 탭 라우팅
│   ├── screens/
│   │   ├── Home.tsx                 ← 시작 화면
│   │   ├── KuroTab.tsx              ← 기존 kuro UI wrapping
│   │   └── MameTab.tsx              ← 기존 mame src/App.tsx wrapping
│   ├── lib/
│   │   ├── ipc.ts                   ← 통합 IPC (아래 12.3)
│   │   ├── project.ts               ← Rust project CRUD 호출 래퍼
│   │   └── ipc-kuro/, ipc-mame/     ← 기존 각 앱의 ipc 호출 모듈 (이름 분리)
├── src-tauri/                       ← Rust shell (기존 kuro/src-tauri 베이스)
│   └── src/
│       ├── sidecar.rs               ← 이중 sidecar 관리 (아래 12.3)
│       ├── project.rs               ← project CRUD commands
│       └── xlsx_meta.rs             ← __kuma_meta__ read/write
├── python-core/
│   ├── build_sidecar.py             ← 두 sidecar 순차 빌드 (--target kuro|mame|all)
│   ├── kuro-sidecar.spec            ← 기존 유지
│   ├── mame-sidecar.spec            ← 기존 유지
│   ├── sidecar_main_kuro.py         ← 기존 kuro/python-core/sidecar_main.py
│   ├── sidecar_main_mame.py         ← 기존 mame/python-core/sidecar_main.py
│   └── shared/                      ← 공유 유틸 (Step 5에서 채움)
├── kuma_core/                       ← 통합 Python 패키지 루트
│   ├── kuro/                        ← 기존 kuro/kuro/ 이동
│   ├── mame/                        ← 기존 mame/src/mame/ 이동
│   └── shared/                      ← config 경로, 로깅, 에러 포맷
└── pyproject.toml                   ← 두 패키지 + shared 등록
```

**핵심 결정**:
- Python 패키지는 `kuma_core.kuro`, `kuma_core.mame`로 네임스페이스 통일 (기존 `kuro`, `mame` → 전역 find/replace)
- sidecar entry point는 두 파일 유지, PyInstaller spec도 두 개 유지 (빌드만 통합 스크립트)

### 12.2 Sidecar 생명주기 관리 (Rust 소유)
- **소유자**: Tauri Rust 쪽(`src-tauri/src/sidecar.rs`)이 두 sidecar 프로세스 핸들 소유
- **spawn 시점**: 해당 탭 첫 활성화 시. React가 Tauri command `activate_sidecar(kind: 'kuro' | 'mame')` 호출
- **kill 시점**: 
  - v0.1: 앱 종료 시에만 kill. 탭 전환으론 kill 안 함 (단순성 우선)
  - v0.2: idle 타이머 기반 종료 (별도 이슈로 추적)
- **실패 처리**: spawn 실패 시 Rust가 에러 이벤트 emit, React는 해당 탭 영역에 에러 UI 표시, 다른 탭은 무사

### 12.3 IPC 레이어 패턴
**단일 ipc.ts가 kind별로 분기**:
```ts
// src/lib/ipc.ts
type SidecarKind = 'kuro' | 'mame';
export async function rpc(kind: SidecarKind, method: string, params: unknown): Promise<unknown> {
  return await invoke('sidecar_rpc', { kind, method, params });
}
```
- Rust `sidecar_rpc` command가 `kind`에 따라 해당 프로세스로 JSON-RPC 라우팅
- 기존 kuro/mame의 handler별 래퍼(예: `exportExcel()`)는 `src/lib/ipc-kuro/`, `src/lib/ipc-mame/`로 이동하고 내부적으로 `rpc('kuro', ...)` 호출

### 12.4 xlsx 메타 시그니처 쓰기 책임과 시점
- **쓰기**: `kuma_core.kuro`의 export handler(`handlers/export.py`의 `handle_export_excel`)가 project_id를 파라미터로 받아 `__kuma_meta__` 시트 추가. 현재는 project_id 인자 없음 → 추가 필요.
- **project_id 발급 순서**: 
  1. "새 프로젝트" 시점에 Rust가 uuid 생성 → `kuma.project.json` 생성
  2. Kuro 탭이 xlsx export할 때 현재 프로젝트의 project_id를 sidecar에 전달
  3. scratch 모드 export는 project_id 없이(메타 시트 생략) 생성 — 기존 kuro 동작과 동일
- **수정 포함 단계**: **Step 4(탭 통합)**. Step 3까지는 기존 동작 그대로 둠. Step 4에서 export 시그니처 확장 + Mame 탭의 xlsx 드롭 시 메타 read 추가.
- **읽기**: `kuma_core.mame`는 xlsx 파싱 시 `__kuma_meta__` 시트 있으면 project_id 반환. Rust/React가 받아서 `recent_projects`와 매칭.

### 12.5 Stage 전이 정책 (v0.1)
- **수동 전이 없음**. `stage` 필드는 파일 존재 여부로 Rust가 자동 계산:
  - `draft`: design workspace 없음
  - `design_complete`: `expected_mutations.xlsx` 존재
  - `analyzing`: `analysis/consensus/`에 파일 존재, `verdict.xlsx` 없음
  - `done`: `verdict.xlsx` 존재
- 프로젝트 열 때 및 주요 저장 이벤트 후 재계산. UI는 계산 결과만 표시.
- 탭 접근 제약 없음 — 사용자가 아직 Kuro 단계 안 끝나도 Mame 탭 열 수 있음(빈 상태 표시).

### 12.6 Build script 통합
- `python-core/build_sidecar.py`를 CLI 화: `python build_sidecar.py --target {kuro|mame|all}`
- 내부적으로 두 `.spec` 파일 순차 실행
- Tauri `tauri.conf.json`의 `externalBin`에 두 바이너리(`binaries/kuro-sidecar`, `binaries/mame-sidecar`) 등록

### 12.7 엣지 케이스 단계 할당
| 케이스 | 처리 단계 |
|---|---|
| Projects root 사라짐/이동 | Step 2 (프로젝트 레이어) |
| 동명 프로젝트 suffix | Step 2 |
| 손상된 kuma.project.json | Step 2 |
| xlsx project_id 불일치 | Step 4 (탭 통합) |
| schema 버전 미래값 | Step 2 |
| sidecar spawn 실패 UI | Step 4 |
| 미사용 sidecar 자동 종료 | v0.2 연기 (Step 5 out of scope) |

시간 예측 3.5-4일에 Step 2·4 엣지 케이스 포함. v0.2 연기 항목은 별도.

## 13. 향후 과제 (out of scope, 기록만)

- Python sidecar 단일 프로세스 통합 (v0.2+ 검토)
- 다중 프로젝트 동시 열기 (창 분리 또는 세션 스위처)
- 프로젝트 단계 자동 감지 (폴더 내 파일 존재 여부로 `stage` 업데이트)
- 미사용 탭 sidecar 자동 종료 정책
- 프로젝트 템플릿 (자주 쓰는 파라미터 조합 저장)
