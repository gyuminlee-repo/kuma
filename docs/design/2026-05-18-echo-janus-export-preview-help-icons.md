# Spec: Echo/Janus Export Plate Preview + ? Help Icons Phase 1-3

Date: 2026-05-18
Author: brainstorming session
Scope: 2 independent features bundled (separate PRs if needed)

## Context

요청 2건.

**1.** Echo/Janus 매핑 미리보기를 Design Report 다이얼로그에서 빼고 KURO Export 탭 아래 독립 섹션으로 옮긴다. 텍스트 테이블이 아닌 **plate view** 시각화로. Echo는 384-well source + 96-well dest. Janus는 96-well 두 rack.

**2.** kuro/mame UI 구성요소에 ? 도움말 아이콘 광범위 도입. 기존 `InlineHelp` 컴포넌트가 이미 있고 14곳에서 쓰임. 후보 ~65개 (Mame 파라미터 12 + Kuro 파라미터 25 + 섹션 3 + 액션 버튼 10 + 상태 5 + 탭 10). en+ko 두 언어만 추가, 나머지 8개 언어는 영문 fallback.

## Plate Format Reference (확정)

| 시스템 | Source | Dest | row 규약 |
|---|---|---|---|
| Echo 525 | 384-well (16×24, A-P × 01-24) | 96-well (8×12) | source rows: odd(A,C,E,G,I,K,M,O) = fwd, even(B,D,F,H,J,L,N,P) = rev |
| JANUS | 96-well Rack 1 = fwd | 96-well Rack 2 (dest) | rack 분리, row split 없음 |

근거: 옵시디언 `weekly_260417_gyumin.md:33`, `260428_mame_PPTX_gap_analysis.md:113-122`, 코드 `kuma_core/kuro/plate_mapper.py:507-544,582-585,656-659`.

Echo dry-run row (`python-core/sidecar_kuro/handlers/export.py:605-668`):
- source_plate, source_well_name, source_well (384 format A01), dest_plate, dest_well_name, dest_well (96 format A1), transfer_vol (nL, split if >100)

Janus dry-run row (`:671-720`):
- name (-fw|-rv), type, dsp_rack_label, no, asp_rack(1|2), asp_posi (96 A1), dsp_rack(2), dsp_posi (96 A1), volume (µL)

## Architecture, Feature 1 (Echo/Janus Plate Preview)

### Components

```
src/components/widgets/EchoPlateView.tsx (NEW, 384-well 전용)
  ├── 16 rows (A-P) × 24 cols (1-24)
  ├── props: { sourceRows: EchoRow[], destRows: EchoRow[] (optional), highlightFwdRev: boolean (default true) }
  ├── 시각화: odd row 옅은 파랑 stripe (fwd), even row 옅은 주황 stripe (rev)
  ├── 셀 hover tooltip: source_well_name, dest_well, transfer_vol (nL)
  ├── source plate + dest plate 좌우 PanelGroup. dest는 96-well이므로 기존 WellPlate 재사용

src/components/widgets/JanusPlateView.tsx (NEW, 96-well 2-rack 표시)
  ├── 기존 WellPlate 2개를 좌우 배치 (Rack 1 = fwd, Rack 2 = dest)
  ├── props: { rack1Rows: JanusRow[], rack2Rows: JanusRow[] }
  ├── 셀 hover tooltip: name, volume (µL)

src/components/widgets/ExportPlatePreview.tsx (NEW, kuro Export tab section)
  ├── 탭 전환 (Echo | JANUS), 둘 다 한 화면에 보이는 토글
  ├── 마운트 시 dry-run RPC 자동 호출 (auto load on tab open)
  ├── 로딩/에러 state, 빈 상태 ("No mapping yet")
```

### Backend (변경 없음)

Echo/Janus dry-run RPC 핸들러는 그대로 유지 (`handle_export_echo_mapping_dry_run`, `handle_export_janus_mapping_dry_run`). 응답 row 형식도 변경 없음. 프론트에서 row → cell 매핑 어댑터만 추가.

### Removal: Design Report 기존 미리보기

`src/components/dialogs/DesignReportContent.tsx:405-486` 영역 (Echo + JANUS 두 테이블 + state echoPreview/janusPreview + 자동 RPC 호출 L101-104) 전부 제거. 관련 import 정리.

