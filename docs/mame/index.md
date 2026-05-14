# MAME — Major.Sub 워크플로우

MAME 는 3개 major step 으로 구성되며, 각 major 는 하위 sub-step 을 가진다. KURO 의 단일 1..6 카운트와 달리 **Major.Sub 계층 표기** (`1.1`, `1.2`, `2.1`, `2.2`, `3.1`, `3.2`) 를 쓴다.

```
1. Run Setup
   1.1 Files & Coordinates
   1.2 Expected Mutations
2. Sequencing Review
   2.1 Verdict + Plate
   2.2 Per-plate verdict bar    (NGS 효율 그래프)
3. Activity Data
   3.1 Ingest
   3.2 Merge & Export
```

<!-- TODO: insert screenshot of MAME rail with Major.Sub labels -->

## 표기 위치

- WizardContainer header: `Step 1.1: Files & Coordinates`
- Sidebar rail: major 굵게 (`1. Run Setup`), sub 들여쓰기 (`  1.1 Files & Coordinates`)
- Footer progress: `Step 1.1 / 2.2`

## v0.9.2.x 변경

- Sidebar 자유 navigate: 1.1 → 3.2 어떤 sub-step 이든 즉시 클릭 이동.
- 빈 화면 fallback 제거. step 별 default 경로가 모두 empty-state 메시지로 처리됨.
- 2.1/2.2 통합 review sub-step + per-plate verdict bar (PPT slide 6 의 NGS 효율 그래프) — **Task #12 구현 진행 중**.

자세한 step 설명은 좌측 메뉴.
