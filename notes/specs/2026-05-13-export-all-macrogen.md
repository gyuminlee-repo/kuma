# Export All — Macrogen Plate Order 통합

작성: 2026-05-13
대상: kuro 모듈 Phase C `export.format` 서브스텝
관련 파일:
- `src/components/steps/ExportFormatSelector.tsx`
- `src/components/layout/export-handlers.ts`
- `src/components/dialogs/MappingExportDialog.tsx` (legacy 참고)
- `python-core/sidecar_kuro/handlers/export.py`
- `python-core/sidecar_kuro/models.py`
- `kuma_core/kuro/plate_mapper.py`
- `.cross-layer-sync.json`
- 출처 템플릿: `$WORKSPACE_ROOT/020.admin/projects/030.EvolveProprimer/Macrogen_PlateOligo_Order_ExcelTemplate.xls`

## 1. 배경 / 문제

1. 기존 Phase C export UI가 두 섹션 (Primer Order Export + Plate Mapping Export) 으로 분리되어, 한 번에 일괄 export 하던 과거 동작이 "mapping" 중심 분할로 회귀함. 사용자 요구: Section 1 = **Export All** 단일 버튼으로 kuro 생성 산출물 6종 일괄 생성.
2. Primer Order 옵션이 IDT CSV / Twist CSV / FASTA 였으나 실제 주문은 Macrogen Plate Oligo Order. IDT/Twist 코드패스는 사용되지 않음.
3. `ExportFormatSelector.tsx:36` 의 echo 범위가 50–5000 nL 로 하드코딩되어 legacy `MappingExportDialog.tsx:28` 의 25–500 nL 및 관련 테스트(max=500)와 불일치. UI 의 "Range: 50–5000 nL" 문구가 잘못된 값을 노출.

## 2. 목표 (in-scope)

- Phase C export.format 서브스텝을 단일 **Export All** 섹션으로 재설계.
- Macrogen Plate Oligo Order `.xls` exporter 신설 — fwd/rev 2 plate 가 한 파일 안에 수직 concatenation.
- Echo 입력 범위 표시·검증을 25–500 nL 로 통일.
- IDT/Twist 라디오 옵션 제거.

## 3. 비목표 (out-of-scope)

- `export_idt_csv` / `export_twist_csv` 함수 본체 삭제 (기존 테스트 보존, import 만 정리).
- mame 모듈 export.
- Macrogen 웹 LIMS 자동 업로드.
- 다국어 신규 번역키 외 전반 i18n 리팩터링.

## 4. 입력 규칙 — 출처 정리

### 4.1 Plate Name

- 출처: 사용자 실측 (Macrogen 공식 PDF `DNA_Order_Guide_Oligo_v2.0` 은 검증 규칙 미명시).
- 정규식: `^[A-Za-z0-9_-]{1,20}$`
- 한글, 공백, 그 외 특수문자 거부.
- 빈 문자열 거부.

### 4.2 Oligo Name

- Macrogen Custom Oligo 가이드: "이름을 한글로 입력 시 기입 안 됨" (PDF p.6).
- 정규식: `^[A-Za-z0-9_-]{1,20}$` (length 20 은 plate name 과 동일 정책으로 채택, 실측 미확정 — 위반 시 export 차단).
- 위반 발견 시 Macrogen export 만 차단. 그 외 산출물(FASTA, run.json 등) 은 sanitization 없이 그대로 진행.

### 4.3 Amount

- 허용 값: `0.05`, `0.2` (단위 μmole).
- 기본값: `0.05`.
- UI 라벨: `0.05 μmole`, `0.2 μmole`. `.xls` 셀에 기입할 정확한 문자열은 **TBD — Macrogen 웹 실측 후 확정** (현재 spec 기본: `0.05` / `0.2` 숫자만).

### 4.4 Purification

- 단일 값 `MOPC`. dropdown 대신 readonly 라벨 표시.

### 4.5 Echo transfer volume

