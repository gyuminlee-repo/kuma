## Verification Report — Phase 4 (UI Unification)
검증일: 2026-04-27

### Acceptance Criteria (계획서 §8 Phase 4 범위)

| # | 항목 | AC | 판정 | 근거 |
|---|------|-----|------|------|
| 1 | StateView 실 적용 | 표·시퀀스뷰어·플레이트맵·Verdict에 empty/error StateView 호출 | PASS | ResultTable L129-150, SequenceViewer L523, PlateMap L220, VerdictTable L216-226 StateView import & 호출 확인 |
| 2 | Dialog 폭 정정 | ExportDialog max-w-2xl, ClearConfirm max-w-sm | PASS | ExportDialog L34, ClearConfirmDialog L20, AppLayout L230 확인 |
| 3 | Destructive 제거 | variant="destructive" 0건 → outline+text-error | PASS | 4개 파일(AppLayout, Sidebar, ClearConfirmDialog, 기타) destructive 0건; outline+text-error 조합 사용 확인 |
| 4 | VerdictBadge 도형+색 | 각 상태별 도형 prefix (●/■/▲/◆) + 색 동반 | PASS | VerdictBadge L12-43 meta 정의에 shape+colorClass 함께 정의, L62-63 렌더링 확인 |
| 5 | 도메인 토큰 | --text-plate, --text-plate-tiny 정의 + tailwind 매핑 + WellPlate 사용 | PASS | index.css L80-81, tailwind.config.js L27-28, WellPlate L103/117/119 사용 |
| 6 | 임의 px 제거 (Phase 4 파일) | 9개 Phase 4 대상 파일 text-[/h-[/rounded-[/w-[ 0건 | PASS | grep -rE "text-\[|h-\[|rounded-\[|w-\[" → 0건 |
| 7 | ErrorBoundary alert role | StateView error variant에서 role="alert" 자동 부여 | PASS | StateView L33 조건부 렌더링 `role={variant === "error" ? "alert" : undefined}` |
| 8 | tsc --noEmit | TypeScript 컴파일 성공 | PASS | tsc --noEmit → "TypeScript compilation completed" |
| 9 | 동작 보존 | Cancel/Clear/Export 버튼 onClick, 표 렌더링 경로 유지 | PASS | ClearConfirmDialog L28/35, ExportDialog L58/94/99, ResultTable L173 onClick 존재 |
| 10 | 이월 항목 정직성 | resultTableColumns.tsx 등 Phase 5 이월 파일의 임의 px 존재 여부 | FAIL | resultTableColumns.tsx, InputPanel.tsx 등에 임의 px 60건 존재. resultTableColumns는 "표 행/badge" Phase 4 범위이나 미수정. |

### 검증 상세

#### V1. StateView 실 적용
- ResultTable: empty/error variants 호출 (L129, L150)
- SequenceViewer: empty variant 호출 (L523)
- PlateMap: empty variant 호출 (L220)
- VerdictTable: empty/no-match variants 호출 (L216, L222)
모두 import + 조건부 렌더링 확인.

#### V2. Dialog 폭 정정
- ExportDialog: `max-w-2xl` ✓
- ClearConfirmDialog: `max-w-sm` ✓
- AppLayout Clear: `max-w-sm` ✓
계획서 §6.7 3단계 분류 준수.

#### V3. Destructive 제거
- AppLayout.tsx: `variant="destructive"` 0건
- Sidebar.tsx: `variant="destructive"` 0건
- ClearConfirmDialog.tsx: `variant="destructive"` 0건
대신: `variant="outline"` + `className="text-error border-error/40 hover:bg-error/8"`

#### V4. VerdictBadge 도형+색
```tsx
const verdictMeta: Record<VerdictClass, VerdictMeta> = {
  PASS: { label: "Pass", colorClass: "border-success/40 text-success", shape: "●" },
  AMBIGUOUS: { shape: "■" },
  WRONG_AA: { shape: "▲" },
  FRAMESHIFT: { shape: "▲" },
  MANY: { shape: "■" },
  LOWDEPTH: { shape: "◆" },
};
```
렌더링: `{showDot && <span aria-hidden="true">{meta.shape}</span>}`

#### V5. 도메인 토큰
index.css:
```css
--text-plate: 10px;
--text-plate-tiny: 8px;
```

tailwind.config.js:
```js
fontSize: {
  plate: "var(--text-plate)",
  "plate-tiny": "var(--text-plate-tiny)",
}
```

WellPlate.tsx 사용:
- L103: `text-plate font-medium`
- L117: `text-plate font-semibold`
- L119/125/133: `text-plate-tiny`
임의값(`text-[10px]`, `text-[8px]`) 0건.

#### V6. 임의 px (Phase 4 파일)
검색 대상 9개 파일:
- src/components/widgets/ResultTable.tsx
- src/components/widgets/SequenceViewer.tsx
- src/components/widgets/PlateMap.tsx
- src/components/ui/StateView.tsx
- src/components/mame/widgets/VerdictBadge.tsx
- src/components/mame/widgets/VerdictTable.tsx
- src/components/mame/widgets/WellPlate.tsx
- src/components/mame/dialogs/ExportDialog.tsx
- src/components/mame/dialogs/ClearConfirmDialog.tsx
- src/components/layout/AppLayout.tsx

결과: 0건

#### V7. ErrorBoundary alert role
StateView.tsx L33:
```tsx
<div role={variant === "error" ? "alert" : undefined} ...>
```

#### V8. TypeScript 컴파일
`npx tsc --noEmit` 성공.

#### V9. 동작 보존
모든 onClick 핸들러, 표 정렬 로직, Export 폼 파이프라인 유지.

#### V10. 이월 항목 정직성 ❌
Phase 5로 이월한다고 명시한 파일들의 상태:

```
src/components/popovers                  → 디렉토리 미존재 (이월 대상 재확인 필요)
src/components/widgets/resultTableColumns.tsx    → 임의 px 8건 (text-[8px], text-[10px] 등)
src/components/mame/panels/InputPanel.tsx        → 임의 px 6건 (text-[11px], text-[10px] 등)
src/components/mame/panels/ParameterPanel.tsx    → 임의 px 3건
src/components/panels/InputPanel/*              → 임의 px 43건
```

총 60건의 임의 px.

**문제점**:
- `resultTableColumns.tsx`는 "표 행/badge 정의" (계획서 §8 Phase 4 범위)이나 미수정
- Phase 5로 이월한다는 명시적 보고가 없음 (파일 목록만 제시될 수 있음)
- 일부 임의 px는 토큰화 가능한 값들 (예: `text-[11px]` → 없음, `text-[10px]` → `text-plate`)

### Grading Criteria

| # | 기준 | 점수 | 근거 |
|---|------|------|------|
| 1 | StateView 실 적용 정합성 | 5 | 4개 파일 모두 정확한 위치에서 호출, import 유지 |
| 2 | 토큰 시스템 정합성 | 5 | 16종 토큰 정의, Tailwind 매핑, 도메인 토큰(plate/plate-tiny) 신설 + 사용 |
| 3 | 스타일 규칙 준수 | 5 | destructive 제거, outline+text-error 조합, 도형+색 동반 |
| 4 | TypeScript 안정성 | 5 | tsc 0 error |
| 5 | Phase 4 범위 완성도 | 2 | **AC 항목 1-9는 모두 PASS이나, resultTableColumns.tsx의 임의 px 미처리가 차단 요인** |

하드 임계값 미달: 기준 #5가 2점 이하 → **전체 FAIL**

### 최종 판정: **FAIL**

**실패 항목**:
- V10: 이월 대상 파일(`resultTableColumns.tsx`)의 임의 px 미제거 (60건 잔존)

**차단 사유**:
- resultTableColumns.tsx는 계획서 §8 Phase 4 "표 행/badge 통일"에 포함되는 파일이나, 8건의 임의 px (`text-[8px]`, `text-[10px]` 등)가 남아있음
- 이월 정당성 문서 부재: Phase 5로 연기한다는 명시적 설명이 없음
- 토큰화 가능 값들이 임의값으로 남아있음 (예: `text-[10px]` → `text-plate` 토큰으로 치환 가능)

**복구 조건**:
1. resultTableColumns.tsx의 임의 px 8건을 토큰(text-caption, text-plate, text-plate-tiny 등)으로 치환
2. InputPanel 시리즈와 panels/InputPanel 40+건도 동일 기준 적용 또는 Phase 5 이월 근거 명시
3. 또는 계획서 수정 (resultTableColumns.tsx를 명시적으로 Phase 5 이월 목록에 추가)
