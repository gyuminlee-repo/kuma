# MAME 변이 목록 입력 사양

MAME 는 변이 목록을 두 가지로 받는다. KURO export 워크북이거나, 변이만 나열한 평범한 목록이다.

well 위치는 어느 쪽에도 적지 않는다. **잔기 position 오름차순이 곧 플레이트 순서**다. 배치는 세로 채움(A1, B1, C1 ... H1, A2)이다. 벤치가 클론 플레이트를 그 순서로 채우기 때문이다. `kuma_core/mame/layout.py` 의 `build_clone_plate_layout` 이 `canonical_plate_order` 로 그 순서를 세우고 `build_draft_layout` 이 n번째 점유자를 n번째 well 에 넣는다. 같은 position 에 치환이 여럿이면 시트에 적힌 순서로 안정 정렬한다. 조합 유전자형처럼 한 클론이 여러 행에 걸치면 그 클론의 가장 낮은 position 자리에 놓인다.

`Well` 열을 가진 파일은 다르다. 그 주소는 파일이 적은 사실이므로 정렬하지 않고 그대로 쓴다.

## 갈래 1: KURO export 워크북

`expected_mutations` 시트를 가진 워크북은 자동으로 이 갈래로 간다 (`kuma_core/mame/io/variant_list.py`, `KURO_SHEET`).

| 시트 이름 | 내용 |
|---|---|
| `expected_mutations` | 변이 한 행씩, 플레이트 순서. `kuma_core/kuro/plate_mapper.py:508` 이 쓴다 |
| `__kuma_meta__` (숨김) | 프로젝트 자동 매칭 키 |

`expected_mutations` 헤더는 아래 10개가 **순서까지** 일치해야 한다 (`kuma_core/mame/io/kuro_reader.py:13-24`).

```
mutant_id, position, wt_aa, mt_aa, wt_codon, mt_codon,
group_id, primer_set_ref, notation_type, status
```

이 중 MAME 가 읽지 않는 다섯 개(`wt_codon`, `mt_codon`, `group_id`, `primer_set_ref`, `notation_type`)는 비어 있어도 된다. 값을 지어내지 않는다.

`status` 는 설계된 상태 집합(`_DESIGNED_STATUSES`) 안에 있어야 한다. 벗어난 행은 배치되지 않으며, 배치되지 않은 행이 하나라도 있으면 읽기가 거부된다. 행 하나가 빠지면 그 뒤 변이가 전부 한 웰씩 당겨지는데 결과는 정상 플레이트처럼 보이기 때문이다. 단 `mutant_id` 가 WT 라벨인 행은 대조군 점유자이므로 status 와 무관하게 유지된다.

### 프라이머 플레이트 시트와는 순서가 다르다

같은 워크북의 `Fwd List`/`Fwd Plate` 는 KURO 가 설계 시트 index 로 배정한 프라이머 웰을 적은 시트다. MAME 가 채우는 클론 플레이트는 잔기 position 오름차순이다. 이미 position 순으로 적힌 워크북이 아니면 두 주소가 어긋난다. `validate_inputs` 가 둘을 대조해 어긋난 웰을 보고하지만(`kuma_core/mame/io/clone_plate_crosscheck.py`) 거부하지는 않는다. 어느 쪽이 랙에 꽂힌 튜브인지는 워크북에 적혀 있지 않기 때문이다. 자세한 동작은 [Step 2 문서](../mame/02-review.md)에 있다.

## 갈래 2: 변이만 나열한 목록

`.csv`, `.tsv`, `.txt`, `.xlsx` 를 받는다. 컬럼 하나면 충분하다.

```csv
variant
S65T
Y66H
T203Y
WT
```

`S65T` 가 A1, `Y66H` 가 B1, `T203Y` 가 C1, `WT` 가 D1 이다.

컬럼명 자동 인식 후보는 `variant`, `variants`, `mutant`, `mutants`, `mutation`, `mutations`, `mutant_id`, `variant_id` 다. 후보가 없어도 비어있지 않은 헤더가 정확히 하나면 그 열을 쓴다. 단 그 하나가 변이 표기나 WT 라벨로 읽히면 헤더가 아니라 데이터로 본다(아래 참조). 그 외에는 호출부가 시트와 컬럼을 지정한다 (`inspect_variant_source` 가 후보를 보고한다).

