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

## 이 폴더와 번들 샘플은 다른 캠페인이다

위 시나리오는 **이 폴더(`templates/`)** 의 내용이다. 앱이 Help > Load Sample Data 로 여는 파일은 `src-tauri/samples/mame/` 에 있다. 그쪽은 2026-08-31 에 별도 캠페인으로 재생성됐다. 두 폴더를 같은 것으로 읽지 마라.

번들 샘플 쪽은 `python-core/scripts/generate_mame_step4_samples.py` 가 만든다. 스크립트는 shipped reference 로 위치와 잔기를 확정한다. 이어서 실제 파이프라인을 돌려 결과와 verdict 워크북을 뽑는다. 마지막으로 step 4 입력 분기 10개를 전부 `build_evolvepro_input` 으로 통과시킨 뒤에야 끝난다.

### templates/#6 은 step 4 build 를 통과하지 못한다

이 폴더의 `06_mame_plate_layout.xlsx` 는 변이당 웰 3개(`_r<n>` 반복)를 쓴다. `build_evolvepro_input` 의 `_layout_maps` 는 한 변이가 두 웰에 앉는 것을 거절한다(`kuma_core/mame/activity/build_evolvepro_input.py:113-115`). 이 파일을 `layout_xlsx` 로 넘기면 `layout maps variant '232A' to multiple wells` 로 멈춘다. verdict 워크북에서 매핑을 유도하는 경로도 같은 1:1 제약을 건다(`:145-146`).

`plate_layout_xlsx.py` 는 `_r<n>` 접미사를 벗겨내도록 만들어져 있으므로 반복 웰은 의도된 표기다. 파서와 소비자가 서로 다른 계약을 들고 있는 상태이며 어느 쪽을 정본으로 삼을지는 아직 정해지지 않았다. 번들 샘플은 그 결정을 기다리지 않고 변이당 웰 1개로 재생성해 build 가 도는 쪽을 택했다.

## 번들 샘플 캠페인 (`src-tauri/samples/mame/`)

