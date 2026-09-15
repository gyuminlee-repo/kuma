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

Janus 장비 설정은 v0.15.12 에서 step 2.1 밖으로 나와 자체 major step 3 이 되었다. Activity 는 4.x 로 밀렸다. 시퀀싱 판정만 필요한 운용자가 쓰지 않을 로봇 설정을 지나치지 않도록 한 분리이며 step 3 은 어떤 실행도 막지 않는다.

## step 3 (v0.16.1 기준)

실행이 스스로 쓰는 Janus 파일은 선정 클론 pick 목록(`..._picks.csv`) 하나다. 로봇이 읽는 8열 매핑 시트(`..._janus.csv`)는 step 3 의 export 를 눌렀을 때만 만들어진다. 로봇 시트는 deck 을 적는 파일이고 이 값은 export 시점의 실험실 상태를 진술하므로 재실행마다 자동으로 다시 쓰지 않는다. 두 rack 열에는 deck 번호가 아니라 플레이트 이름이 들어가고 liquid class 열은 없다.

step 3 화면에서 다이얼로그가 사라졌다. "Janus 장비 설정 열기" 버튼과 팝업 대신 같은 내용(volume, liquid class, sample type, 행 미리보기, 제외 클론, export 버튼)이 step 3 페이지에 인라인으로 펼쳐진다.

analyze 화면(2.x)에는 Janus 가 없다. 장비 설정도, 실행이 장비용 파일을 썼다는 안내도 step 3 에서만 나온다.

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
