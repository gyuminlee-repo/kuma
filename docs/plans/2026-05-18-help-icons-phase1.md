# ? Help Icons Phase 1 구현 계획

> **Status: completed** (구현 머지 PR #13, v0.9.9.1)

**목표:** kuro/mame 핵심 파라미터·섹션에 ? 도움말 아이콘 ~40개 추가 (en + ko)

**아키텍처:** 기존 `src/components/ui/InlineHelp.tsx` 100% 재사용. 컴포넌트 신규 0. Label 옆에 `<InlineHelp text={t("...Help")} />` 패턴 반복. i18n 키만 80개(40 × 2 언어) 추가.

**기술 스택:** React, react-i18next, 기존 shadcn

**근거 문서:** [source: docs/design/2026-05-18-echo-janus-export-preview-help-icons.md]

**적용 범위 (Phase 1, ~40)**:
- Mame 파라미터 12: targetAmpliconLength, lengthTolerance, minQscore, minBarcodeScore, trimAdapters, universalRevPrimer, normalizeHeaders, legacyKb, minFilteredDepth, 외 3
- Kuro 파라미터 25: tmFwd, tmRev, tmOverlap, tmTolerance, gcMin, gcMax, primerLengthMin, primerLengthMax, randomSeed, codonStrategy, polymerase, 외 14
- 섹션 헤더 3: Bimodal Distribution, Demux Progress, 외 1 비자명 헤더

---

## 파일 구조

### 수정
| 파일 | 변경 |
|---|---|
| `src/locales/en.json` | `parameterPanel.*Help` 25 + `mame.parameters.*Help` 12 + `{area}.*Description` 3 = +40 키 |
| `src/locales/ko.json` | 동일 40 키 ko 번역 |
| `src/components/mame/panels/ParameterPanel.tsx` | 12개 Label에 `<InlineHelp text={t(".Help")} />` 추가 |
| `src/components/panels/ParameterPanel.tsx` (kuro) | 25개 Label에 `<InlineHelp text={t(".Help")} />` 추가 |
| 섹션 헤더 3개 파일 (BarcodeSetupPanel, RoundSummaryPanel 등) | 헤더 옆 `<InlineHelp>` 추가 |

### 변경 없음
- `src/components/ui/InlineHelp.tsx` (재사용)
- 백엔드, Rust, 다른 8 언어 locale

---

## 사전 작업 (Task 0)

`@editor` 또는 PI 검수 권장. 본 계획은 개발자 초안 텍스트로 진행, follow-up PR에서 PI 검수 반영.

- [ ] **Step 0-1: 적용 대상 40개 정확히 인벤토리**

`docs/plans/help-icons-phase1-targets.md` (worktree-local) 작성:
- 파일 경로:line 단위로 각 Label 위치 + 신규 i18n 키명 + en/ko 초안 텍스트
- 형식: 표 (Area | File:Line | Field | KeyName | en | ko)

이 인벤토리가 Task 2-5의 입력. 직접 만들거나 grep으로 자동 수집.

- [ ] **Step 0-2: 커밋**: `git add docs/plans/help-icons-phase1-targets.md && git commit -m "vX: phase1 help-icon target inventory"`

---

## Task 1: i18n 키 추가 (en + ko 일괄)

**파일:** 수정 `src/locales/en.json`, `src/locales/ko.json`

- [ ] **Step 1-1: parity 사전 체크**: `node scripts/i18n-parity.mjs 2>&1 | tail -10` 현재 상태 baseline 기록
- [ ] **Step 1-2: en.json에 40 키 추가**

키 위치는 inventory 표 따름. 패턴:
```json
// src/locales/en.json
{
  "parameterPanel": {
    "tmFwdHelp": "Target melting temperature for forward primers. Default 60°C. Lower values increase mismatch tolerance.",
    "tmRevHelp": "Target melting temperature for reverse primers. Should match tmFwd for balanced PCR.",
    "gcMinHelp": "Minimum GC content (%) for primer regions. Recommended ≥40 to avoid weak binding.",
    "gcMaxHelp": "Maximum GC content (%). Above 65 increases hairpin and primer-dimer risk.",
    "primerLengthMinHelp": "Shortest acceptable primer length (nt). Typical range 18-22 for SDM."
    // ... 25 entries
  },
  "mame": {
    "parameters": {
      "targetAmpliconLengthHelp": "Expected amplicon length in bp. Reads outside ± lengthTolerance are filtered.",
      "lengthToleranceHelp": "Allowed deviation from targetAmpliconLength (bp).",
      "minQscoreHelp": "Minimum mean Q-score for read inclusion. Phred Q20 = 99% accuracy."
      // ... 12 entries
    }
  }
}
```

- [ ] **Step 1-3: ko.json에 동일 40 키 ko 번역**

```json
{
  "parameterPanel": {
    "tmFwdHelp": "Forward 프라이머의 목표 melting temperature. 기본 60°C. 낮을수록 mismatch 허용.",
    "gcMinHelp": "프라이머 영역 최소 GC content (%). 약한 결합 방지 위해 ≥40 권장."
    // ...
  }
}
```

용어: PCR/Tm/GC/melting temperature 등 학계 통용 영문 유지 (locale rule 메모리 참조). UI 자연어만 한국어.

- [ ] **Step 1-4: JSON 유효성**: 
  - `python3 -m json.tool src/locales/en.json > /dev/null && echo OK_en`
  - `python3 -m json.tool src/locales/ko.json > /dev/null && echo OK_ko`

- [ ] **Step 1-5: i18n parity 체크**: `node scripts/i18n-parity.mjs 2>&1 | tail`. 
  - 다른 8 언어가 fallback으로 처리되는지 확인.
  - parity가 strict-equal 강제하면 8 언어 파일에도 40 키를 영문 그대로 복사 필요. lint 결과 따라 분기.
  
- [ ] **Step 1-6: 만약 strict parity 필요**:
  - 자동화 스크립트 작성 또는 수동: `jq` 또는 Python으로 en.json의 새 키들을 다른 8개 파일에 복사 (값 그대로)
  - 다시 parity 통과 확인

- [ ] **Step 1-7: 커밋**: `git add src/locales/*.json && git commit -m "vX: add 40 phase1 help i18n keys (en+ko, others fallback)"`

---

## Task 2: Mame ParameterPanel InlineHelp 12개 적용

**파일:** 수정 `src/components/mame/panels/ParameterPanel.tsx`

- [ ] **Step 2-1: 기존 패턴 확인**: 파일에서 이미 적용된 9개 InlineHelp 위치 grep으로 확인 (`rg -n "InlineHelp" src/components/mame/panels/ParameterPanel.tsx`)

- [ ] **Step 2-2: 미적용 12개 Label에 추가**

패턴:
```tsx
<Label htmlFor="target-amplicon-length">
  <span className="inline-flex items-center gap-1.5">
    {t("mame.parameters.targetAmpliconLength")}
    <InlineHelp text={t("mame.parameters.targetAmpliconLengthHelp")} />
  </span>
</Label>
```

inventory(Task 0)의 12개 field 각각 위 패턴 적용.

- [ ] **Step 2-3: import 확인**: 파일 상단 `import { InlineHelp } from "@/components/ui/InlineHelp";` 이미 있으면 OK.

- [ ] **Step 2-4: typecheck**: `npx tsc --noEmit 2>&1 | tail -10` 0 errors

- [ ] **Step 2-5: 시각 확인**: 가능하면 dev 서버 후 mame ParameterPanel 진입 (WSL GUI 미지원 시 스킵, 사용자 확인 위임)

- [ ] **Step 2-6: 커밋**: `git add src/components/mame/panels/ParameterPanel.tsx && git commit -m "vX: add 12 InlineHelp to mame parameters"`

---

## Task 3: Kuro ParameterPanel InlineHelp 25개 적용

**파일:** 수정 `src/components/panels/ParameterPanel.tsx` (kuro 측 정확한 파일은 Task 0 inventory에서 확인)

- [ ] **Step 3-1: 기존 5개 위치 확인**
- [ ] **Step 3-2: 미적용 25개 Label에 패턴 적용** (Task 2와 동일 구조, 다만 i18n prefix `parameterPanel.`)
- [ ] **Step 3-3: typecheck** 0 errors
- [ ] **Step 3-4: 커밋**: `git add src/components/panels/ParameterPanel.tsx && git commit -m "vX: add 25 InlineHelp to kuro parameters"`

---

## Task 4: 섹션 헤더 3개에 InlineHelp 추가

**파일:** inventory에서 식별된 3개 헤더 파일 (예: BarcodeSetupPanel.tsx, RoundSummaryPanel.tsx 등)

- [ ] **Step 4-1: 각 헤더 옆 추가**

```tsx
<h3 className="...">
  <span className="inline-flex items-center gap-1.5">
    {t("area.sectionTitle")}
    <InlineHelp text={t("area.sectionTitleHelp")} />
  </span>
</h3>
```

- [ ] **Step 4-2: typecheck** 0 errors
- [ ] **Step 4-3: 커밋**

---

## Task 5: 통합 검증

- [ ] `npx tsc --noEmit` 0 errors
- [ ] `node scripts/i18n-lint.mjs` 통과 (하드코딩 한국어 0)
- [ ] `node scripts/i18n-parity.mjs` 통과
- [ ] `npx vitest run --reporter=basic 2>&1 | tail -20` 기존 테스트 회귀 0 (InlineHelp는 visual addition이므로 logic 영향 없음)
- [ ] `git diff --stat` 예상: locale 2 + 컴포넌트 5 = 7개 파일, ~250줄 추가

---

## 검증 기준 (karpathy-guidelines)

- **가정 명시**: InlineHelp는 클릭형 포퍼 (이미 14개 위치에서 검증). PI 검수 텍스트는 follow-up.
- **최소 코드**: 기존 컴포넌트 재사용, 신규 컴포넌트 0.
- **변경 범위 제한**: Phase 1만. Phase 2(액션 버튼 15) + Phase 3(탭/다이얼로그 10)은 별도 plan/PR.
- **검증 기준**: Task 5 모든 항목 PASS.

---

## Risks 점검

- i18n parity 정책이 strict면 8 언어 일괄 영문 복사 필요. Task 1-6 분기로 대응.
- InlineHelp 텍스트 정확성: 개발자 초안이라 PI 검수 후 텍스트 수정 follow-up PR 필요.
- ParameterPanel.tsx가 길어 InlineHelp 12+25 추가가 가독성에 영향. 필요 시 별도 컴포넌트 (LabelWithHelp) 추출 follow-up, Phase 1 범위 외.
- inventory(Task 0)가 정확하지 않으면 작업 누락. Task 0 시간 충분히 투자.

---

## Confidence Check

| 축 | 점수 | 비고 |
|---|---|---|
| Completeness | 4/5 | inventory(Task 0)가 정확해야 40개 모두 매핑. 사전 작업 의존 |
| Clarity | 5/5 | 패턴 단순, 반복 작업 |
| Feasibility | 5/5 | InlineHelp 이미 검증, i18n 키 추가는 표준 |

총 14/15. 진행 가능. Phase 2/3는 동일 패턴으로 별도 PR.
