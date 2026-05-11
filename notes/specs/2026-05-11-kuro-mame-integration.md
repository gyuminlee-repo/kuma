# KURO-MAME Integration + UI 정리 스펙

date: 2026-05-11
status: approved (rev2 - 2026-05-11)

---

## 변경 이력

| rev | 날짜 | 주요 변경 |
|-----|------|----------|
| 1 | 2026-05-11 | 초안 |
| 2 | 2026-05-11 | B 기능을 KURO→MAME 이동. MAME 2-Phase 구조 추가. 플랭킹 프라이머 Tm 기반 설계로 업그레이드. C 단순화 (sdm_primers만). |

---

## 범위 요약

4개 독립 기능. 의존 순서: C 독립, B → A, D 독립.

| ID | 기능 | 위치 | 의존 |
|----|------|------|------|
| A | MAME Context Bridge (mame_context.json 자동 채움 + Re-detect) | MAME | B |
| B | MAME Barcode Setup (2-Phase UI + 플랭킹 프라이머 설계 + 패키지 생성) | MAME | - |
| C | KURO Export All 원클릭 (sdm_primers만) | KURO | - |
| D | UI 정리 (메뉴 재구성 + About/Settings 분리 + i18n) | 공통 | - |

---

## B. MAME Barcode Setup (Phase 1)

### 배경 결정

- 바코드 생성 기능은 MAME에 위치. KURO는 프라이머 설계 전용.
- MAME = 시퀀싱 준비(Barcode Setup) + 시퀀싱 후 분석(Analyze) 두 단계 포괄.
- 플랭킹 프라이머는 단순 슬라이싱이 아닌 Tm 기반 길이 탐색으로 업그레이드.
  - **절대 원칙**: amplicon은 target gene 전체를 포함해야 함. gene 좌표가 flank의 기준점.

### MAME 2-Phase 구조

```
┌─ MAME ─────────────────────────────────────────┐
│  [1. Barcode Setup]  [2. Analyze]               │
└─────────────────────────────────────────────────┘
```

- Phase 탭은 MAME 내부 탭. `MainShell`의 Kuro/Mame 탭과 별개.
- Phase 선택: `localStorage` 키 `kuma:mame:phase` 에 "setup" | "analyze" 저장.
- 신규 컴포넌트: `src/components/mame/panels/BarcodeSetupPanel.tsx`
- `MameAppLayout.tsx` 상단에 Phase 탭 추가, Phase에 따라 BarcodeSetupPanel / 기존 Sidebar+분석 렌더.

### BarcodeSetupPanel UI

```
┌─ Amplicon Target ────────────────────────────────┐
│  Reference sequence                               │
│  [ ispS.fa               ] [Browse]               │
│  (Auto-detected badge if from mame_context.json)  │
│                                                   │
│  Gene start (0-based, CDS)  [    0    ]           │
│  Gene end   (0-based, CDS)  [   1350  ]           │
│  Gene name                  [ ispS    ]           │
└──────────────────────────────────────────────────┘

┌─ Primer Design Options ──────────────────────────┐
│  Polymerase         [Q5           ▾]              │
│  Flanking distance   Min [100]  Max [400]  bp     │
│  Binding length      Min [ 18]  Max [ 35]  bp     │
│  Tm range            Min [ 55]  Max [ 68]  °C     │
│  GC clamp           [✓] require 3' G/C            │
└──────────────────────────────────────────────────┘

┌─ Barcode Seeds ──────────────────────────────────┐
│  Barcode seeds file  [ seeds.xlsx ] [Browse]      │
└──────────────────────────────────────────────────┘

[Generate Barcode Package]

┌─ Output (생성 후 표시) ──────────────────────────┐
│  design/barcodes_sequence.xlsx       ✓            │
│  design/ispS_amplicon.fa             ✓            │
│  design/sample_map_template.xlsx     ✓            │
│  mame_context.json                   ✓            │
│  [Open folder]                                    │
└──────────────────────────────────────────────────┘
```

mame_context.json 있으면 reference_path → fasta 필드, gene_start/end 자동 채움 + "Auto-detected" 뱃지. 없으면 빈 상태 (에러 아님).

### barcode_seeds.xlsx 포맷

```
A열      B열 (대문자, 8-15bp)
fwd_1    TATCTGACCTT
...
fwd_12   GAACATACGG
rev_1    CCCTATGACA
...
rev_8    AGAGTGCGGC
```

검증 규칙:
- fwd 12개 + rev 8개 정확히 있어야 함 (부족/초과 시 ValueError)
- 중복 서열 금지 (fwd+rev 합산 20개 전체)
- 허용 문자: A, T, G, C (대소문자 허용, 내부 upper() 처리)
- 길이 5-30bp