### 헤더가 없는 파일

첫 행의 비어있지 않은 셀이 정확히 하나이고 그 값이 변이 표기나 WT 라벨이면 헤더 없는 파일로 본다. 그 행부터 데이터로 읽고 행 번호는 1부터 센다. 이 판정은 호출부가 컬럼을 지정했는지와 무관하다.

```csv
S65T
Y66H
```

`S65T` 가 A1, `Y66H` 가 B1 이다. 이 판정이 없던 동안 첫 행이 컬럼명으로 소비돼 첫 변이가 조용히 사라졌고, 그 뒤 변이가 전부 한 웰씩 당겨졌다.

변이 표기는 1-letter 형식만 받는다. 정규식은 `kuma_core/kuro/mutation.py:13` 의 `^([A-Z])(\d+)([A-Z])$` 하나뿐이다. `p.Ala123Val` 같은 3-letter 표기, 소문자, 슬래시로 이은 다중 변이는 거부된다.

WT 대조군 라벨은 `wt`, `wildtype`, `wild-type`, `wild type`, `control` 이다. 목록 안에 두면 그 자리 well 이 대조군이 되고, 생략하면 마지막 변이 다음 well 에 붙는다.

## 갈래 3: 앱이 발급한 템플릿

Analyze 입력 화면의 변이 목록 선택 옆 "템플릿 받기" 버튼이 `well`, `variant` 두 열짜리 xlsx 를 쓴다. `well` 열에는 96개 주소가 세로 채움 순서로 이미 적혀 있고 마지막 well 인 `H12` 에 `WT` 가 들어간다 (`kuma_core/mame/io/variant_template.py`).

채울 것은 `variant` 열뿐이다. `well` 열은 손대지 말고, 행을 지우거나 정렬로 순서를 바꾸지도 않는다. 그 열이 이 파일이 어느 well 을 뜻하는지 말하는 유일한 근거다.

## 거부 규칙

전부 경고가 아니라 `ValueError` 다. 잘못 배치된 채 진행되는 것보다 낫다는 판단이다.

| 상황 | 근거 |
|---|---|
| 파싱 불가한 변이 표기 | `parse_mutation_notation` |
| 같은 변이 중복 | 웰마다 서로 다른 변이여야 채점된다 |
| WT 라벨 행 두 개 | 플레이트는 대조군 웰을 하나만 갖는다 |
| 빈 목록 | 배치할 것이 없다 |
| 읽혔으나 배치 못 한 행 | 그 뒤 변이가 전부 한 웰씩 밀린다 |

용량은 클론 95개 + WT 1개 = 96 well 이다 (`kuma_core/mame/layout.py`, `MUTANT_CAPACITY`). 같은 `mutant_id` 를 가진 행 여럿은 클론 하나로 세므로 한도에 걸리는 것은 행 수가 아니라 클론 수다. 넘치면 부분 배치 없이 전량 비우고 넘친 클론 이름을 돌려준다.

## `__kuma_meta__` 필드

`kuma_core/mame/io/kuma_meta.py` 가 읽는 필드는 넷이다.

| 필드 | 내용 |
|---|---|
| `project_id` | 프로젝트 매칭 키. 이 값이 없으면 시트 전체를 무시한다 |
| `kuma_version` | 내보낸 앱 버전 |
| `kuro_module_version` | KURO 모듈 버전 |
| `exported_at` | 내보낸 시각 |

## 프로젝트 자동 매칭

`MameTab.tsx` 가 워크북을 받으면 `read_kuma_meta` 로 `project_id` 를 읽는다. 현재 프로젝트와 같으면 그대로 쓴다. 다르면 최근 프로젝트 목록에서 같은 `project_id` 를 찾아, 있을 때만 그 프로젝트로 전환할지 묻는다. 시트가 없거나 읽기에 실패하면 조용히 현재 상태로 진행한다.

## 사용자 안내

입력 예시는 [샘플 템플릿 안내](../../templates/README.md)를 참고한다.
