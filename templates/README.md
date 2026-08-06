# KUMA Sample Data Templates

Load Sample Data 진입점용 더미 데이터. [[260514_KUMA_엑셀_입력파일_정리]] v2 의 사용자 직접 제공 표 파일을 **하나의 일관된 EGFP 시나리오**로 구현. 컬럼 헤더·시트명·확장자는 코드 검증 기준과 일치.

자동 감지 파일(`sequencing_summary*`, `pore_activity_*`, `throughput_*`, `barcode_alignment*`, `sample_sheet_*`)은 MinKNOW 실 출력이라 더미 제외.

## Canonical 시나리오

EGFP, Round 1, `plate01`.

```
Round 0 EVOLVEpro pred (#1)  ── top candidates
        │
        ▼ user picks EGFP single variants
KURO design                  ── primers for 9 single candidates
        │
        ▼ export
Expected mutations (#3)       ── 9 single candidates + WT control
        │
        ▼ wet lab → plate subset
Plate layout (#6)             ── 22 wells (WT × 3, 6 variants × 3, 1 blank)
        │  ┌──────────────┐
        ├─▶│ Sample map (#5)
        │  │ 동일 22 wells, sample=<variant>_r{1,2,3}
        │  └──────────────┘
        ▼ measure
Activity long (#7)            ── 22 wells values
        │  ┌──────────────┐
        ├─▶│ EVOLVEpro raw (#8)        ── short-form rank source
        ├─▶│ Agilent (#9)              ── variant-labeled confirmation
        ├─▶│ GC normalised (#10)       ── well-labeled relative sheet
        ├─▶│ GC-FID round 1 raw (#11)  ── well-labeled raw report
        ├─▶│ Numeric index (#12)       ── rank-ID confirmation report
        │  └──────────────┘
        ▼ merge → export
Round 2 EVOLVEpro pred        ── 다음 라운드 (이 폴더 범위 밖)
```

**Designed variants (KURO → MAME)**: S65T, Y66H, T203Y, F64L, A206K, S65A, Y66W, T203F, F99S, WT control.

**Measured variants (MAME activity / Step 3)**: WT, S65T, Y66H, T203Y, F64L, A206K, S65A.

**Plate layout**:
| Row | Wells | Variant |
|---|---|---|
| A | A1-A3 | WT |
| A | A4-A6 | S65T |
| B | B1-B3 | Y66H |
| B | B4-B6 | T203Y |
| C | C1-C3 | F64L |
| C | C4-C6 | A206K |
| D | D1-D3 | S65A |
| H | H12 | blank |

## Cross-file 일관성 검증 (검증 완료)

- 22 wells 모두 #6 plate_layout, #7 activity_long 일치
- Measured variant set {WT, S65T, Y66H, T203Y, F64L, A206K, S65A}: #6/#8/#9/#10/#11/#12 일치
- #3 expected mutations 는 plate subset 보다 넓은 9개 EGFP single 후보를 담고, #6 이후 activity/Step 3 파일은 실제 측정된 6개 후보만 담는다
- True activity 값 통일: WT=1.00, S65T=1.85, Y66H=0.48, T203Y=2.33, F64L=1.55, A206K=1.20, S65A=3.11
- Step 3 Help 샘플 기본 조합: #11 raw GC-FID round-1 primary + #12 numeric-index confirmation + #8 rank source

## 파일 목록