### Polymerase 프로파일

PrimerBench 패턴 참조. 초기 지원 목록 (확장 가능):

| name | mv_conc | dv_conc | dntp_conc | dna_conc | tm_method |
|------|---------|---------|-----------|----------|-----------|
| Q5 | 50.0 | 3.0 | 0.2 | 250.0 | santalucia |
| Taq | 50.0 | 1.5 | 0.2 | 250.0 | santalucia |
| Phusion | 50.0 | 1.5 | 0.2 | 250.0 | santalucia |

`salt_corrections_method = "santalucia"` 공통.

`kuma_core/mame/ingest/polymerase.py` (신규) 에 `POLYMERASE_PROFILES: dict[str, dict]` 상수로 정의.

### Python 백엔드

**`kuma_core/mame/ingest/barcode_package.py`** - 이미 구현됨, 하기 함수 시그니처 업그레이드 필요:

```python
@dataclass
class PolymeraseProfile:
    name: str
    mv_conc: float
    dv_conc: float
    dntp_conc: float
    dna_conc: float
    tm_method: str = "santalucia"
    salt_corrections_method: str = "santalucia"

def calc_tm(seq: str, profile: PolymeraseProfile) -> float:
    """primer3.calc_tm wrapper with polymerase profile."""

def _gc_percent(seq: str) -> float: ...

def design_flanking_primers(
    cds_sequence: str,
    gene_start: int,          # 0-based, gene 시작 위치 (amplicon이 감싸야 할 범위 시작)
    gene_end: int,            # 0-based exclusive, gene 끝 위치
    profile: PolymeraseProfile,
    flank_min: int = 100,     # gene 경계에서 primer 3' end까지 최소 거리 (bp)
    flank_max: int = 400,     # gene 경계에서 primer 3' end까지 최대 거리 (bp)
    binding_min_len: int = 18,
    binding_max_len: int = 35,
    tm_min: float = 55.0,
    tm_max: float = 68.0,
    require_gc_clamp: bool = True,
) -> tuple[str, str]:         # (fwd_flanking, rev_flanking) 소문자
    """Tm 기반 플랭킹 프라이머 탐색.

    fwd primer: gene_start 기준으로 upstream 방향 flank_min..flank_max 범위 내에서
                binding_min_len..binding_max_len 길이를 시도하여
                tm_min <= Tm <= tm_max + (require_gc_clamp 시 3' end G/C) 조건 충족하는 첫 번째 후보 반환.
    rev primer: gene_end 기준으로 downstream 방향 동일 로직, reverse_complement 적용.

    조건 충족 후보 없으면: Tm 범위 내 최선 후보 반환 + warnings에 메시지 추가.
    flank 범위 내 서열이 binding_min_len보다 짧으면: ValueError.
    """

def generate_mame_package(
    fasta_path: Path,
    gene_start: int,
    gene_end: int,
    barcode_seeds_path: Path,
    output_dir: Path,
    project_root: Path,
    gene_name: str = "ispS",
    polymerase: str = "Q5",
    flank_min: int = 100,
    flank_max: int = 400,
    binding_min_len: int = 18,
    binding_max_len: int = 35,
    tm_min: float = 55.0,
    tm_max: float = 68.0,
    require_gc_clamp: bool = True,
) -> MamePackageResult: ...
```

**중요**: 기존 구현의 `amplicon_start/end` 파라미터명을 `gene_start/gene_end`로 변경. 의미가 달라졌음 (프라이머 위치가 아닌 gene 범위).

**`python-core/sidecar_mame/handlers/barcode_package.py`** (신규 - sidecar_kuro 아님):

```python
def handle_generate_mame_package(params: dict) -> dict:
    """
    Params:
      fasta_path           str, required
      gene_start           int, required
      gene_end             int, required
      barcode_seeds_path   str, required
      output_dir           str, required
      project_root         str, required
      gene_name            str, optional, default "ispS"
      polymerase           str, optional, default "Q5"
      flank_min            int, optional, default 100
      flank_max            int, optional, default 400
      binding_min_len      int, optional, default 18
      binding_max_len      int, optional, default 35
      tm_min               float, optional, default 55.0
      tm_max               float, optional, default 68.0
      require_gc_clamp     bool, optional, default true
    Returns:
      barcodes_xlsx, amplicon_fa, sample_map_template, context_json (절대 경로 str)
      warnings: list[str]
    """
```

**`python-core/sidecar_kuro/handlers/barcode_package.py`** - 삭제 (이미 생성됐다면 제거).
**`python-core/sidecar_kuro/dispatcher.py`** - `generate_mame_package` 등록 제거.
**`python-core/sidecar_mame/dispatcher.py`** - `generate_mame_package` 등록 추가.