### KURO Export 탭 진입점 (메인 최상단)

`src/components/steps/ExportStepView.tsx:33-36`의 `<div className="space-y-6">` 최상단에 `<ExportPlatePreview />` 삽입. 순서: ExportPlatePreview → ExportFormatSelector → OrderSummary.

근거: Inspector(320px 고정)는 384-well plate(최소 500-700px) 강제 가로 스크롤. 메인 WizardContainer는 maxWidth="4xl"(~896px)로 충분. 사용자 동선 "설정 입력 → mapping 시각화 확인 → Summary → Export" 자연스러움. Output step도 메인에 시각화 두는 일관 패턴.

`src/components/inspectors/kuro/ExportInspector.tsx`는 변경 없음 (정보 표시 전용 유지).

### 데이터 흐름

```
ExportPlatePreview mount
  ↓ invoke("export_echo_mapping_dry_run") + invoke("export_janus_mapping_dry_run")
  ↓ 응답: rows[] (EchoRow / JanusRow)
  ↓ adapter: rows → WellCell 좌표 + tooltip data
  ↓ EchoPlateView / JanusPlateView 렌더
```

### Error Handling

- RPC 실패 시 inline 에러 메시지 ("Failed to load Echo mapping preview: {err}") + 재시도 버튼
- 빈 결과 (디자인 결과 없음) 시 empty state ("Design primers first to see mapping preview")
- 일부만 실패 (Echo OK, Janus FAIL) 시 각각 독립 표시

### Testing

- `EchoPlateView.test.tsx`: 384 cell 렌더, fwd/rev stripe 색 검증, row 매핑 (예: A01은 row A col 01) snapshot
- `JanusPlateView.test.tsx`: 2 rack 좌우 배치, well 좌표 매핑
- `ExportPlatePreview.test.tsx`: mount 시 RPC 호출, 빈 응답 → empty state, 에러 응답 → 재시도 UI

## Architecture, Feature 2 (? Help Icons Phase 1-3)

### 컴포넌트 (재사용)

`src/components/ui/InlineHelp.tsx` 그대로 사용. 신규 컴포넌트 없음. 호출 패턴:

```tsx
<Label htmlFor="x">
  <span className="inline-flex items-center gap-1.5">
    {t("section.fieldLabel")}
    <InlineHelp text={t("section.fieldLabelHelp")} />
  </span>
</Label>
```

### 적용 대상 (~65)

**Phase 1 (~40, 가장 체감 큰 영역)**:
- Mame 파라미터 12: `targetAmpliconLength`, `lengthTolerance`, `minQscore`, `minBarcodeScore`, `trimAdapters`, `universalRevPrimer`, `normalizeHeaders`, `legacyKb`, `minFilteredDepth`, 외 3
- Kuro 파라미터 25: `tmFwd`, `tmRev`, `tmOverlap`, `tmTolerance`, `gcMin`, `gcMax`, primer length min/max, `randomSeed`, codon strategy, polymerase 등
- 섹션 헤더 3: Bimodal Distribution, Demux Progress 등 비자명 헤더

**Phase 2 (~15)**:
- 고급 액션 버튼 10: Re-demux, Apply Recommended, Use Cutoff 등
- 상태 배지/카드 5: confidence high/medium/low 의미

**Phase 3 (~10)**:
- 탭 트리거 detail (기존 `title=` 속성을 InlineHelp로 격상)
- 다이얼로그 헤더 일부

### i18n

- en + ko 두 언어만 추가. 나머지 8 언어(de, es, fr, ja, pt-BR, ru, zh-CN, zh-TW)는 i18n 라이브러리의 영문 fallback에 의존.
- 키 네이밍: `{area}.{fieldName}Help` (예: `mame.parameters.minFilteredDepthHelp`, `parameterPanel.tmFwdHelp`)
- 추가 키 수: 65 × 2 = 130 (en, ko 각각)
- 톤: 짧은 1-2문장. 권장값/범위/효과를 핵심만. 외부 링크는 필요 시 마크다운 inline link (e.g. `[Tm 계산 설명](docs/tm.md)`)

### 단계별 PR 분리 권장

Phase 1, 2, 3을 각각 별도 PR로. Phase 1만 먼저 머지하면 사용자 즉시 체감, 나머지는 follow-up. 단 사용자가 한 번에 다 원하면 하나의 PR로 묶어도 됨 (선호도 따라).