- **KURO 와 MAME 가 한 캠페인이다.** 변이 목록을 손으로 적지 않고 KURO 샘플에서 유도한다. `sample_evolvepro.csv` 의 round-0 예측 24개를 `sample_plasmid.gb` 에 대해 실제로 설계해 보고, 프라이머가 나온 후보를 예측 순위대로 16개 뽑아 플레이트에 올린다. 설계에 실패한 후보는 벤치에 도달할 수 없으므로 제외된다(현재 기본 설정 KOD 에서 8개 실패). 즉 지금은 설계 가능한 후보 전부가 플레이트에 오른다. 코돈도 KURO 설계 결과에서 가져오므로 expected mutations 시트가 프라이머가 실제로 싣는 코돈을 적는다.
- 설계 변이 16개 + WT 대조 1행. `sample_plasmid.gb` 의 CDS 와 `reference.fasta` 는 같은 239 잔기 단백질이고 `wt_aa` 는 그 서열에서 읽는다. 이전 목록은 avGFP 넘버링이라 EGFP 가 이미 갖고 있는 `S65T`·`F64L` 을 다시 도입하라고 적고 있었고, 그 전 판은 KURO 예측과 아예 겹치지 않는 변이를 검증하고 있었다.
- 변이 목록은 위치 오름차순이다. 플레이트는 파일 행 순서로 채워지는데 numeric-ID 디코더는 위치 순서로 순번을 매기므로, 정렬돼 있을 때만 두 해석이 같은 웰을 가리킨다.
- 플레이트: 변이 16개가 A01~H02, WT 대조가 H12.
- **native barcode 3개로 읽은 triplicate 다 (v0.16.42).** NB01·NB02·NB03 이 같은 플레이트를 각각 demux 하고, 파이프라인이 변이마다 최적 복제본을 고른다. 웰은 변이당 하나 그대로다. 두 웰에 앉은 변이는 NGS 근거를 붙일 웰이 정해지지 않아 layout 리더와 verdict 리더가 모두 거절하기 때문이다. 3중은 플레이트를 넓히는 것이 아니라 플레이트 위에 축을 하나 더 얹는 것이다.
- **선정된 복제본(FINAL) 기준으로는 8종 중 7종만 나온다 (2026-08-31).** PASS 11개, 그리고 FRAMESHIFT·LOWDEPTH·MANY·MIXED·NO_CALL·WRONG_AA 각 1개다. AMBIGUOUS 는 FINAL 에는 없다. `kuma_core/mame/select/best_pick.py` 의 `PRIORITY_ORDER`(`PASS > AMBIGUOUS > LOWDEPTH`)가 대표 복제본을 뽑는 층위이고, 이 층위는 verdict 발탁 층위(`build_evolvepro_input`/`export_janus_mapping` 의 PASS 전용 필터)와 다르다. 세 복제본이 전부 AMBIGUOUS 인 변이를 두면 PRIORITY_ORDER 가 AMBIGUOUS 를 대표로 뽑아, 화면에는 "AMBIGUOUS 를 골랐다"로 읽힌다. 그래서 AMBIGUOUS 를 유발하는 변이(`K239A`)는 세 복제본 중 하나(NB01)만 AMBIGUOUS 로 만들고 나머지 둘은 정상 치환만 넣어 PASS 로 읽히게 한다. `G190A` 도 같은 이유로 NB01 만 LOWDEPTH 다. 두 변이 모두 나머지 둘이 통과해 NB03 이 대표로 선정된다. AMBIGUOUS 자체는 사라지지 않고 전체 51건 verdict 중 1건(K239A·NB01)으로, 복제본 비교 화면에서만 보인다. `A227V` 는 세 복제본이 전부 LOWDEPTH 라 LOWDEPTH 가 그대로 대표로 선정된다. 이는 AMBIGUOUS 와 같은 성질이지만 이번 재생성 범위에는 포함하지 않았다. 전부 consensus 서열과 FASTA 헤더 값만으로 유발하므로 `classify_verdict` 는 손대지 않았고 픽스처도 손으로 고치지 않았다.
- 체인이 끊어지면 `tests/mame/test_sample_campaign_chain.py` 가 잡는다. 같은 단백질인지, 플레이트 변이가 전부 예측 후보인지, 설계 가능한 상위 16개인지, verdict 워크북이 그 변이들을 채점하는지, step 4 export 가 FINAL PASS 변이와 정확히 일치하는지를 출하 파일에서 직접 읽어 검사한다. 마지막 항목은 `build_evolvepro_input` 이 엄격한 PASS 만 내보내므로 "설계된 전부" 가 아니라 "통과한 것" 과 대조한다.
- `13_mame_verdict.xlsx` 는 실제 analyze 실행이 쓴 워크북이다. step 4 필수 입력이며 샘플 데이터에 다른 공급원이 없다. 시트는 `NB01`·`NB02`·`NB03`·`Final`·`NGS Results`·`Final (matrix)` 와 메타 시트다.
- nanopore raw run(fastq, MinKNOW 폴더)은 번들에 넣지 않는다. 용량이 크고 화면에 필요한 것은 결과이지 원시 신호가 아니다. 대신 결과 픽스처와 verdict 워크북이 같은 실행에서 나온다. step 2 의 run folder 칸은 샘플을 불러오면 그 사실을 문구로 밝히고 비어 있는 채로 남는다.

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

번들 샘플 전용(`src-tauri/samples/mame/`, 이 폴더에는 없다):

| # | 파일 | 단계 | 필수 컬럼/헤더 | 시트명 |
|---|---|---|---|---|
| 13 | `13_mame_verdict.xlsx` | step 4 `verdict_xlsx` (필수) | Analyze 워크북 그대로. `Final` 시트의 `well_id`, `verdict`, `mutant_id` 를 읽는다 | `Final` 외 analyze 시트 일체 |
| 14 | `14_mame_activity_long_raw.csv` | step 4 `activity_path`, `activity_scale=raw` | `plate_id`, `well_id`, `value`, `replicate_idx`. `WT_1`~`WT_3` 행이 분모다 | 없음 (csv) |
| 15 | `15_mame_activity_variant.csv` | step 4 `activity_path`, variant 라벨 | `variant`, `activity`, `replicate_idx`. plate layout 이 필요 없다 | 없음 (csv) |
| 16 | `16_mame_agilent_numeric_confirmation.xlsx` | step 4 `remeasure_numeric_xlsx` | FID1B block. 순번이 primary 의 above-WT 부분집합을 센다 | `Agilent numeric confirmation` |

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
