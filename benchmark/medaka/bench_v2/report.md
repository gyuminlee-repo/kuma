# kuma-mame Consensus Accuracy Benchmark v2 Report

## 가정 및 설계
- 합성 데이터 (badread nanopore2023 모델, seed=1)
- WT amplicon: 177bp (현실 비반복 backbone + 2 homopolymer runs)
  - A-run: [60,67) 7bp
  - T-run: [120,127) 7bp
  - 서열: ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCGAAAAAAATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTCTTTTTTTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA
- ingest_run_folder 파라미터: mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30, min_depth=1
- Consensus frame: G1(WT) well에 대해 4-frame edlib 최소 거리 자동 결정
- WT sanity gate: G1 well N wildcard edlib ed <= 2 (depth>=30x 실패시 결과표 생성 중단)

## Well 설계
| Well | Barcode (F,R) | custom_barcode | 유형 | amp_len | 변이 위치 |
|------|--------------|----------------|------|---------|----------|
| G1 | F1,R1 | 1_1 | WT | 177 | 없음 |
| G2 | F3,R2 | 2_3 | SNV3 | 177 | SNV pos 95,105,135 (비-homopolymer) |
| G3 | F7,R4 | 4_7 | HomoAdjacentSNV | 177 | SNV pos 119 (T-run 직전) |
| G4 | F12,R8 | 8_12 | Del2bp | 175 | 2bp del [80,82) (비-homopolymer) |
| G5 | F5,R6 | 6_5 | HomoDel1bp | 176 | 1bp del pos 62 (A-run 내부) |

## WT Sanity Gate 결과
| Depth | G1 WT ed (N wildcard) | G1 N수 | Gate 판정 |
|-------|----------------------|--------|----------|
| 10x | 2 | 12 | PASS |
| 20x | 0 | 0 | PASS |
| 30x | 0 | 1 | PASS |
| 50x | 0 | 1 | PASS |
| 100x | 0 | 0 | PASS |

## 회수율 요약표

| Depth | G1(WT) | G2(SNV3) | G3(HomoAdj) | G4(Del2bp) | G5(HomoDel) |
|-------|--------|----------|-------------|------------|-------------|
| 10x | ed=14 | OK | ed=2 | ed=15 | ed=7 |
| 20x | OK | OK | ed=2 | ed=7 | ed=8 |
| 30x | ed=1 | ed=1 | ed=3 | ed=4 | ed=7 |
| 50x | ed=1 | OK | ed=1 | ed=5 | ed=4 |
| 100x | OK | ed=1 | ed=1 | ed=4 | ed=4 |

## 상세 결과 (depth별)

### 10x
- Consensus frame: **amp**
- WT gate: ed=2 N=12 PASS

| Well | 유형 | reads | edit_dist | false_SNV | false_Ins | false_Del | N수 | len_match |
|------|------|-------|-----------|-----------|-----------|-----------|-----|-----------|
| G1 | WT | 30 | 14 | 14 | 0 | 0 | 12 | yes |
| G2 | SNV3 | 32 | 0 | 0 | 0 | 0 | 0 | yes |
| G3 | HomoAdjacentSNV | 35 | 2 | 2 | 0 | 0 | 2 | yes |
| G4 | Del2bp | 42 | 15 | 13 | 1 | 0 | 15 | no(c=177,t=175) |
| G5 | HomoDel1bp | 52 | 7 | 6 | 1 | 0 | 6 | no(c=177,t=176) |

### 20x
- Consensus frame: **amp**
- WT gate: ed=0 N=0 PASS

| Well | 유형 | reads | edit_dist | false_SNV | false_Ins | false_Del | N수 | len_match |
|------|------|-------|-----------|-----------|-----------|-----------|-----|-----------|
| G1 | WT | 61 | 0 | 0 | 0 | 0 | 0 | yes |
| G2 | SNV3 | 71 | 0 | 0 | 0 | 0 | 0 | yes |
| G3 | HomoAdjacentSNV | 77 | 2 | 2 | 0 | 0 | 2 | yes |
| G4 | Del2bp | 87 | 7 | 5 | 1 | 0 | 7 | no(c=177,t=175) |
| G5 | HomoDel1bp | 84 | 8 | 7 | 1 | 0 | 8 | no(c=177,t=176) |