- Range: 25 ≤ v ≤ 500 nL (legacy MappingExportDialog 값으로 통일).
- 기본값: 100 nL.
- step: 1.
- 500 nL 초과 입력 차단 (이전의 multi-transfer 자동 분할 안내는 제거 — Range 단일 정책으로 단순화).

## 5. UI 설계 (ExportFormatSelector 재작성)

```
┌─ Export All ────────────────────────────────────────────────────────┐
│ Plate Name (fwd):  [ MyProj_fwd       ]  ← 인라인 검증 (regex)      │
│ Plate Name (rev):  [ MyProj_rev       ]                              │
│ Amount:            [ 0.05 ▾ ]   Purification: MOPC                   │
│ Echo transfer vol: [ 100 ] nL   (Range: 25–500 nL)                   │
│ JANUS transfer vol: [ 2.0 ] μL  (Range: 0.5–10 μL)                   │
│ [ ] Include BoM                                                      │
│                                                                      │
│ 입력 규칙: Plate / Oligo name 1–20자, 영문·숫자·`_`·`-` 만 허용       │
│                                                                      │
│ [ Export All ]   ← 클릭 → 6개 파일 일괄 생성 + toast 결과 요약        │
└──────────────────────────────────────────────────────────────────────┘
```

- fwd 또는 rev primer 가 없는 경우 해당 Plate Name 입력란을 숨김.
- Plate Name 입력란 옆 실시간 well 카운트 표시 (예: `87/96 wells`). 96 초과 시 카운트 빨강 + 안내 캡션 "primer 수가 96 well 한계 초과. 설계 단계에서 분할 필요". Export All 버튼 disabled.
- 검증 실패 시 Export All 버튼 disabled + 위반 항목별 메시지 (예: `Plate Name (fwd) 형식 오류: 한글 포함`).
- BoM 체크박스는 mapping export 옵션 (Echo/JANUS) 에 그대로 전달.

## 6. Export All 동작

클릭 시 단일 directory dialog 호출. dialog default = `<projectDir>/`. 사용자 폴더 선택 후 그 폴더 안에 6 종 파일 일괄 작성:

| 산출물 | 파일명 | exporter |
|---|---|---|
| Macrogen plate order | `<projectName>_<YYYYMMDD>.kuro.macrogen.xls` | `export_macrogen_xls` (신규) |
| FASTA | `<projectName>_<YYYYMMDD>.kuro.primers.fasta` | `export_primers_fasta` (신규 또는 기존 재사용) |
| Echo mapping CSV | `<projectName>_<YYYYMMDD>.kuro.echo.csv` | `export_echo_mapping_csv` |
| JANUS mapping CSV | `<projectName>_<YYYYMMDD>.kuro.janus.csv` | `export_janus_mapping_csv` |
| Plate map xlsx | `<projectName>_<YYYYMMDD>.kuro.platemap.xlsx` | `export_plate_excel` |
| Run report json | `<projectName>_<YYYYMMDD>.kuro.run.json` | 기존 |

- `<projectName>` fallback 순서: `project.name` → `fwd_plate_name` → `rev_plate_name` → 고정 문자열 `"kuro_export"`. 어느 것도 없는 시나리오에서도 export 가 차단되지 않음.
- 폴더 default 가 이미 존재하면 그대로 사용. 기존 동일 파일명 존재 시 단일 confirm dialog 에서 6 종 파일 목록을 모두 보여주고 일괄 덮어쓰기 / 취소 (개별 confirm 없음).
- 한 파일이라도 검증/IO 실패 시 partial success — 성공한 파일은 보존하고 toast 에 다음 형식으로 표시:
  ```
  Exported 4/6 files.
    ✓ macrogen.xls, primers.fasta, echo.csv, platemap.xlsx
    ✗ janus.csv (reason: ...), run.json (reason: ...)
  ```
  toast action 으로 [Open folder] 와 [Retry failed] 제공. retry 는 실패 파일 목록만 재시도.

## 7. Macrogen `.xls` 포맷 상세