### TS 타입

`src/types/mame/barcode_package.ts` (신규):
```ts
export interface GenerateMamePackageParams {
  fasta_path: string
  gene_start: number
  gene_end: number
  barcode_seeds_path: string
  output_dir: string
  project_root: string
  gene_name?: string
  polymerase?: string
  flank_min?: number
  flank_max?: number
  binding_min_len?: number
  binding_max_len?: number
  tm_min?: number
  tm_max?: number
  require_gc_clamp?: boolean
}

export interface MamePackageResult {
  barcodes_xlsx: string
  amplicon_fa: string
  sample_map_template: string
  context_json: string
  warnings: string[]
}
```

### 단위 테스트 업데이트

`tests/mame/test_barcode_package.py` - 기존 케이스 유지 + 추가:
- Tm 기반 설계: 정상 범위 → fwd/rev primer Tm이 tm_min..tm_max 내인지 검증
- GC clamp: require_gc_clamp=True → 3' end가 G/C인지 검증
- flank 범위 내 후보 없음 → warnings에 메시지 포함, 최선 후보 반환
- gene_start/end 파라미터명 반영 (amplicon_start/end 제거)

---

## A. MAME Context Bridge

### mame_context.json 스키마

위치: `{project root}/mame_context.json`. 경로는 모두 프로젝트 루트 기준 상대 경로.
"프로젝트 루트" = `KumaProject.path` (kuma.project.json이 있는 폴더).

```json
{
  "schema": 1,
  "published_at": "2026-05-11T13:00:00Z",
  "custom_barcodes_path": "design/barcodes_sequence.xlsx",
  "reference_path": "design/ispS_amplicon.fa",
  "sample_map_template_path": "design/sample_map_template.xlsx"
}
```

### BarcodeSetupPanel 자동 채움

mame_context.json 로드 시:
- `reference_path` → fasta 필드 (상대 경로를 절대 경로로 변환)
- 필드 옆 "Auto-detected" 뱃지 표시

### detectProjectFiles.ts 우선순위 (기존 Analyze Phase 입력용)

```
1. autosave  (.autosave/mame.json)     - 최우선
2. mame_context.json                   - autosave로 채워지지 않은 필드만 적용
3. readDir 파일시스템 스캔              - mame_context.json 없을 때만 실행 (성능)
```

구현:
- `readTextFile("{projectPath}/mame_context.json")` → JSON.parse → 상대 경로를 절대 경로로 변환
- 파일 없거나 parse 실패 시 → readDir 스캔으로 fallback (에러 무시)
- 각 필드: 이미 채워진 store 값 있으면 skip

### Re-detect 버튼

위치: MAME `InputPanel.tsx` 상단 우측 (소형, ghost variant).

```
┌─ Input Files ────────────────── [Re-detect] ┐
```

동작:
- `applyMameAutoDetect(projectPath, onMessage)` 호출 (useAutosaveHydration에서 export)
- 빈 필드만 채움. 이미 입력된 값 보호.
- 결과 toast: `"Auto-detected: {채워진 필드 목록}"` / 아무것도 없으면 `"No new files detected"`
- 버튼 클릭 중 loading 스피너 표시

에러 처리:
- readDir 실패 → 해당 필드 skip, 나머지 계속
- mame_context.json 파싱 실패 → console.warn + readDir fallback

### TS 타입 신규

`src/types/mame/mame_context.ts`:
```ts
export interface MameContext {
  schema: number
  published_at: string
  custom_barcodes_path?: string
  reference_path?: string
  sample_map_template_path?: string
}
```

---

## C. KURO Export All (단순화)

### 동작

단축키: `Ctrl+Shift+E`
저장 위치: `{KumaProject.path}/design/` (대화창 없음, 자동)

생성 파일:

| 파일 | 조건 |
|------|------|
| `design/sdm_primers.xlsx` | designResults 있을 때 |

완료 toast: `"Exported sdm_primers.xlsx → design/"` + "Open folder" 링크

에러 처리:
- designResults 없을 때: 버튼 disabled

**rev1 대비 변경**: 바코드 패키지 생성(barcodes_sequence.xlsx, amplicon.fa 등) 제거. KURO는 SDM primers만 export.

### 메뉴 변경 (KURO MenuBar)

**제거 항목:**
- Save Workspace...
- Load Workspace...
- Open run manifest...
- Compare run manifests...
- Compare workspaces...
- Export workspace as zip...
- Export IDT CSV
- Export Twist CSV

