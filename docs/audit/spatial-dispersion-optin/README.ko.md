# Trusted-coordinate 3D 분산 진단: opt-in 구현

기준 공개 main: `9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4` (v0.16.73).
문서 감사 PR #3의 후속이며 기존 선택 기본값·화면·RPC·저장 형식·parser는 변경하지 않는다.

## 구현한 범위

`kuma_core.kuro.spatial_dispersion`는 **이미 올바르게 참조 위치에 대응시킨 단일 model/chain Cα 좌표**를 받는 명시적 Python API다. 현재 구조 cache를 자동으로 연결하는 adapter는 없다. finite 좌표라는 이유만으로 신뢰할 수 있다고 판정하지 않는다. 호출자가 frame/mapping/관측 좌표의 적합성을 먼저 확립해야 한다.

- 전체 residue identity(model, chain, author number, insertion code)를 보존한다. reference position은 양의 정수다.
- missing/NaN/Inf 좌표는 제외 사유와 위치로 보고한다. 1D 거리·가상 좌표로 바꾸지 않는다.
- 완전히 같은 중복 행만 축약한다. 같은 위치의 score/좌표/identity 상충과 구조 residue의 다대일 대응은 거부한다. 같은 위치의 여러 치환 score를 어떤 규칙으로 대표시킬지는 상류에서 명시적으로 결정해야 한다.
- 기존 `structural_diversity_select`의 full-pool/kappa0 경로를 단일위치 adapter로 재사용하고 top-score와 seeded random을 제공한다. 기존 알고리즘의 기본값은 그대로 둔다.
- 선택점 내부 최소 쌍거리·선택점 최근접거리·전체 eligible candidate의 nearest-selected 거리·평균/최대 coverage 거리·top-k 대비 합성 score gap을 따로 보고한다.

목표는 접힌 구조에서의 공간 분포를 투명하게 측정하는 것이다. 기능적 다양성·독립성·epistasis·fitness를 예측하지 않는다. 실제 단백질 입력·외부 서비스·실험·유료 모델을 사용하지 않았다.

## 고정 비교 계약 v1

`synthetic-comparison.json`의 contract가 기계 판독 가능한 정본이다.

1. 모든 방법은 같은 finite-coordinate 고유 reference-position universe와 같은 k를 사용한다. 제외된 위치의 높은 score도 어떤 방법에만 남기지 않는다.
2. k는 정수이며 `0 ≤ k ≤ eligible count`다. 부족하면 오류다. 방법별 축소나 조용한 top-up은 없다.
3. FPS seed는 score 내림차순 → reference position 오름차순이다. 이후 nearest-selected Euclidean distance 최대 → score 최대 → position 최소다. 거리 tie는 **계산된 float의 정확한 동률**이다. near-tie의 rounding 민감성은 남는다.
4. random은 position 기준 canonical order를 만든 뒤 비복원 sampling한다. 합성 비교의 seeds는 0–31이며 global RNG를 바꾸지 않는다.
5. legacy Pareto 비교는 `first`, `pool_multiplier=2`, `entropy_weight=0`, `distance_mode=3d`다. 모든 앱 모드를 대표한다고 부르지 않는다. legacy structural 비교는 full eligible pool, kappa0, anchor 없음, 단일 위치만 사용한다.
6. 단위는 모두 Å다. 선택점 최근접거리는 자기 자신을 제외하며 candidate coverage는 선택점 자신의 거리0을 포함한다. k0의 coverage와 k<2의 최소 쌍거리는 null이다. 다른 위치의 동일 좌표는 정상적으로 거리0이다.
7. score gap은 같은 universe의 top-k score sum에서 해당 선택 score sum을 뺀 값이다. score는 임의 합성 값이며 퍼센트 손실·생물학적 품질로 변환하지 않는다.
8. labelled outlier는 fixture가 명시한 합성 점이다. 실제 단백질의 말단이나 linker를 자동으로 이상치라 판정하거나 제거하지 않는다.

입력 순서를 바꿔도 canonical order와 tie 규칙은 같다. near-tie가 없는 합성 fixture에서 translation·90도 및 비직교 rotation·uniform scaling을 검증했다. 모든 floating-point 극단값에서 동일한 순서를 보장한다는 주장은 하지 않는다. 기존 selector의 제곱 연산에 안전하지 않은 전체 좌표 span과 표현 범위를 넘는 pair distance는 명시적 ValueError로 중단하며 비유한 metric을 JSON으로 내보내지 않는다.

## 재사용 여부에 대한 실제 결과

**7개 합성 fixture 모두 trusted adapter, 비교 script에만 있는 독립 표준 FPS, 기존 `structural_diversity_select`의 full-pool/kappa0 선택 순서가 같았다.** 새로운 최적화 방법이 기존보다 우월하다는 결과가 아니다. 추가된 가치는 제한된 신뢰 좌표 계약, sparse position 처리, 명시적 결측 보고와 분리된 진단 지표다. production에 별도 FPS loop를 추가하지 않는다. adapter는 하나의 row에 정확히 하나의 좌표만 주므로 다중잔기의 centroid 요약을 사용하지 않는다. 임시 dense index를 원래 reference position으로 다시 변환하고 residue identity를 보존한다.