| # | 파일 | 도구 | 단계 | 필수 컬럼/헤더 | 시트명 |
|---|---|---|---|---|---|
| 1 | `01_kuro_evolvepro_pred.csv` | KURO | Stage 2 | `variant`, `y_pred` | 없음 (csv) |
| 3 | `03_mame_expected_mutations.xlsx` | MAME | Stage 3 | `mutant_id`, `position`, `wt_aa`, `mt_aa`, `wt_codon`, `mt_codon`, `group_id`, `primer_set_ref`, `notation_type`, `status` | `expected_mutations` |
| 4 | `04_mame_custom_barcodes.xlsx` | MAME | Stage 4 | A=`isps_f_1..12`/`isps_r_1..8`, B=서열 | `barcodes` |
| 6 | `06_mame_plate_layout.xlsx` | MAME activity | plateLayout route `layout_xlsx` | `Mutant`, `Well Pos.` (`sample_name`+`well` 헤더도 대신 쓸 수 있음). `_r<n>` 반복 접미사는 반복 웰을, `blank` 행은 빈 웰을 뜻하고 activity 파싱에서 제외된다 | `Plate Layout` |
| 7a | `07_mame_activity_long.csv` | MAME activity | genotype route `activity.upload` | `well_id`, `value` (별칭은 아래 비고), opt `plate_id`, opt `replicate_idx` | 없음 (csv) |
| 7b | `07_mame_activity_long.xlsx` | MAME activity | genotype route `activity.upload` (xlsx 변형) | 동일 | `activity_long` |
| 8 | `08_mame_evolvepro_raw.xlsx` | MAME activity | plateLayout route `round1_evolvepro_xlsx` (축 A) 또는 Step 3 `prev_evolvepro_xlsx` (`rep_batch_xlsx` 의 rank 소스) | `Variant`, `activity` (EVOLVEpro short form, activity 내림차순) | `EVOLVEpro` |
| 9 | `09_mame_agilent_rep_batch.xlsx` | MAME activity / Step 3 | plateLayout route `rep_batch_xlsx` (축 B) 또는 variant-labeled confirmation | FID1B block, `Sample Name`=EVOLVEpro short variant, `Area` raw peak area, WT blocks 포함 | `Agilent` |
| 10 | `10_mame_gc_prenormalised.xlsx` | MAME activity / Step 3 | plateLayout route `gc_data_xlsx` (축 A) 또는 GC-sheet primary screen | `Sample Name`=well, `Area`=WT 대비 상대값 | `GC_normalised` |
| 11 | `11_mame_gc_fid_round1_raw.xlsx` | MAME Step 3 | primary screen | FID1B block, `Sample Name`=well, `Area`=raw peak area, WT blocks 포함 | `GC-FID round1 raw` |
| 12 | `12_mame_agilent_numeric_index.xlsx` | MAME Step 3 | numeric-index confirmation | FID1B block, `Sample Name`=`1`, `1-2`, `1-3` 형식, WT blocks 포함 | `Agilent numeric index` |

## 비고

- **#4 custom_barcodes**: 96-well combinatorial barcode 정의 자체이므로 다른 파일과 직접 매핑되지 않는 독립 reference 데이터.
- **#9 Agilent**: variant-labeled confirmation report. 파일명은 이전 샘플명과 호환을 위해 유지하지만, 내용은 Step 3 `variantLabels` 입력 형식이다.
- **#11/#12 Step 3 샘플**: Help → Load Sample Data 가 EVOLVEpro 입력 생성 패널을 바로 실행 가능한 raw primary + numeric confirmation 조합으로 채우는 데 사용.
- **#7/#8/#10/#11/#12**: 동일 measurement 의 다른 표현 (long vs variant-mean vs raw report). 값은 일치.
- **step 3 의 두 입력 경로는 서로 다르다**: genotype route 는 #7 을 `activity.upload` 로 올려 NGS verdict 와 well 단위로 묶고, plateLayout route 는 #6/#8/#9/#10 xlsx 를 `build_evolvepro_input` 에 직접 넘긴다. #8/#9/#10 은 #7 의 대체 업로드 포맷이 아니다.
- **#7 컬럼 별칭**: well 컬럼은 `well_id`, `sample name`, `sample`, `well`, `well pos.` 중 하나, 값 컬럼은 `value`, `area`, `activity` 중 하나면 된다 (헤더는 소문자로 정규화 후 비교). `plate_id` 는 plate 가 정확히 1개일 때만 생략 가능하고, 여러 plate 를 한 파일에 담으면 필수다. `replicate_idx` 를 빼면 1 로 채운다.

## 참조

- 분석 정본: `$OBSIDIAN_VAULT/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/260514_KUMA_엑셀_입력파일_정리.md`
- 전체 입력 종합: `260514_KUMA_입력파일_종합정리.md`
- 코드 위치 (심볼이 정본, 라인은 조회 시점 기준):
  - `python-core/sidecar_mame/handlers/activity.py`, `_ALLOWED_ACTIVITY_EXTENSIONS` (`.csv`/`.xlsx`/`.xls`, 라인 32), `handle_activity_upload`
  - `kuma_core/mame/activity/ingest_long_csv.py`, `WELL_COL_ALIASES`, `VALUE_COL_ALIASES` (라인 36-37), `ingest_long_csv`
  - `kuma_core/mame/activity/plate_layout_xlsx.py`, `parse_plate_layout_xlsx` (라인 68, 헤더 판정 141-169), `Mutant` + `Well Pos.` 또는 `sample_name` + `well`
  - `kuma_core/mame/activity/evolvepro_xlsx.py`, `parse_agilent_standard` (327), `parse_agilent_block_rep_batch` (595), `parse_relative_only` (685), `read_evolvepro_rows` (812), `write_evolvepro_xlsx` (876)
  - `python-core/sidecar_mame/models.py`, `BuildEvolveproInputParams`, `_axis_sources` (라인 296, 409)
  - `kuma_core/mame/io/kuro_reader.py:11-22` — expected_mutations 컬럼
  - `kuma_core/mame/ingest/sort_barcode.py:74-75, 135, 207-220` — barcode/sample map
  - `python-core/sidecar_kuro/handlers/misc.py:70` — KURO `load_evolvepro_csv`
