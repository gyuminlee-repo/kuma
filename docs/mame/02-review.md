# Step 2. Sequencing Review

per-barcode mutation verdict 와 96-well plate view 를 나란히 본다.

## 8-class verdict

코드 `VerdictClass` enum (kuma_core/mame/models.py) 기준. 분류는 fail-first 우선순위로 동작한다 (kuma_core/mame/compare/verdict.py).

| Verdict | 의미 |
|---|---|
| `PASS` | 관찰 AA 변이가 설계(기대) 변이와 정확히 일치 |
| `WRONG_AA` | 기대 위치 변이 불일치, 기대 변이 누락, 또는 window 밖 예상외 변이 |
| `AMBIGUOUS` | 기대 변이는 모두 일치하나 인접(±codon window) 추가 변이 또는 indel 이벤트 신호 |
| `MIXED` | well 내 혼합 (유의한 2nd allele) |
| `FRAMESHIFT` | frameshift window 내 연속 nucleotide indel |
| `MANY` | cutoff·설계를 모두 초과한 과다 AA 변이 |
| `LOWDEPTH` | read depth 미달 (또는 depth 헤더 부재 시 file-size fallback) |
| `NO_CALL` | consensus N(no-call) 과다로 AA call 신뢰 불가 |

## 2.1 Inputs

실행 입력(run 폴더, expected 워크북, reference FASTA, sample map)을 고르고 Run 또는 Validate 를 누른다. Janus 장비 설정은 이 화면에 없다. step 3 소관이다.

### 입력을 바꾸면 이전 결과가 지워진다 (v0.15.14)

run 폴더, expected 워크북, reference FASTA, sample map 중 하나라도 바꾸면 이전 실행이 만든 것이 지워진다. verdict 와 플레이트 맵, 산출물 안내가 모두 사라지고 2.2 는 실행 전 상태로 돌아간다. 끝난 실행의 화면이 새 입력의 결과처럼 보이는 것을 막기 위한 동작이다. 같은 경로를 다시 골랐을 때는 아무 일도 일어나지 않는다. 백엔드로 보내는 분석 파라미터(mode, CDS 좌표, raw run 파라미터 등)도 같은 규칙을 따른다. 출력 경로는 입력이 아니므로 무효화하지 않으며 화면 표시용 임계값인 `minFilteredDepth` 도 마찬가지다.

## 2.2 Review

좌측: verdict table (NB01/NB02/NB03/ALL 필터). 우측: 96-well plate map (colorblind-safe toggle).

### Per-plate verdict bar (NGS 효율 그래프)

각 plate 별 verdict 비율 stacked bar chart. PPT slide 6 의 "NGS 효율" 그래프와 동일 표현.

<!-- TODO: insert screenshot of verdict bar chart -->

### 매핑 정합성 경고 (v0.15.14)

실행이 끝나면 각 well 의 관측 아미노산 변화를 그 well 자신의 expected 변이 및 다른 well 의 expected 변이와 대조한다(`kuma_core/mame/qc/mapping_integrity.py`). 자기 일치율이 낮고 교차 일치율이 높으면 well 과 변이의 대응이 어긋난 상태로 판정하고 2.2 상단에 경고를 띄운다. 변이가 관측된 well 수, 자기 일치율, 교차 일치율을 함께 표시한다.

- 실행을 막지 않는다. 이미 끝난 결과에 대한 판단이므로 경고만 띄운다.
- 변이가 관측된 well 이 24개 미만이면 판정하지 않는다. 표본이 작으면 우연한 라벨 겹침이 신호와 구분되지 않는다.
- 개별 well 은 각자의 expected 집합에 대해 정상적으로 분류되므로 실행 전 입력 검사로는 이 실패를 잡을 수 없다. 플레이트 전체를 함께 봐야 드러난다.

### 레이아웃 출처 (v0.15.14)

analyze 응답에 `layout_provenance` 가 항상 실린다. well 과 sample 의 대응을 무엇이 만들었는지 기록하는 필드이며 값은 두 가지다.

| `source` | 의미 |
|---|---|
| `explicit_well_layout` | 운용자가 준 well layout |
| `inferred_draft_layout` | 실행 시점의 변이 목록에서 계산한 초안 |

세 번째 값 `sample_map_xlsx` 는 v0.15.24 에 사라졌다. sample map 은 플레이트를 한 번 더 적는 파일이었고 변이 목록과 나란히 유지되지 못했다.

읽은 워크북 경로(`expected_path`)와 이 run 이 점유한다고 선언한 웰(`selected_wells`)이 함께 실린다. `selected_wells` 가 null 이면 앞쪽 N+1 웰을 쓴 것이고, 이는 이 필드가 생기기 전 모든 run 의 동작과 같다. 추론된 레이아웃이 운용자가 지정한 레이아웃처럼 보이지 않게 하려는 필드다.

선언한 웰이 점유자보다 많으면 남는 쪽은 `unused_wells` 로 함께 실린다. 거절이 아니다(선언이 캠페인보다 넓은 것 자체는 벤치에 대한 거짓말이 아니다). 다만 조용히 자르면 결과만 보고는 선언한 적 없는 웰과 구분할 수 없어서 이름을 적는다. 반대 방향, 즉 점유자보다 웰이 적은 선언은 거절이며 demux 앞에서 막힌다.

레이아웃이 이름을 대지 않은 웰에서 온 레코드 수는 `off_layout_records` 로 함께 실린다. 거절이 아니라 보고다. 비었다고 선언한 웰에서 read 가 나오는 것과 바코드 crosstalk 는 같은 신호를 내고, 개수만으로는 둘을 가를 수 없다.

## Layout

- Verdicts table min-height 480 px, Plate plate view min-height 360 px.
- 또는 resizable splitter 로 두 영역 자유 조절.

→ [Step 3. Janus 장비 설정](03-janus.md) 은 선택 단계다. 시퀀싱 판정만 필요하면 여기서 멈춰도 된다.

→ [Step 4. Activity Data](04-activity.md)