예시 실측(전체 결과는 JSON):

| 합성 fixture / 방법 | 최소 쌍거리↑ | candidate max 거리↓ | score gap↓ |
|---|---:|---:|---:|
| line-score-cluster / top score | 1 | 19 | 0 |
| 같은 fixture / legacy Pareto pool2 | 3 | 10 | 5 |
| 같은 fixture / FPS 및 legacy fullpool | 10 | 3 | 8 |
| core+labelled outlier / top score | 1 | 99 | 0 |
| 같은 fixture / FPS 및 legacy fullpool | 2.8284 | 1 | 13 |

FPS의 coverage 개선과 score gap 증가가 함께 나타난다. outlier를 더 멀리 옮겨도 FPS는 이 점을 선택했다. 우수한 생물학적 후보가 선택되었다는 뜻이 아니다. random32의 metric 범위·평균·선택점 최근접거리 표본·seed별 선택 위치도 포함했다. 서로 다른 fixture는 universe 자체가 다르므로 그 사이 수치 차이를 동일 조건 성능 우위로 읽지 않는다.

## 사용 예시와 실행

새 API를 명시적으로 import해야 하며 기존 CSV/GUI 흐름에서 자동 활성화되지 않는다.

```python
from kuma_core.kuro.spatial_dispersion import (
    ResidueIdentity, ResiduePoint, prepare_trusted_residues,
    select_farthest_first, measure_dispersion,
)
# 합성 예시다. 실제 사용 시 좌표-참조 대응은 호출자가 별도 검증해야 한다.
points = [
    ResiduePoint(1, ResidueIdentity("1", "A", 10), (0., 0., 0.), 2.),
    ResiduePoint(2, ResidueIdentity("1", "A", 10, "A"), (5., 0., 0.), 1.),
]
data = prepare_trusted_residues(points, frame_id="synthetic:reference:1/A")
selected = select_farthest_first(data, 2)
metrics = measure_dispersion(data, selected)
```

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/test_spatial_dispersion.py -q
PYTHONDONTWRITEBYTECODE=1 python scripts/compare_spatial_dispersion.py > comparison.json
```

helper는 Python 표준 라이브러리만 사용한다. 새 의존성·Torch·구조 예측 모델을 추가하지 않았다. 재사용하는 FPS 경로의 scratch memory는 O(n), 거리 계산은 O(nk)다. metric 계산은 O(k²+nk)이며 거리 전행렬을 저장하지 않는다.

## 검증과 한계

최종 로컬 검증: 새 contract test 27개 PASS. 기존 EVOLVEpro/Pareto/parser/interface 검사와 함께 93개 PASS(exit0)를 얻었다. 독립 검토자도 새 27개를 재실행했고 비교 JSON의 byte 일치를 확인했다. `focused-tests.log`는 아래 묶음의 실제 출력이다.

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/test_spatial_dispersion.py tests/test_evolvepro.py tests/test_pareto_esm.py tests/test_structure_file.py tests/test_interface_residues.py -q -p no:cacheprovider
```

로컬 전체 tests 수집은 primer3, python_calamine, xlwt 미설치로 중단됐다. 3,469개 수집과 71 collection errors는 전체 suite 통과가 아니다. 원격 PR CI는 별도 확인하며 skip된 실제 외부 데이터 경로를 통과로 세지 않는다.

- 테스트는 hand-computed 거리, k0/1/n, 잘못된 k, input permutation, distance/score/position tie, rigid transform, scaling, missing/nonfinite, 중복 score·좌표 충돌, residue identity, hairpin, labelled outlier, 수치 overflow와 비교 cardinality를 다룬다.
- 독립 검토에서 비유한 중복의 잘못된 축약과 finite 결과의 중간 overflow를 찾아 regression을 추가했다. 혼합 부호 score sum은 드문 overflow 시 표준 라이브러리의 정확한 binary-rational 합으로 재시도한다.
- 선택 최소거리 최대화와 전체 target의 k-center coverage는 서로 다른 목적이다. FPS를 최적 max-min 해법이나 품질 가중/제약을 포함한 2-approximation이라고 부르지 않는다.
- 검증되지 않은 homolog mapping, parser 전체 redesign, multi-chain/assembly 해석, GUI 연결, 실험적 효능 검증은 범위 밖이다. 이것들을 확인하기 전 기존 raw cache에 helper를 자동 연결하지 않는다.

선행 알고리즘: Gonzalez 1985, DOI [10.1016/0304-3975(85)90224-5](https://doi.org/10.1016/0304-3975(85)90224-5). KUMA 현행 구현과 문헌/레포 비교는 [문서 PR #3](https://github.com/gyuminlee-repo/kuma/pull/3)에 있다. 본 구현은 해당 알고리즘의 제한된 기하 진단 적용이며 새로운 생물학적 최적화 주장이나 성능 보장을 추가하지 않는다.
