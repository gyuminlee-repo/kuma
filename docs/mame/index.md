# MAME — Major.Sub 워크플로우

MAME 는 4개 major step 으로 구성되며, 각 major 는 하위 sub-step 을 가진다. KURO 의 단일 1..6 카운트와 달리 **Major.Sub 계층 표기** (`1.1`, `2.1`, `2.2`, `3.1`, `4.1`) 를 쓴다. rail 이 세는 sub-step 은 6개이며, 정본은 `src/components/mame/layout/MameWorkflowRail.tsx` 의 `ALL_SUBSTEPS` 와 `SUBSTEP_DISPLAY` 다.

```
1. Barcode Setup
   1.1 Files & Coordinates
2. Analyze
   2.1 Inputs                 (실행 입력, Run/Validate)
   2.2 Review                 (verdict + plate + per-plate verdict bar)
3. Janus instrument settings
   3.1 Janus                  (선택 단계. 건너뛰어도 실행에 지장 없음)
4. Activity Data
   4.1 Ingest
   4.2 Signals                (merge + export 포함)
```

Janus 장비 설정은 v0.15.12 에서 step 2.1 밖으로 나와 자체 major step 3 이 되었고, Activity 는 4.x 로 밀렸다. 시퀀싱 판정만 필요한 운용자가 쓰지 않을 로봇 설정을 지나치지 않도록 한 분리이며, step 3 은 어떤 실행도 막지 않는다. 실행은 저장된 값만으로 `..._picks.csv` 와 `..._janus.csv` 를 스스로 쓴다.

<!-- TODO: insert screenshot of MAME rail with Major.Sub labels -->

## 표기 위치

- WizardContainer header: `Step 1.1: Files & Coordinates`
- Sidebar rail: major 굵게 (`1. Barcode Setup`), sub 들여쓰기 (`  1.1 Files & Coordinates`)
- Footer progress: `Step 1.1 / 4.2`

## v0.9.2.x 변경

- Sidebar 자유 navigate: 1.1 → 4.2 어떤 sub-step 이든 즉시 클릭 이동.
- 빈 화면 fallback 제거. step 별 default 경로가 모두 empty-state 메시지로 처리됨.
- 2.1/2.2 통합 review sub-step + per-plate verdict bar (PPT slide 6 의 NGS 효율 그래프) — **Task #12 구현 진행 중**.

자세한 step 설명은 좌측 메뉴.