- 1 시트, BIFF8 (`.xls`).
- 헤더 1 행: `No.`, `Plate Name`, `Well`, `Oligo Name`, `5' - Oligo Seq - 3'`, `Amount`, `Purification`.
- fwd plate 행 (96 행) → rev plate 행 (96 행) 수직 concatenation. No. 는 1..192 연속.
- Well 순서 column-major: `A1, B1, C1, ..., H1, A2, ..., H12` — 템플릿 default 동일.
- 한 plate 내 oligo 수 ≤ 96. 초과 시 export 차단 + 사용자 메시지 ("fwd primer 100 개 > 96 well. 분할 필요").
- 사용한 well 만 Oligo Name / Seq / Amount / Purification 채움, 나머지 well 은 Plate Name + Well + No. 만 두고 나머지 셀 공란 (템플릿 관행).
- 작성 라이브러리: `xlwt==1.3.0` (Python). `.devcontainer/Dockerfile` 에 추가 후 rebuild.

## 8. 백엔드 변경

### 8.1 `kuma_core/kuro/plate_mapper.py`

신규 함수:

```python
def export_macrogen_xls(
    fwd_primers: list[Primer],
    rev_primers: list[Primer],
    fwd_plate_name: str,
    rev_plate_name: str,
    amount: Literal["0.05", "0.2"],
    purification: Literal["MOPC"],
    output_path: str,   # 단일 .xls 파일 절대 경로
) -> None: ...
```

명명 규칙: `output_path` = 단일 파일 경로 (`.xls`, `.csv` 등 개별 exporter), `output_dir` = 폴더 경로 (Export All 처럼 다수 파일 작성). 본 spec 전체에서 일관 적용.

- 입력 검증: plate name regex, oligo name regex, well count ≤ 96. 위반 시 `ValueError`.
- column-major well order: `[f"{row}{col}" for col in range(1, 13) for row in "ABCDEFGH"]`.

### 8.2 `python-core/sidecar_kuro/models.py`

Pydantic 요청 모델 추가:

```python
class ExportMacrogenParams(BaseModel):
    project_id: str | None = None
    output_path: str
    fwd_plate_name: str
    rev_plate_name: str
    amount: Literal["0.05", "0.2"] = "0.05"
    purification: Literal["MOPC"] = "MOPC"

    @field_validator("fwd_plate_name", "rev_plate_name")
    @classmethod
    def _plate_name_rule(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", v):
            raise ValueError(f"plate name '{v}' violates ^[A-Za-z0-9_-]{{1,20}}$")
        return v


class ExportAllParams(BaseModel):
    project_id: str | None = None
    output_dir: str
    fwd_plate_name: str | None = None
    rev_plate_name: str | None = None
    amount: Literal["0.05", "0.2"] = "0.05"
    purification: Literal["MOPC"] = "MOPC"
    echo_transfer_vol: int = 100   # nL, 25..500
    janus_transfer_vol: float = 2.0  # μL, 0.5..10
    bom: bool = False
```

### 8.3 `python-core/sidecar_kuro/handlers/export.py`

- 기존 `if p.format == "idt"` / `"twist"` 분기 제거.
- 신규 `handle_export_macrogen` (단일 .xls), `handle_export_all` (6 종 일괄) 등록.
- dispatcher `_METHODS` 에 추가. cross-layer registry sync.
- `export_idt_csv` / `export_twist_csv` 함수 본체와 단위 테스트는 유지 (회귀 안전망).

## 9. 프론트엔드 변경

### 9.1 `src/components/steps/ExportFormatSelector.tsx`

- Section 2 제거. Section 1 만 유지하되 Export All 입력 영역으로 재작성.
- `ExportFormat` 타입 제거 (또는 `"all" | "macrogen-only"` 로 축소 — 본 spec 은 `"all"` 단일).
- `MAPPING_FORMAT_DEFAULTS` 의 echo `min:50, max:5000` → `min:25, max:500, step:1`. janus 는 유지.
- 인라인 검증: zod 또는 단순 regex 함수로 plate name / oligo name 확인. 위반 항목은 입력란 아래 빨간 캡션.

### 9.2 `src/components/layout/export-handlers.ts`

신규 `handleExportAll(params)`:

