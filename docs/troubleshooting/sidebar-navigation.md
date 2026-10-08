# Sidebar Navigation 정책

## 증상

"sequence 를 안 넣었더니 mutation step sidebar 가 막혀 있다", "탭간 이동이 안 된다" 등.

## v0.9.2.05 / .09 패치 결정

**Sidebar 클릭은 항상 자유**. Next 버튼만 validation 으로 차단한다.

| 경로 | 정책 |
|---|---|
| Sidebar / 탭 클릭 | 항상 즉시 navigate. prerequisite 미충족이어도 진입 허용 |
| Next 버튼 (linear) | `validateBeforeNext` 로 missing input Dialog 표시 → navigation 차단 |

## 빈 화면 fallback

prerequisite 미충족 step 에 진입하면 빈 화면이 아니라 empty-state 메시지가 표시된다.

| Step | empty state |
|---|---|
| KURO mutation | "Load sequence first" |
| KURO params | "Load sequence first" |
| MAME 1.2 | "Reference FASTA required" |
| MAME 2.x | "Expected mutations xlsx required" |
| MAME 3.x | "Ingest activity data first" |

## 구현 위치

- `src/components/layout/WorkflowRail.tsx` (KURO) — click handler 의 prerequisite guard 제거.
- `src/components/mame/MameWorkflowRail.tsx` — 동일.
- 각 sub-step view 의 `default: return null` → empty state 컴포넌트로 교체.
- `WizardContainer` 의 `validateBeforeNext` props 가 모든 wizard step 에 채워짐.

## 보존되는 guard

- destructive action 확인 Dialog
- Next 버튼의 `validateBeforeNext`

단순 navigation 차단은 모두 제거되었다.