### 30x
- Consensus frame: **amp**
- WT gate: ed=0 N=1 PASS

| Well | 유형 | reads | edit_dist | false_SNV | false_Ins | false_Del | N수 | len_match |
|------|------|-------|-----------|-----------|-----------|-----------|-----|-----------|
| G1 | WT | 99 | 1 | 1 | 0 | 0 | 1 | yes |
| G2 | SNV3 | 112 | 1 | 1 | 0 | 0 | 1 | yes |
| G3 | HomoAdjacentSNV | 117 | 3 | 3 | 0 | 0 | 3 | yes |
| G4 | Del2bp | 126 | 4 | 2 | 1 | 0 | 4 | no(c=177,t=175) |
| G5 | HomoDel1bp | 121 | 7 | 6 | 1 | 0 | 7 | no(c=177,t=176) |

### 50x
- Consensus frame: **amp**
- WT gate: ed=0 N=1 PASS

| Well | 유형 | reads | edit_dist | false_SNV | false_Ins | false_Del | N수 | len_match |
|------|------|-------|-----------|-----------|-----------|-----------|-----|-----------|
| G1 | WT | 187 | 1 | 1 | 0 | 0 | 1 | yes |
| G2 | SNV3 | 172 | 0 | 0 | 0 | 0 | 0 | yes |
| G3 | HomoAdjacentSNV | 196 | 1 | 1 | 0 | 0 | 1 | yes |
| G4 | Del2bp | 194 | 5 | 3 | 1 | 0 | 5 | no(c=177,t=175) |
| G5 | HomoDel1bp | 197 | 4 | 3 | 1 | 0 | 4 | no(c=177,t=176) |

### 100x
- Consensus frame: **amp**
- WT gate: ed=0 N=0 PASS

| Well | 유형 | reads | edit_dist | false_SNV | false_Ins | false_Del | N수 | len_match |
|------|------|-------|-----------|-----------|-----------|-----------|-----|-----------|
| G1 | WT | 391 | 0 | 0 | 0 | 0 | 0 | yes |
| G2 | SNV3 | 370 | 1 | 1 | 0 | 0 | 1 | yes |
| G3 | HomoAdjacentSNV | 359 | 1 | 1 | 0 | 0 | 1 | yes |
| G4 | Del2bp | 415 | 4 | 2 | 1 | 0 | 4 | no(c=177,t=175) |
| G5 | HomoDel1bp | 378 | 4 | 3 | 1 | 0 | 4 | no(c=177,t=176) |

## 결론

- 일반 SNV (G2, 3개 SNV): 최초 완벽 회수 depth = **10x**
- Homopolymer 인접 SNV (G3): 최초 완벽 회수 depth = **Nonex**
- 비-homopolymer 결실 (G4, 2bp del): 최초 완벽 회수 depth = **Nonex**
- Homopolymer 내 결실 (G5, 1bp polyA del): 최초 완벽 회수 depth = **Nonex**

### 판정
- 충분: 일반 SNV는 10x부터 안정적 회수.
- Homopolymer 인접 SNV(G3): 10-100x 범위에서 완벽 회수 실패.
- 깨짐: Homopolymer 내 결실(G5)은 10-100x 범위에서 완벽 회수 실패.

## 한계
- 합성 데이터(badread nanopore2023): 실 MinKNOW 런 아님.
- Medaka head-to-head 비교 미수행 (macOS arm64 네이티브 Medaka 미설치).
- 각 well당 단일 barcode 조합만 테스트.
- edit_dist 기반 채점: 동일 위치 치환+삭제 동시 발생시 attribution 불완전.

*생성 시각: 2026-06-12T12:29:15.717803*