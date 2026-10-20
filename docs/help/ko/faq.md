# 자주 묻는 질문

KURO 와 MAME 를 쓰다 자주 막히는 지점을 모았다. 답마다 그 설정이나 안내가 나오는 화면을 적었다.

## KURO

### 1단계에서 FASTA 파일을 받지 않는다

KURO 는 CDS 주석으로 설계하는데 FASTA 에는 주석이 없다. 화면에는 `CDS annotation required. Use a GenBank (.gb/.gbk) or SnapGene (.dna) file.` 가 뜬다. GenBank 나 SnapGene 파일을 넣는다. [단계 1. 변이체 로드](kuro-01-load.md) 참고.

### 설계 개수가 96 에서 멈춘다

설계 한 번이 플레이트 한 장을 맡는다. 더 큰 값을 넣으면 `Design count limited to one plate of variants` 와 함께 96 으로 돌아간다. [단계 3. 프라이머 파라미터](kuro-03-params.md) 참고.

### 폴리머레이스를 바꿨더니 Tm 과 GC 값이 바뀌었다

프리셋을 고르면 Tm 목표와 GC 범위가 그 프리셋 값으로 덮어써진다. 손으로 정해 둔 값이 있었다면 다시 확인한다. [단계 3. 프라이머 파라미터](kuro-03-params.md) 참고.

### Run Design 이 `Sidecar is not ready` 를 띄운다

상태 표시줄의 재시도 버튼을 누르거나 앱을 다시 시작한다. [단계 4. 풀 필터 및 실행](kuro-04-submit.md) 참고.

### 결과 표에 `This workspace has no primer results` 가 뜬다

실행 뒤 설계 입력이 바뀌어 프라이머 결과를 버린 상태다. 안내에 시각과 개수가 나온다. 4단계에서 설계를 다시 돌린다. [단계 5. 요약](kuro-05-output.md) 참고.

### `wells exceed one 96-well plate.` 와 함께 내보내기 버튼이 꺼져 있다

결과 표에서 `Include` 를 풀어 96 개 이하로 줄인다. [단계 6. 내보내기](kuro-06-export.md) 참고.

### MAME 에 넘길 KURO 파일은 무엇인가

`..._platemap.xlsx` 다. 내보내기를 하면 항상 함께 저장된다. 시퀀싱 데이터가 나오면 같은 프로젝트 폴더에서 MAME 탭을 연다.

## MAME

### read 를 바코드별로 미리 나눠야 하나

아니다. 2단계에는 MinKNOW run 폴더를 그대로 넣는다. MAME 가 `fastq_pass/` 아래의 `.fastq` 와 `.fastq.gz` 를 읽어 바코드를 직접 나눈다. [단계 2. 분석 및 검토](mame-02-review.md) 참고.

### 실행은 끝났는데 판정이 하나도 없다

"분석이 끝났지만 well 0개" 창이 뜨고 read 가 단계마다 얼마나 버려졌는지 보여 준다. 먼저 두 숫자를 본다.

- MAPQ 통과 read 가 0: reference 에 정렬된 read 가 없다. reference 파일이 실제로 시퀀싱한 construct 인지 확인한다.
- Coverage 통과 read 가 0: 정렬은 됐지만 reference 를 충분히 덮은 read 가 없다. 전장 construct 를 reference 로 쓰고 amplicon read 를 넣으면 이렇게 된다. amplicon 구간을 reference 로 쓰거나 고급 옵션의 Coverage Fraction 을 내린다.

이 창은 기대 변이 파일이 이번 실행의 변이를 담고 있는지, 고른 폴더가 맞는 run 이고 barcode 폴더에 read 가 있는지도 확인하라고 안내한다.

### 커버리지 게이트가 정렬된 read 의 일부를 버렸다는 안내가 뜬다

부분 정렬과 chimeric read 는 원래 걸러지므로 일부 손실은 정상이다. read 를 전부 잃은 well 은 판정이 없어 화면에서는 분주하지 않은 well 과 똑같이 보인다. 비율이 크면 시료보다 reference 를 먼저 의심한다. 프라이머 자리처럼 reference 양 끝에서 일정한 염기 수만큼 못 미치는 정렬은 amplicon 이 짧을수록 비율 기준에 걸리기 쉽다. Coverage Fraction 은 2.1 의 고급 옵션에 있다.

### amplicon 을 잘라내지 못했다

프라이머 자리가 reference 에 없거나 여러 곳에 맞거나 앞뒤 순서가 뒤집힌 경우다. CDS 만 담긴 reference 에서는 프라이머가 CDS 밖에 있어 없는 것이 정상이다. 잘라내기를 건너뛴 채 가장 긴 read 도 커버리지 기준을 넘지 못하면 실행을 시작하지 않고 거절한다.

### 레퍼런스 끝에 있는 변이라고 이름이 뜬다

준 reference 를 그대로 정렬에 쓴 run 에서 기대 변이가 reference 양 끝 30 bp 안에 있으면 판정표 위에 그 변이 이름이 뜬다. 정렬기가 그 자리에서 read 를 잘라내므로 well 이 보고하는 depth 보다 얕게 읽힐 수 있다. 프라이머 결합 구간까지 포함한 reference 를 쓰면 그 위치가 안쪽으로 들어온다.

### 이전 run 이 만든 plate 폴더라는 안내가 뜬다

출력 폴더에 있지만 그 폴더에 기록된 run 에 속하지 않는 폴더라 판정에서 뺐다. 지운 것은 없다. 그 결과가 아직 필요한지 확인한 뒤 직접 지우고 run 마다 출력 폴더를 따로 쓴다.

### 공극 수가 빈칸이다

run 폴더와 그 한 단계 위 폴더에서 `report_*.json` 을 찾지 못했다. 빈칸은 읽지 못했다는 뜻이고 0 이 아니다. 공극 수에는 원래 합격선을 걸지 않는다.

### 3단계를 꼭 거쳐야 하나

아니다. 3단계는 선택이고 어떤 실행도 막지 않는다. 시퀀싱 판정만 필요하면 2단계에서 4단계로 바로 넘어간다. [단계 3. Cell stock 제작](mame-03-janus.md) 참고.

### 3단계 내보내기에 클론 하나가 빠졌다

PASS 클론만 내보낸다. 3단계의 제외 목록에 빠진 클론마다 사유가 나온다. AMBIGUOUS 나 LOWDEPTH 판정이 그런 예다.

### 4단계가 라벨 불일치로 내보내기를 막는다

확인 측정 평균이 같은 변이체의 1차 값과 크게 달라 라벨이 바뀌었을 수 있다는 뜻이다. 플레이트 레이아웃과 판정 라벨을 확인한다. 맞으면 **검토한 라벨 불일치 허용** 을 켜고 다시 만든다. [단계 4. 활성 데이터](mame-04-activity.md) 참고.

### EVOLVEpro 파일에 일부 변이체가 없다

판정이 명시적 Pass 이고 실패나 대체 반복 표시가 없으며 중복 행 사이에 충돌이 없는 변이체만 쓴다. 생성 결과에 NGS 판정으로 빠진 개수가 나온다. 통과한 변이체가 하나도 없으면 빈 파일을 쓰지 않고 실패한다.

→ [KURO 개요](kuro-index.md) | [MAME 개요](mame-index.md)
