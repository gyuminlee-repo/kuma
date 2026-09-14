# 라운드 2 (run FBF10847) 배포판 재분석, 2026-09-13

PaperA Figure 2b 를 FASTQ 부터의 재분석으로 갱신하기 위해 만든 산출물이다.

## 무엇을 돌렸나

- 코드: kuma `origin/main` 커밋 `ac841d65`, `KUMA_VERSION = "0.16.58"`. 벤치 하네스 코드가 아니라 배포 코드다
- 런 폴더: `060.nanopore_NGS/20260212_2227_X4_FBF10847_e7145f8e` 전량
- 참조: `070.KUMA_elements/260730 MAME test/260804_MAME_output/demux_filtered/pTSN-PtIspS-idi(KanR)_corrected.reference.amplicon.fa` (amplicon 1715 bp, 현행 조건)
- 코딩 윈도: 16..1699
- 네이티브 바코드: barcode06, barcode13, barcode20
- 드라이버와 로그: 같은 폴더의 `bench_r2_release.sh`, `bench_r2_release.log`

드라이버는 어느 체크아웃의 코드를 읽을지 인자로 받는다. 기본값이 없으므로 지정하지 않으면 거부한다.

```
./bench_r2_release.sh <kuma-checkout>
```

실행 직전에 인터프리터에게 `kuma_core.__file__` 을 직접 물어 그 체크아웃 아래인지 확인하고 아니면 중단한다. 지정한 체크아웃의 커밋 SHA 와 브랜치와 워킹트리 clean 여부는 로그에 남는다. 산출물 위치는 `BENCH_R2_OUT` 으로 바꾸며 미지정 시 `070.KUMA_elements/bench_out/rounds-ab` 를 쓴다. `BENCH_PREFLIGHT_ONLY=1` 은 이 확인까지만 하고 재분석 없이 끝낸다.
- 소요: 1,117초. `total_reads` 2,706,444

## 결과: 설계변이 95웰의 8분류 분포

| 분류 | 현행 Figure 2b | 이번 재분석 |
|---|---|---|
| PASS | 74 (77.9%) | 82 (86.3%) |
| NO_CALL | 13 | 3 |
| LOWDEPTH | 4 | 2 |
| WRONG_AA | 2 | 4 |
| MIXED | 1 | 1 |
| AMBIGUOUS | 1 | 2 |
| FRAMESHIFT | 0 | 1 |
| MANY | 0 | 0 |

WT 대조 H12 는 PASS 다. 96웰 총계는 PASS 83 이다.

PASS 가 아닌 13웰은 이렇다. A3 R87P, A8 Y360F, G6 R261N, H2 R87M 이 WRONG_AA 다. A5 V218L, H5 E228D, B3 R93A 가 NO_CALL 이다. G2 N64W, G3 S112M 이 LOWDEPTH 다. E11 V550C 가 MIXED 다. C5 E222D 가 FRAMESHIFT 다. B9 I428V, E8 K409S 가 AMBIGUOUS 다.

## 현행 Figure 2b 값과 다른 이유

현행 값은 보관된 per-plate 판정에 분류기와 depth floor 90 을 재적용한 것이고 FASTQ 부터의 재분석이 아니다. 원고 각주 `ev-depthfloor` 가 그 한계를 직접 적어 두었다. 차이는 두 갈래다.

- depth floor 90 대 기본값 30: 각주 기준 A8 과 G3 두 웰만 움직인다
- 참조와 ingest 층: 나머지 차이가 여기서 온다. amplicon 참조는 `v0.16.21` 이후 제품 기본 동작이고 read-length 창도 1765-1825 에서 1615-1975 로 넓어졌다

## replicate 층 (288 레코드)

원고는 96웰 통합 층과 함께 웰 곱하기 플레이트 288 레코드 층을 보고한다. 그 층도 같은 워크북의 NB06·NB13·NB20 시트에서 나온다. 두 층이 같은 재분석에서 나오므로 방법이 갈리지 않는다.

| 분류 | 레코드 | read depth 중앙값 |
|---|---|---|
| PASS | 191 | 5,684 |
| WRONG_AA | 37 | 2,639 |
| MIXED | 30 | 2,103 |
| NO_CALL | 12 | 4,213 |
| AMBIGUOUS | 8 | 3,193 |
| FRAMESHIFT | 5 | 3,063 |
| LOWDEPTH | 5 | 30 |
| MANY | 0 | 해당 없음 |