**File 메뉴 최종:**
```
Open Sequence...     Cmd+O
─────────────────
Restart Sidecar
```

**Export 메뉴 (신규 분리):**
```
Export All           Ctrl+Shift+E
─────────────────
Export Excel...      Cmd+E
Export Echo Mapping...
Export JANUS Mapping...
```

---

## D. UI 정리 — About/Settings 분리 + i18n

### Settings 다이얼로그 (신규)

`src/components/layout/SettingsDialog.tsx` (신규)

내용:
- **Accessibility**: Colorblind mode 토글, Keyboard shortcuts 표
- **Notifications**: 알림 설정
- **Data folder**: 앱 데이터 경로 표시 + 열기 버튼

KURO/MAME 양쪽 MenuBar의 Help 메뉴에 Settings 항목 추가 또는 기존 About에서 접근.

### About 다이얼로그 (최소화)

현재 About에서 Settings 다이얼로그로 이동:
- Accessibility, Notifications, Data folder → Settings

About 다이얼로그 최종 내용:
```
버전 + 설명 + GitHub 링크
─────────────────────────
Check for Updates 버튼
─────────────────────────
How to cite (BibTeX 복사 버튼)
─────────────────────────
License 한 줄
Third-party licenses 버튼
─────────────────────────
[Advanced ▾]  ← 접힌 섹션
  External services, Build info, Diagnostics, Codesign status
```

KURO About = MAME About → 동일한 `SharedAboutDialog` 컴포넌트로 통합.
타이틀: "About Kuma".

### i18n 활성화

**의존성 추가:** `pnpm add react-i18next i18next`

**번역 파일:**
```
src/locales/
  en.json
  ko.json
```

**초기화:** `src/main.tsx`에서 앱 마운트 전 `i18next.init()` 호출.

**LocaleToggle 수정:** 선택 시 `i18next.changeLanguage(resolved)` + `setLocale(locale)` 호출.

**번역 범위 (1차):**
- UI 레이블, 버튼 텍스트, toast 메시지, 에러 메시지
- 과학 용어(primer, barcode, well ID 등)는 영어 고정

---

## 변경 파일 목록

### 신규 파일

| 파일 | 설명 |
|------|------|
| `src/components/mame/panels/BarcodeSetupPanel.tsx` | MAME Phase 1 패널 |
| `src/components/layout/SettingsDialog.tsx` | Settings 다이얼로그 |
| `src/types/mame/mame_context.ts` | MameContext 타입 |
| `src/types/mame/barcode_package.ts` | barcode package RPC 타입 |
| `src/locales/en.json` | 영어 번역 |
| `src/locales/ko.json` | 한국어 번역 |
| `kuma_core/mame/ingest/polymerase.py` | Polymerase 프로파일 상수 |
| `python-core/sidecar_mame/handlers/barcode_package.py` | MAME RPC 핸들러 |
| `tests/mame/test_barcode_package.py` | 단위 테스트 (기존 업그레이드) |

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `kuma_core/mame/ingest/barcode_package.py` | design_flanking_primers Tm 기반 업그레이드, gene_start/end로 파라미터명 변경 |
| `python-core/sidecar_mame/dispatcher.py` | generate_mame_package 등록 |
| `python-core/sidecar_kuro/dispatcher.py` | generate_mame_package 등록 제거 (rev1에서 잘못 추가됨) |
| `src/components/mame/layout/MameAppLayout.tsx` | Phase 탭 추가 |
| `src/components/layout/MenuBar.tsx` | 항목 다수 제거, Export 메뉴 분리, About 최소화 |
| `src/components/mame/layout/MenuBar.tsx` | About → SharedAboutDialog |
| `src/lib/i18n.ts` | i18next 초기화 헬퍼 |
| `src/main.tsx` | i18next.init() 호출 추가 |
| `src/lib/mame/detectProjectFiles.ts` | mame_context.json 우선순위 추가 |
| `src/hooks/useAutosaveHydration.ts` | applyMameAutoDetect export |
| `src/components/mame/panels/InputPanel.tsx` | Re-detect 버튼 추가 |
| `src/components/layout/export-handlers.ts` | handleExportAll 추가, IDT/Twist 핸들러 제거 |

### 삭제 파일

| 파일 | 이유 |
|------|------|
| `python-core/sidecar_kuro/handlers/barcode_package.py` | sidecar_mame으로 이동 |

### rev1에서 이미 완료된 파일 (재사용)

| 파일 | 상태 |
|------|------|
| `kuma_core/mame/ingest/barcode_package.py` | 구현됨, 시그니처 업그레이드 필요 |
| `tests/mame/test_barcode_package.py` | 구현됨, 케이스 추가 필요 |
