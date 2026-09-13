# 라운드 2 (run FBF10847) 배포판 재분석, 2026-09-13

PaperA Figure 2b 를 FASTQ 부터의 재분석으로 갱신하기 위해 만든 산출물이다.

## 무엇을 돌렸나

- 코드: kuma `origin/main` 커밋 `ac841d65`, `KUMA_VERSION = "0.16.58"`. 벤치 하네스 코드가 아니라 배포 코드다
- 런 폴더: `060.nanopore_NGS/20260212_2227_X4_FBF10847_e7145f8e` 전량
- 참조: `070.KUMA_elements/260730 MAME test/260804_MAME_output/demux_filtered/pTSN-PtIspS-idi(KanR)_corrected.reference.amplicon.fa` (amplicon 1715 bp, 현행 조건)
- 코딩 윈도: 16..1699
- 네이티브 바코드: barcode06, barcode13, barcode20
- 드라이버와 로그: 같은 폴더의 `bench_r2_release.sh`, `bench_r2_release.log`
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

## 숫자를 다시 확인하는 법

이 폴더의 수치를 인용하는 문서는 기억이 아니라 워크북을 근거로 삼는다. 검사기를 돌리면 8분류 분포를 워크북에서 다시 뽑아 위 표와 대조한다.

```
kuma/.venv/bin/python count_workbook.py
```

12건을 검사하고 전부 맞으면 `CONTROL_OK`, 하나라도 어긋나면 어느 값이 얼마로 바뀌었는지 찍고 exit 1 이다. 검사 대상은 워크북 sha256, 채점 웰 수 95, 8분류 각각의 값, 선언하지 않은 판정 분류의 출현, WT 대조 판정이다. 웰 하나의 판정을 PASS 에서 WRONG_AA 로 바꾼 사본으로 돌려 실제로 실패하는지 확인했다. 해시와 PASS 와 WRONG_AA 세 경로로 잡는다.

워크북 sha256 은 `80bcddd08d637f79728ba1d995523d1530077857b954a7b2fc8fc019913477d0` 이다. 같은 이름의 다른 파일은 다른 측정이므로 통과하지 않는다.

한계도 같이 찍힌다. 이 워크북의 `__kuma_meta__` 시트는 참조 파일, 코딩 윈도, `min_read_count` 를 기록하지 않는다. 그 조건은 옆의 `bench_r2_release.sh` 에서 읽어야 한다. 기록하지 않는 것은 작성기 쪽 결함이고 별도로 고치는 중이다.

## 교차 검증

같은 런을 벤치 하네스(`bench/rounds-ab` 커밋 `e0e7e6a0`)의 arm A 로 돌린 결과와 96웰 전부 판정이 일치한다. 코드 경로가 달라도 같은 답을 낸다.

## 주의

원고 각주 `ev-depthfloor` 와 `ev-replicate` 가 가리키는 경로 `060.nanopore_NGS/TEST/260615_MAME_sorting_hmk/` 는 2026-09-13 현재 이 워크스페이스에 없다. 다른 머신에 있는지는 **미확인**이다. 원고가 그 산출물을 근거로 인용하는 동안 이 머신에서는 재현할 수 없다.

## 이 폴더의 위치

정본은 kuma 저장소의 `bench/rounds-ab` 브랜치다. 원고와 노트는 git 경로와 커밋 SHA 로 인용한다. `020.admin` 밑의 사본은 편의용이고 인용 대상이 아니다. 버전 관리 밖에 둔 근거는 사라진다. 각주 `ev-depthfloor` 가 가리키던 폴더가 그렇게 없어졌다.