합계 288 이고 read count 결측은 0건이다. 288 레코드는 같은 construct 를 3 플레이트에서 잰 기술 반복이고 생물학적 반복이 아니다.

MIXED 판정에 쓰는 90-read floor 는 이 재분석에서도 실제로 작동한다. mixed position 을 가지면서 read count 가 90 미만인 레코드가 6건이다. NB13 의 G2(20), G3(17), C5(47), B12(64), D12(54) 와 NB20 의 G3(30) 이다. MIXED 로 남은 30 레코드의 최소 read count 는 100 으로 floor 바로 위다.

## 숫자를 다시 확인하는 법

이 폴더의 수치를 인용하는 문서는 기억이 아니라 워크북을 근거로 삼는다. 검사기를 돌리면 8분류 분포를 워크북에서 다시 뽑아 위 표와 대조한다.

```
kuma/.venv/bin/python count_workbook.py
```

검사 건수는 검사를 더할 때마다 바뀌는 값이므로 여기에 고정하지 않는다. 실행하면 검사기가 스스로 건수와 상시 가드 지점 수와 한계를 출력한다. 전부 맞으면 `CONTROL_OK`, 하나라도 어긋나면 어느 값이 얼마로 바뀌었는지 찍고 exit 1 이다. 검사 대상은 워크북 sha256, 채점 웰 수 95, 8분류 각각의 값, WT 대조 판정, 그리고 replicate 층의 레코드 수와 8분류와 클래스별 depth 중앙값이다. 선언하지 않은 판정 분류는 검사 항목이 아니라 즉시 중단 사유다. 워크북을 읽는 자리에서 `VerdictClass` 밖의 판정을 만나면 세지 않고 abort 한다. 분류별 집계 합이 레코드 수와 다른 경우도 같다. 8분류 목록은 `kuma_core/mame/models.py` 의 `VerdictClass` 에서 읽어 온다. 기댓값 숫자는 알려진 답이므로 손으로 적은 채로 남고 키 집합만 enum 과 맞춘다. 웰 하나의 판정을 PASS 에서 WRONG_AA 로 바꾼 사본으로 돌려 실제로 실패하는지 확인했다. 해시와 PASS 와 WRONG_AA 세 경로로 잡는다. per-plate 레코드 하나를 PASS 에서 MIXED 로 바꾼 사본에서는 다섯 경로로 잡는다.

워크북 sha256 은 `80bcddd08d637f79728ba1d995523d1530077857b954a7b2fc8fc019913477d0` 이다. 같은 이름의 다른 파일은 다른 측정이므로 통과하지 않는다.

한계도 같이 찍힌다. 이 워크북의 `__kuma_meta__` 시트는 참조 파일, 코딩 윈도, `min_read_count` 를 기록하지 않는다. 그 조건은 옆의 `bench_r2_release.sh` 에서 읽어야 한다. 기록하지 않는 것은 작성기 쪽 결함이고 별도로 고치는 중이다.

## 교차 검증

같은 런을 벤치 하네스(`bench/rounds-ab` 커밋 `e0e7e6a0`)의 arm A 로 돌린 결과와 96웰 전부 판정이 일치한다. 코드 경로가 달라도 같은 답을 낸다.

## 주의

원고 각주 `ev-depthfloor` 와 `ev-replicate` 가 가리키는 경로 `060.nanopore_NGS/TEST/260615_MAME_sorting_hmk/` 는 2026-09-13 현재 이 워크스페이스에 없다. 다른 머신에 있는지는 **미확인**이다. 원고가 그 산출물을 근거로 인용하는 동안 이 머신에서는 재현할 수 없다.

## 이 폴더의 위치

정본은 kuma 저장소의 `bench/rounds-ab` 브랜치다. 원고와 노트는 git 경로와 커밋 SHA 로 인용한다. `020.admin` 밑의 사본은 편의용이고 인용 대상이 아니다. 버전 관리 밖에 둔 근거는 사라진다. 각주 `ev-depthfloor` 가 가리키던 폴더가 그렇게 없어졌다.
