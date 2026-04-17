# 빠른 시작

5단계로 첫 프라이머 설계.

### Step 0 — 실행

![초기 화면](../screenshots/01-initial.png)

Sidecar 기동 후 상태 표시줄에 **Ready** 표시.

### Step 1 — 서열 로드

![파일 로드 완료](../screenshots/02-file-loaded.png)

**Browse** 버튼 클릭, GenBank / SnapGene / FASTA 파일 선택. KURO가 longest ORF를 CDS 타깃으로 자동 감지.

### Step 2 — 변이 입력

![변이 입력 완료](../screenshots/03-mutations-entered.png)

한 줄당 하나(`Q232A`), 또는 **Load CSV**로 EVOLVEpro CSV 로드.

### Step 3 — 파라미터 확인

기본 Q5 폴리머레이즈, 코돈 전략 *Min. changes*, Mutations 95. 필요 시 Parameter 패널에서 조정.

### Step 4 — 설계

![설계 진행](../screenshots/10-designing.png)

**Design Primers** 클릭. 진행률 바가 단계별로 업데이트.

### Step 5 — 검토·내보내기

![설계 완료](../screenshots/04-design-complete.png)

전체 결과는 File → *Export Excel*, Echo/JANUS 인풋은 Plate Map의 **Export Mapping...** 클릭.

자세한 내용: [서열 로드](loading-sequences.md), [변이 입력](entering-mutations.md), [파라미터 패널](parameter-panel.md), [프라이머 설계](designing-primers.md).
