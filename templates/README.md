# KUMA Sample Data Templates

Load Sample Data 진입점용 더미 데이터. [[260514_KUMA_엑셀_입력파일_정리]] v2 의 사용자 직접 제공 표 파일 9종을 **하나의 일관된 시나리오**로 구현. 컬럼 헤더·시트명·확장자는 코드 검증 기준과 일치.

자동 감지 파일(`sequencing_summary*`, `pore_activity_*`, `throughput_*`, `barcode_alignment*`, `sample_sheet_*`)은 MinKNOW 실 출력이라 더미 제외.

## Canonical 시나리오

가상 IspS-like 효소, Round 1, `plate01`.

```
Round 0 EVOLVEpro pred (#1)  ── top-10 candidates
        │
        ▼ user picks top 5 single + 1 combo idea
KURO design                  ── primers for 5 single + 1 combo
        │
        ▼ export
Expected mutations (#3)       ── 5 single + 1 combo + WT control
        │
        ▼ wet lab → plate
Plate layout (#6)             ── 22 wells (7 variant × 3 reps + 1 blank)
        │  ┌──────────────┐
        ├─▶│ Sample map (#5)
        │  │ 동일 22 wells, sample=<variant>_r{1,2,3}
        │  └──────────────┘
        ▼ measure
Activity long (#7)            ── 22 wells values
        │  ┌──────────────┐
        ├─▶│ EVOLVEpro raw (#8)
        ├─▶│ Agilent (#9)        ── 동일 7 variants
        ├─▶│ GC normalised (#10)
        │  └──────────────┘
        ▼ merge → export
Round 2 EVOLVEpro pred        ── 다음 라운드 (이 폴더 범위 밖)
```

**Designed variants (KURO → MAME)**: WT, Q232A, Y233A, A40P, E61Y, L150V, A40P_E61Y (combo)

**Plate layout**:
| Row | Wells | Variant |
|---|---|---|
| A | A1-A3 | WT |
| A | A4-A6 | Q232A |
| B | B1-B3 | Y233A |
| B | B4-B6 | A40P |
| C | C1-C3 | E61Y |
| C | C4-C6 | L150V |
| D | D1-D3 | A40P_E61Y |
| H | H12 | blank |

## Cross-file 일관성 검증 (검증 완료)

- 22 wells 모두 #5 sample_map, #6 plate_layout, #7 activity_long 일치
- Variant set {WT, Q232A, Y233A, A40P, E61Y, L150V, A40P_E61Y}: #6/#8/#9/#10 일치
- 콤보 표기: `A40P_E61Y` 언더스코어 통일 (슬래시 미사용)
- #1 EVOLVEpro top-5 = 설계된 single 5종 (Q232A, Y233A, A40P, E61Y, L150V)
- 설계된 variants ⊆ MAME 측정 variants (누락 0)
- True activity 값 통일: WT=1.00, Q232A=1.85, Y233A=0.48, A40P=2.33, E61Y=1.55, L150V=1.20, A40P_E61Y=3.11

## 파일 목록

| # | 파일 | 도구 | 단계 | 필수 컬럼/헤더 | 시트명 |
|---|---|---|---|---|---|
| 1 | `01_kuro_evolvepro_pred.csv` | KURO | Stage 2 | `variant`, `y_pred` | — |
| 3 | `03_mame_expected_mutations.xlsx` | MAME | Stage 3 | `mutant_id`, `position`, `wt_aa`, `mt_aa`, `wt_codon`, `mt_codon`, `group_id`, `primer_set_ref`, `notation_type`, `status` | `expected_mutations` |
| 4 | `04_mame_custom_barcodes.xlsx` | MAME | Stage 4 | A=`isps_f_1..12`/`isps_r_1..8`, B=서열 | `barcodes` |
| 5 | `05_mame_sample_map.xlsx` | MAME | Stage 4 (선택) | A=sample 이름, B=well | `sample_map` |
| 6 | `06_mame_plate_layout.xlsx` | MAME activity | Stage A | `Mutant`, `Well Pos.` | `Plate Layout` |
| 7a | `07_mame_activity_long.csv` | MAME activity | Stage B (주) | `plate_id`, `well_id`, `value`, opt `replicate_idx` | — |
| 7b | `07_mame_activity_long.xlsx` | MAME activity | Stage B (xlsx 변형) | 동일 | `activity_long` |
| 8 | `08_mame_evolvepro_raw.xlsx` | MAME activity | Stage B 대안 | `Variant`, `activity` | `EVOLVEpro` |
| 9 | `09_mame_agilent_rep_batch.xlsx` | MAME activity | Stage B 대안 (Agilent GC) | `Sample Name`, `Area` (per injection) | `Agilent` |
| 10 | `10_mame_gc_prenormalised.xlsx` | MAME activity | Stage B 대안 (정규화본) | `Sample Name`, `Area` | `GC_normalised` |

## 비고

- **#4 custom_barcodes**: 96-well combinatorial barcode 정의 자체이므로 다른 파일과 직접 매핑되지 않는 독립 reference 데이터.
- **#9 Agilent**: per-injection raw Area (true_act × 1000 ± noise). 정규화 전 데이터.
- **#7/#8/#10**: 동일 measurement 의 다른 표현 (long vs variant-mean). 값은 일치.

## 참조

- 분석 정본: `$OBSIDIAN_VAULT/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260514_KUMA_엑셀_입력파일_정리.md`
- 전체 입력 종합: `260514_KUMA_입력파일_종합정리.md`
- 코드 위치:
  - `python-core/sidecar_mame/handlers/activity.py:32` — `_ALLOWED_ACTIVITY_EXTENSIONS`
  - `kuma_core/mame/activity/ingest_long_csv.py:27-57` — long CSV 컬럼
  - `kuma_core/mame/activity/plate_layout_xlsx.py:49-117` — `Mutant` + `Well Pos.`
  - `kuma_core/mame/activity/evolvepro_xlsx.py:185, 392, 469, 537` — EVOLVEpro/Agilent/GC 파서
  - `kuma_core/mame/io/kuro_reader.py:11-22` — expected_mutations 컬럼
  - `kuma_core/mame/ingest/sort_barcode.py:74-75, 135, 207-220` — barcode/sample map
  - `python-core/sidecar_kuro/handlers/misc.py:70` — KURO `load_evolvepro_csv`