```ts
export async function handleExportAll(params: {
  projectId?: string;
  fwdPlateName?: string;
  rvsPlateName?: string;
  amount: "0.05" | "0.2";
  echoTransferVol: number;
  janusTransferVol: number;
  bom: boolean;
}): Promise<{ success: string[]; failed: { path: string; reason: string }[] }> { ... }
```

- 단일 폴더 dialog (`@tauri-apps/plugin-dialog` `open({ directory: true })`).
- 폴더 결정 후 6 종 파일 경로 계산 → sidecar `export_all` RPC 1 회 호출.
- partial success 결과를 toast 로 노출. `revealInOSFolder` 액션 포함.

### 9.3 `src/types/models.ts` / `src/types/models.generated.ts`

- Pydantic 재생성: `pnpm gen:models`.
- `RpcMethodMap` 에 `export_macrogen`, `export_all` 추가.

### 9.4 i18n

신규 키:
- `phaseC.export.all.heading` "Export All"
- `phaseC.export.all.plateNameFwd` / `plateNameRev`
- `phaseC.export.all.amountLabel`
- `phaseC.export.all.purificationLabel`
- `phaseC.export.all.echoVolLabel`
- `phaseC.export.all.janusVolLabel`
- `phaseC.export.all.bomLabel`
- `phaseC.export.all.runExport`
- `phaseC.export.all.ruleHint` "1–20자, 영문/숫자/_/- 만 허용"
- 검증 오류 메시지 키 군 (`phaseC.export.all.error.plateNameRegex` 등)

기존 `phaseC.export.format.idt` / `.twist` / `.orderExport.*` / `.mappingExport.*` 키는 사용처가 없어지면 ko/en JSON 에서 삭제. 잔류 검색은 `grep -r "orderExport"` 로 확인.

## 10. 테스트

### 10.1 백엔드

- `tests/test_macrogen_export.py` 신규
  - 정상 1 plate 96 well
  - 정상 fwd+rev 2 plate (192 행, No. 1..192)
  - well count 97 → `ValueError`
  - plate name 한글 → `ValueError`
  - oligo name 공백 → `ValueError`
  - `.xls` 파싱 후 column-major well 순서 확인

### 10.2 프론트엔드

- `ExportFormatSelector.test.tsx`
  - Echo Range 텍스트 "25–500 nL" 렌더
  - plate name 한글 입력 → 버튼 disabled + 에러 메시지
  - Export All 클릭 → `handleExportAll` 호출 인자 검증
- `handlers/export.integration.test.ts` 6 종 파일 경로 인자 검증.

### 10.3 Cross-layer

- `.cross-layer-sync.json` `groups[]` 에 `macrogen-export-flow` 추가:
  ```json
  {
    "id": "macrogen-export-flow",
    "files": [
      "src/components/steps/ExportFormatSelector.tsx",
      "src/components/layout/export-handlers.ts",
      "python-core/sidecar_kuro/handlers/export.py",
      "python-core/sidecar_kuro/models.py",
      "kuma_core/kuro/plate_mapper.py"
    ],
    "note": "Export All UI ↔ RPC ↔ exporter 정합성",
    "severity": "blocking"
  }
  ```
- `pnpm sync:check` 통과 확인.
- `pnpm gen:models:check` 통과 확인.

## 11. 마이그레이션 / 호환성

- `MappingExportDialog.tsx` 는 dead code 화 — 본 PR 에서 삭제. 관련 테스트도 삭제.
- 기존 export 단축키 / 메뉴 항목 중 Plate Mapping Export 직접 호출 경로 검색 후 Export All 로 리다이렉트.
- 워크스페이스 파일 호환: 변경 없음 (export 는 출력 전용).

## 12. 환경 변경

- `xlwt==1.3.0` 추가 → `.devcontainer/Dockerfile` 즉시 갱신, "Rebuild Container" 사용자 알림.

## 13. 미확정 / 추후 검증 (open questions)