### Testing

- 각 Phase별 i18n parity 체크 (`scripts/i18n-parity.mjs`): en/ko 키 추가 시 다른 8 언어는 변경 없음 또는 동일 키 자동 fallback 처리되는지 lint 통과 확인
- 단위 테스트: 변경된 컴포넌트들에 InlineHelp 마운트 검증 (스냅샷 정도면 충분)

## Component/File Map

신규:
- `src/components/widgets/EchoPlateView.tsx`
- `src/components/widgets/JanusPlateView.tsx`
- `src/components/widgets/ExportPlatePreview.tsx`
- `src/lib/echoJanusAdapter.ts` (dry-run row → plate cell 변환)

수정:
- `src/components/dialogs/DesignReportContent.tsx` (Echo/Janus 섹션 제거)
- `src/components/inspectors/kuro/ExportInspector.tsx` (ExportPlatePreview 삽입)
- 약 40개 컴포넌트 (Phase 1): Mame/Kuro 각 ParameterPanel, section header 컴포넌트
- 약 15개 컴포넌트 (Phase 2): action button 위치
- 약 10개 컴포넌트 (Phase 3): TabsTrigger, dialog headers
- `src/locales/en.json`, `src/locales/ko.json` (각 130 키 추가)

테스트 신규:
- `src/components/widgets/EchoPlateView.test.tsx`
- `src/components/widgets/JanusPlateView.test.tsx`
- `src/components/widgets/ExportPlatePreview.test.tsx`

변경 없음:
- `python-core/sidecar_kuro/handlers/export.py` (dry-run 핸들러)
- `src-tauri/*` (Rust 측 무관)

## Risks

- 384-well 렌더링이 좁은 inspector 패널에 들어가면 셀이 너무 작아질 수 있음. 최소 가로 폭 확보 (예: `min-w-[600px] overflow-x-auto`) 또는 별도 다이얼로그로 확대 보기 옵션.
- Design Report에서 Echo/Janus 빼면 기존 보고서 출력(PDF 등)에 미리보기가 빠짐. 사용자 확인 필요 (Design Report는 단순 디자인 결과 요약, mapping은 export 시점 관심사이므로 분리가 합리적).
- Phase 1-3 한 번에 65개 작업은 PR 크기 큼. 단계별 분리 또는 한 PR 모두 묶을지 추후 결정.
- en+ko만 추가 시 fallback이 영문이지만 i18n 라이브러리 설정에 따라 빈 문자열 또는 키 자체 노출 가능. parity 스크립트 통과 확인 필수.
- ExportInspector가 우측 inspector 패널이라 plate view가 좌측 메인 영역이 아닌 사이드에 들어감. 사용자가 "Export 탭 아래" 의도는 메인 영역 확장일 수도. UI 진입 위치 재확인 필요 (현 spec은 inspector 패널 가정).

## Verification Plan

1. `npx tsc --noEmit` 0 errors
2. `cd src-tauri && cargo check` 0 errors (백엔드 무변경이므로 통과)
3. `node scripts/i18n-parity.mjs` 통과 (en/ko 키 추가가 다른 언어 parity 깨지 않는지)
4. `node scripts/i18n-lint.mjs` 통과 (하드코딩 한국어 문자열 0)
5. `npm test -- --silent EchoPlateView JanusPlateView ExportPlatePreview` 통과
6. 수동 (사용자 측, WSL GUI 미지원): KURO 디자인 후 Export 탭 진입 → Echo/Janus plate 자동 로드 확인, fwd/rev stripe 색 확인, hover tooltip 확인
7. 수동: Design Report 다이얼로그 열어 Echo/Janus 섹션 사라진 것 확인
8. 수동: Phase 1 화면들 (Mame/Kuro ParameterPanel) ? 아이콘 클릭 → InlineHelp 포퍼 확인

## Open Items

- ExportInspector 우측 sidebar vs 메인 영역 확장 (사용자 재확인 필요)
- Phase 1-3 단일 PR vs 단계별 PR
- InlineHelp 텍스트의 실제 내용 작성자 (현재 개발자 작성 → PI 검수 권장)
- Janus 2-rack 표시에서 Rack 1/Rack 2 라벨 i18n 키 신규 추가 필요
- 384-well overflow 시 zoom/expand 옵션 도입 여부