- Oligo Name 길이 상한 (현재 20 가정).
- Macrogen `.xls` 의 Amount 셀 정확한 문자열 표기 (`0.05` vs `0.05 μmole` vs `0.05 umole`).
- Echo 500 nL 초과 multi-transfer 자동 분할 기능을 영구 제거할지, 별도 PR 로 보존할지.

## 14. 헌장 / 룰 체크리스트

- [필수] Recovery — partial success 결과 toast.
- [필수] Output Persistence — 6 종 파일이 모두 projectDir 하위에 저장.
- [필수] Input Guards — plate / oligo name regex, well count ≤ 96, echo 25–500, janus 0.5–10.
- [필수] Cross-platform — Dockerfile 갱신 후 ubuntu / windows / macos CI 통과 필요.
- [필수] A11y — Range / 검증 오류는 `aria-describedby` 로 연결.
- [필수] No-hardcoded-constants — Amount / Purification 옵션은 한 곳 (models.py) 에서 정의 후 백엔드/프론트 양쪽 참조.

---

## 15. 사이드바 통일 + 드래그 리사이즈 (kUMA 전역)

### 15.1 배경 / 문제

`AppShell.sidebar` 슬롯 (`src/components/shell/AppShell.tsx:75`) 이 명시적 너비 없이 내부 컨텐츠 (SubStepNav) 길이로 결정됨. kuro / mame 양쪽 동일 AppShell 사용. 결과:
- phase 전환마다 sub-step 레이블 길이에 따라 사이드바 너비 점프
- kuro 와 mame 가 다른 너비로 보일 수 있음
- 사용자가 너비 조절 불가

### 15.2 목표 (in-scope)

- AppShell.sidebar 단일 슬롯 (kuro AppLayout + mame MameAppLayout 공용) 너비 통일.
- 모든 phase 의 SubStepNav 최장 레이블 기준 default width 자동 계산 — phase 전환 시 점프 없음.
- 마우스 드래그 핸들로 너비 조절 가능 (min 180 px, max 480 px).
- 변경 너비 실시간 (debounce 200 ms) localStorage 저장 — Zustand `layoutSlice` 신규 추가.

### 15.3 비목표 (out-of-scope)

- mame `PlateView.tsx:112` 우측 aside (선택된 well 상세 패널) — 용도 다름, 별도 PR.
- 사이드바 collapse/expand toggle.
- 다중 모니터 cross-machine 동기화.

### 15.4 Default width 자동 계산

- 시점: 빌드 타임 정적 계산 (i18n 키 사전 등록되어 있으므로 가능).
- 방법:
  1. 빌드 스크립트 `scripts/compute-sidebar-width.mjs` 신규.
  2. 입력: `src/i18n/locales/{ko,en}.json` 의 `phaseC.subSteps.*`, `mame.subSteps.*` 키 전체.
  3. canvas 2D `measureText` 또는 폰트 메트릭 룩업으로 픽셀 너비 추정 (font: 14 px, weight 500).
  4. 추가 패딩 (badge 20 px + 좌우 padding 24 px) 합산.
  5. 모든 레이블 최댓값 → `src/lib/sidebar-default-width.ts` 에 상수로 emit.
  6. 보수 fallback 240 px (스크립트 실패 시).

- 런타임 fallback: `useEffect` 에서 실제 DOM `getBoundingClientRect` 로 재측정 후 store 의 `computedDefault` 갱신.

### 15.5 Drag handle 구현

- AppShell `<aside>` 우측 끝에 4 px 너비 `<div role="separator" aria-orientation="vertical" aria-valuenow={width} aria-valuemin={180} aria-valuemax={480}>` 배치.
- 핸들 mousedown → document mousemove 리스너 → `width = e.clientX - aside.left` 계산 후 clamp.
- mouseup 시 리스너 해제 + store persist.
- 키보드 접근: `ArrowLeft/Right` 1 px, `Shift+Arrow` 10 px 조정. `Home/End` 로 min/max.
- 호버 시 핸들 시각화 (`bg-border` → `bg-primary` 색상 전환).
- 드래그 중 `cursor: col-resize` + `user-select: none` 전역 적용 (드래그 종료 시 해제).

### 15.6 상태 관리 — `layoutSlice`

신규 파일 `src/store/slices/layoutSlice.ts`:

```ts
export interface LayoutSlice {
  sidebarWidth: number | null;   // null = use computedDefault
  computedDefault: number;        // runtime-measured, default 240
  setSidebarWidth: (w: number | null) => void;
  setComputedDefault: (w: number) => void;
}
```

- `useAppStore` (kuro) 와 `useMameAppStore` (mame) 양쪽 같은 store 슬라이스 참조 — 이미 두 store 가 분리되어 있으므로 슬라이스 정의 1회 + 양쪽 inject.
- persist 미들웨어 `zustand/middleware` 의 `persist` 로 localStorage 키 `kuma.layout.v1` 자동 저장.
- partial persist: `sidebarWidth` 만 저장. `computedDefault` 는 매 빌드 결과 채택.

### 15.7 AppShell 변경

- `<aside>` 에 inline style `{ width: sidebarWidth ?? computedDefault }` 적용.
- 기존 `shrink-0 flex-col` 유지. `width` 명시로 flex shrink 무관.
- 핸들 `<ResizeHandle />` 신규 컴포넌트로 분리 (`src/components/shell/ResizeHandle.tsx`).
- AppShell prop 으로 `disableResize?: boolean` 추가 — 향후 PlateView 등에서 비활성화 가능.

### 15.8 테스트

- `AppShell.test.tsx`
  - 초기 렌더 시 width = computedDefault.
  - mousedown → mousemove → width 변경, store 갱신.
  - mouseup 시 localStorage 키 존재 확인.
  - min/max clamp 확인.
  - 키보드 ArrowLeft/Right 동작 확인.
- `layoutSlice.test.ts`
  - localStorage 모킹 후 persist round-trip.
  - `setSidebarWidth(null)` 시 default 로 복귀.
- `compute-sidebar-width.test.mjs`
  - 알려진 레이블 셋 → 예상 너비 ±10 px.

### 15.9 i18n / 접근성

- 핸들 `aria-label`: `t("appShell.sidebarResize")` — ko: "사이드바 너비 조절", en: "Resize sidebar".
- 키보드 단축키 안내 tooltip (`title` 속성).

### 15.10 마이그레이션

- localStorage 미존재 사용자 = 자동 default 적용 (마이그레이션 불필요).
- 기존 사용자도 동일 — 신규 키이므로 충돌 없음.

### 15.11 헌장 / 룰 체크리스트

- [필수] A11y — `role="separator"`, `aria-orientation`, `aria-valuenow/min/max`, 키보드 조작.
- [필수] Settings — `sidebarWidth` 가 store 영구화.
- [필수] Performance — drag mousemove 는 `requestAnimationFrame` 으로 throttle.
- [필수] Cross-platform — Tauri webview (Chromium 기반) macOS/Windows/Linux 일관 동작.
- [권장] UI Safety — drag 도중 다른 마우스 이벤트 차단 (`pointer-events: none` 메인 영역).

### 15.12 미확정 / 추후 검증

- canvas `measureText` 와 실제 DOM 렌더링 사이의 픽셀 오차 허용 범위 (현재 ±5 px 가정).
- 폰트 로드 전 (FOUT) computed width 가 부정확할 수 있음 → `document.fonts.ready` 대기 후 재측정 필요한지 확인.
- 사이드바 hide/show toggle 은 후속 PR — store 슬라이스에 `sidebarVisible` 자리는 미리 비워둘지.

### 15.13 관련 파일 (cross-layer group 추가)

`.cross-layer-sync.json` `groups[]` 에 추가:

```json
{
  "id": "sidebar-resize-flow",
  "files": [
    "src/components/shell/AppShell.tsx",
    "src/components/shell/ResizeHandle.tsx",
    "src/store/slices/layoutSlice.ts",
    "src/lib/sidebar-default-width.ts",
    "scripts/compute-sidebar-width.mjs"
  ],
  "note": "Sidebar default width 계산 ↔ store ↔ AppShell 렌더 정합성",
  "severity": "warning"
}
```
