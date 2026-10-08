# 구조 좌표 매핑과 3D 공간 분산 감사

- 감사 대상: 공개 `gyuminlee-repo/kuma`의 **9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4**
- 제품 버전: v0.16.73. 커밋 제목의 v0.16.73.01과 구별한다.
- 작성일: 2026-10-08
- 범위: 문서와 합성 재현만 추가한다. 제품 구현·모델 호출·실제 후보 선정은 수행하지 않는다.

## 목표와 판단 기준

목표는 **선정 위치가 접힌 단백질의 특정 공간에 몰리지 않는지 평가하는 것**이다. 3D Cα 거리 기반 분산이 이 목표를 직접 표현한다. 서열 위치 간 거리와 도메인별 분포는 다른 측정 축이며 3D의 동의어가 아니다. 서열상 먼 위치도 접힘에서 가까울 수 있다.

도메인 annotation은 서열 기반으로 별도 유지할 수 있다. KUMA에는 참조서열을 InterProScan에 제출하여 참조 번호 기준 `refDomains`를 얻는 경로가 이미 있다. 선정용 도메인은 이 참조 기준 자료를 사용한다. 구조 좌표는 도메인 annotation을 얻기 위한 필수 입력이 아니다. 근거: `python-core/sidecar_kuro/handlers/external.py:830–889`, `src/store/slices/inputSlice.helpers.ts:70–72`.

공간적으로 분산된 위치가 기능적으로도 다양하거나 더 나은 실험 결과를 낸다는 보장은 없다. 관측된 현상은 우선 **위치 편중**이라고 부른다. 최적화 과정의 local minimum에 갇혔다는 판단은 별도 증거가 필요하다. 이 문서는 특정 단백질의 실제 변이 위치나 성능 향상 전략을 제안하지 않는다.

## 현재 코드에서 확인한 핵심 문제

### 1. 선정 경로의 exact gate

`interface.py:267–289`의 `structure_matches_reference(a, r)`는 trailing stop과 양끝 공백을 정리한 뒤 비어 있지 않은 `a == r` 또는 `r in a`만 허용한다. 구조의 치환 1개와 구조 N말단 1개 결실은 거부된다. 참조가 구조의 연속 부분문자열인 방향만 허용되므로 “말단 절단이면 모두 허용”이라는 설명은 틀리다.

`misc.py:236–265`는 불일치 시 좌표 전체를 `None`으로 바꾼다. 구조 서열이 빈 문자열이면 gate 호출을 생략하고 좌표를 보존한다. 빈 sequence를 정확 일치처럼 취급하지 않는 fail-closed 계약이 필요하다.

### 2. 허용한 terminal offset을 좌표에 적용하지 않음

구조가 `HH + reference`이면 gate는 True지만 guard는 좌표 배열을 그대로 반환한다. 합성 fixture에서 참조 1번에 필요한 구조 3번 좌표는 1이지만 실제 배열의 1번 값 999가 유지됐다. exact substring 판정만으로는 참조 번호와 구조 번호가 일치하지 않는다.

### 3. 별도 dispersion과 선정의 계약이 다름

선정과 benchmark는 exact gate를 공유한다. `dispersion.compute_round_dispersion:100–223`은 accession frame에서 `map_ref_to_accession`을 호출한다. 단일 치환도 매핑하여 3D 계산을 계속한다. 모든 3D 경로가 치환 하나 때문에 일괄 1D로 떨어지는 것은 아니다.

`_build_position_map:194–228`는 Biopython global alignment에 match=2, mismatch=-1, gap open=-11, extend=-1, free end gaps를 쓴다. 첫 최적 alignment의 non-gap columns를 매핑한다. 치환도 매핑 대상이며 identity·coverage·동점 정렬 모호성 검사는 없다. `map_ref_to_accession:231–265`는 정렬된 mapped/dropped 집합만 반환하므로 명시적인 잔기별 대응과 사유가 부족하다.

### 4. 결측 좌표 처리의 서로 다른 의미

| 경로 | 현행 동작 |
|---|---|
| Pareto 전체 좌표 `None` | `abs(pos_i-pos_j)/max_pos` 서열 거리 |
| Pareto first mode 일부 좌표 결측 | `pairwise_ca_distance`가 최대 거리 1.0 반환 |
| Pareto centroid 일부 결측 | 존재하는 좌표만 평균. 한쪽 centroid가 없으면 평균 서열 위치 거리 |
| structural-diversity | 관측 Cα centroid와 좌표 없는 후보의 `(min_pos, mean_pos, max_pos)`를 같은 거리 공간에서 비교할 수 있음 |
| 별도 dispersion | valid Cα끼리 Å 평균. 2개 미만이면 `na` |

특히 structural-diversity의 혼합 fallback은 rigid translation에 불변하지 않다. 합성 fixture의 알려진 모든 좌표에 `(1000,1000,1000)`을 더했을 때 알려진 좌표끼리 거리는 그대로인데 선택 순서가 바뀌었다. 좌표 없는 후보의 서열 tuple이 이동하지 않기 때문이다. 모든 좌표가 있는 대조군은 선택이 유지됐다. fixture 표기의 A1G/C2G/D3G는 소프트웨어 테스트 식별자이며 실제 후보가 아니다.

### 5. 파서의 residue identity 손실

`alphafold._parse_pdb_ca:91–126`와 `_parse_pdb_seq:134–157`는 정수 author residue number만 사용한다. chain, insertion code, MODEL을 구별하지 않는다. 같은 정수 번호에서 처음 나타난 CA를 취하며 뒤 chain/model의 잔기가 앞 구조의 없는 번호를 채울 수 있다. 이 중 chain 혼합·삽입코드 축약·뒤 model의 채움은 합성 재현했다.

서열은 CA ATOM에서만 만들며 미관측 번호는 X로 채운다. deposited polymer sequence와 observed coordinate sequence를 구별해야 한다. `structure_file._parse_cif_ca:99–201`는 첫 model/label chain을 고르는 등 PDB와 다른 동작을 한다. author/label 번호와 insertion code를 보존하는 공통 residue table이 필요하다. mmCIF `B_iso_or_equiv`를 항상 pLDDT로 해석할 수 없다는 항목은 소스 검토이며 별도 실험 mmCIF 실행을 한 것은 아니다.

## 호출 경로

```text
파일/AlphaFold 좌표 로드
  external.py:452–519 → core._state
CSV 선정
  misc.handle_load_evolvepro_csv:268–315
  → _frame_checked_ca_coords:236–265
  → evolvepro.load_evolvepro_csv:666–707
       domain_aware_select → pareto_diversity_select
       또는 pareto_diversity_select / structural_diversity_select
benchmark
  misc.handle_run_benchmark:318–353 → 같은 guard
  → benchmark.run_benchmark → 전략별 selector
별도 공간 분산
  external.handle_compute_dispersion:765–784
  → dispersion.compute_round_dispersion:100–223
  → map_ref_to_accession → _dispersion_from_coords
```

`reference` coordinate frame의 dispersion은 제공된 PDB 좌표를 참조 번호로 직접 해석한다. accession frame과 같은 sequence 정렬 경로를 거치지 않는다. `_dispersion_from_coords`의 null은 모든 유효 구조 Cα에서 샘플링하므로 homolog proxy를 설계할 때 참조에 대응하는 eligible universe와 비교 universe를 일치시키는 문제가 남는다.

## 투영 계약 설계안: 미구현

bool만 느슨하게 바꾸지 않는다. model/chain을 고른 뒤 deposited polymer sequence와 관측 residue ID를 분리하고 참조→구조 대응을 만든다. 결과는 참조 길이의 `projected_ca` 배열로 재색인한다.

- `EXACT`: 유일하게 대응되는 알려진 서열 overlap이 동일함. 허용한 terminal tag/truncation을 기록하고 실제 offset을 적용함. geometry가 정확하다는 보증은 아님.
- `HOMOLOGY_MAPPED`: 치환·indel이 있는 서열 대응을 provenance와 함께 proxy로 사용할 수 있다는 상태. identity만으로 자동 승인하지 않음.
- `INCOMPATIBLE`: 모호한 alignment, 부재 sequence, chain/frame 미확립, 부족한 coverage 또는 명시한 정책에 맞지 않는 경우.

최소 반환 필드:

```text
status / reason_codes / effective_distance_mode
reference_hash / structure_hash / model / chain / alignment_version
identity_numerator / identity_denominator
reference_alignment_coverage / known_pair_coverage / ca_coverage
requested_position_coverage
(ref_position, polymer_position, full_residue_id, relation, coordinate_status)[]
projected_ca / eligible_positions / missing_or_ambiguous_positions
confidence_kind / source / warnings
```

identity 분모가 0이면 0%가 아닌 `null`이다. X/unknown 처리와 coverage 분모를 고정해야 한다. 구조 residue identity는 model, label/auth chain, label/auth sequence ID, insertion code, altloc을 보존한다. 동점 alignment에서 대응이 달라지는 위치는 ambiguous로 표시한다.

gap에 관측 좌표를 지어내지 않는다. 선형 보간을 실제 Cα처럼 사용하지 않는다. 결측을 최대 다양성으로 보상하거나 Å와 서열 index를 조용히 섞지 않는다. 3D를 계산할 수 없는 경우 `unavailable` 또는 명시적 eligible subset을 표시한다. 1D fallback을 허용하더라도 이것이 접힌 구조 분산의 증거를 대체하지 않는다고 표시한다.

CSV 선정·benchmark·dispersion·3D 표시가 같은 projection과 mask를 공유해야 한다. 새 알고리즘이나 정책의 효과를 이 문서에서 검증했다고 주장하지 않는다. 기존 Biopython 또는 가벼운 DP 구현으로 가능하지만 scoring·모호성·성능 검증이 필요하다.

### 회귀 사례의 설계 규격

- A: 동일 overlap과 terminal tag/truncation. 올바른 reindex와 없는 terminal 위치의 None을 검증한다.
- B: 높은 identity와 substitution/small indel. 치환 correspondence와 gap 위치 결측을 분리한다. 높은 identity가 geometry 정확도의 충분조건이라는 assertion을 만들지 않는다.
- C: 낮은 identity의 자동 투영을 거부하는 보수적 정책. `<40%`를 보편적 구조 불가능 법칙으로 쓰지 않는다.
- 반복 서열 ambiguity, chain/model/altloc, 삽입코드, 관측 CA 결측, rigid rotation/translation, 같은 구조의 PDB/mmCIF 일관성을 추가한다.

## 문헌에 따른 제한

- Rost 1999는 sequence identity만이 아니라 alignment 길이도 중요함을 보여준다. 30% 또는 50%를 보편적 거리 정확도 기준으로 쓰지 않는다. PMID 10195279, DOI [10.1093/protein/12.2.85](https://doi.org/10.1093/protein/12.2.85).
- Kosloff & Kolodny 2008는 서열이 비슷한 단백질도 다른 구조를 가질 수 있음을 분석한다. 높은 identity가 domain motion·상태 차이를 제거하지 않는다. PMID 18004789, DOI [10.1002/prot.21770](https://doi.org/10.1002/prot.21770).
- 3N0F/G 원논문은 Populus × canescens PcISPS 구조와 N말단 construct 조건을 기술한다. 이를 다른 종의 PtIspS 또는 임의 참조와 동일한 것으로 취급하지 않는다. 이 compact 재현에서는 실제 구조 다운로드/서열 대조를 실행하지 않았다. PMID 20624401, DOI [10.1016/j.jmb.2010.07.009](https://pmc.ncbi.nlm.nih.gov/articles/PMC2942996/).

## 선행 방법 및 공개 구현 비교

### 공개 레포의 역할과 한계

아래는 2026-10-08에 공식 저장소·문서에서 확인한 기능이다. 패키지를 설치하여 KUMA에 통합하거나 성능을 benchmark한 결과는 아니다. 대부분 **기하·시각화 도구**이며 KUMA 목적에 맞는 잔기 부분집합 선정기를 완성품으로 제공하지 않는다.

| 저장소 | 확인한 용도 | 라이선스·범위 |
|---|---|---|
| [Biopython / Bio.PDB](https://github.com/biopython/biopython) | 선택 원자의 좌표와 [NeighborSearch](https://biopython.org/docs/latest/api/Bio.PDB.NeighborSearch.html)로 거리·접촉 계산 | 기본 Biopython License Agreement. 일부 파일만 BSD-3-Clause 이중 라이선스이므로 전체를 BSD라고 하지 않음. 기존 의존성이라 우선 검토 가능 |
| [Biotite](https://github.com/biotite-dev/biotite) | AtomArray, distance, CellList로 좌표·이웃 계산 | BSD-3-Clause. 기하 API이며 diversity selector는 아님 |
| [ProDy](https://github.com/prody/ProDy) | buildDistMatrix, calcDistance, calcGyradius 및 구조 동역학 | MIT. 구조·동역학 toolkit이며 부분집합 최적화 엔진은 아님 |
| [Graphein](https://github.com/a-r-j/graphein) | protein contact graph, 거리 임계값 edge, k-NN edge | MIT. graph 구성용이며 분산 선정기를 제공한다고 확인한 것은 아님 |
| [3Dmol.js](https://github.com/3dmol/3Dmol.js) | 선택 잔기 색상·라벨·sphere 및 거리 선 시각화 | BSD-3-Clause. 시각화이며 통계·선정 알고리즘이 아님 |
| [Mol*](https://github.com/molstar/molstar) | 구조 선택·측정·annotation, MolViewSpec 장면 표현 | MIT. 풍부한 viewer이며 자동 분산 선정과 구별 |
| [CLUMPS](https://github.com/getzlab/CLUMPS) | 관측 변이의 구조상 clustering을 permutation null과 비교 | 검사한 root에서 라이선스 미확인. 코드 복사·도입 전 확인 필요. 분산 subset 선정과 반대 방향의 통계적 선행 사례 |
| [HotMAPS](https://github.com/KarchinLab/HotMAPS) | 구조상 유의한 local hotspot 탐지. 현재 README는 offline 사용자 PDB/AlphaFold와 Snakemake workflow도 기술 | 검사한 root에서 라이선스 미확인. cancer mutation setting의 null을 일반 잔기 분산에 그대로 적용하지 않음 |

설계상 시각화와 점수 계산을 분리한다. 현재 KUMA parser의 chain/model/insertion-code 결함을 유지한 채 viewer만 추가하면 잘못된 대응을 보기 좋게 표시할 수 있다. 검증된 residue table이 먼저다. 모든 쌍의 거리 행렬을 반드시 저장할 필요는 없으며 목적과 자료 크기에 맞춰 계산 방식을 정한다.

관련 원논문: Bio.PDB DOI [10.1093/bioinformatics/btg299](https://doi.org/10.1093/bioinformatics/btg299), Biotite DOI [10.1186/s12859-018-2367-z](https://doi.org/10.1186/s12859-018-2367-z), ProDy DOI [10.1093/bioinformatics/btr168](https://doi.org/10.1093/bioinformatics/btr168), [Graphein NeurIPS 2022](https://openreview.net/forum?id=9xRZlV6GfOX), 3Dmol DOI [10.1093/bioinformatics/btu829](https://doi.org/10.1093/bioinformatics/btu829), Mol* DOI [10.1093/nar/gkab314](https://pmc.ncbi.nlm.nih.gov/articles/PMC8262734/), CLUMPS DOI [10.1073/pnas.1516373112](https://pmc.ncbi.nlm.nih.gov/articles/PMC4603469/), HotMAPS DOI [10.1158/0008-5472.CAN-15-3190](https://pmc.ncbi.nlm.nih.gov/articles/PMC4930736/).

### 거리 지표와 부분집합 목적

서로 다른 질문을 구별한다. `d(i,j)=||x_i−x_j||`는 Cα 기하 측정이며 그 자체가 선정 알고리즘은 아니다.

| 방법·목적 | 답하는 질문 | 근거와 한계 |
|---|---|---|
| 선택점 내부 최소 쌍거리 / max-min dispersion | 선택 위치끼리 얼마나 가까이 몰리는가 | 먼 outlier가 유리할 수 있음. 전체 단백질이 덮였다는 보장은 별개 |
| metric k-center / coverage radius | 전체 대상 중 선택점에서 가장 멀리 떨어진 곳은 얼마나 먼가 | 최악의 미커버 영역을 평가. 내부 최소 쌍거리 최대화와 다른 목적 |
| farthest-first / FPS | 기존 선택점까지의 최소거리가 가장 큰 다음 점을 고르는 순회 | Gonzalez의 metric k-center 근사 결과를 quota·품질 가중·제한 pool 등 변형에 그대로 적용하지 않음 |
| facility-location | 전체 대상이 선택 집합으로 평균적으로 얼마나 대표되는가 | `Σ_i max_j∈S s(i,j)`. 밀집 영역의 비중 영향을 받으며 worst-case coverage와 다름 |
| DPP | 품질과 다양성을 kernel로 함께 표현할 수 있는가 | sampling, fixed-size k-DPP, MAP 선택은 다름. kernel scale과 PSD 조건에 의존하며 정확 최적해 보장으로 부르지 않음 |

선행 원문과 실제 범용 구현:

- Gonzalez 1985, DOI [10.1016/0304-3975(85)90224-5](https://www.cs.columbia.edu/~verma/classes/uml/ref/clustering_minimize_intercluster_distance_gonzalez.pdf). farthest-first의 metric k-center 결과이며 max-min dispersion과 목적함수를 혼동하지 않는다.
- [PyTorch3D sample_farthest_points](https://pytorch3d.readthedocs.io/en/latest/_modules/pytorch3d/ops/sample_farthest_points.html)는 실제 point-cloud FPS 구현이다. [저장소](https://github.com/facebookresearch/pytorch3d)는 BSD 라이선스이며 단백질 residue mapping·confidence 처리는 제공하지 않는다. KUMA에 새 Torch 의존성을 도입해야 한다는 제안이 아니다.
- [Submodlib](https://github.com/decile-team/submodlib)는 MIT 범용 subset 도구다. [facility-location](https://submodlib.readthedocs.io/en/latest/functions/facilityLocation.html)과 [disparity-min](https://submodlib.readthedocs.io/en/latest/functions/disparityMin.html)을 제공한다. 후자는 공식 문서상 non-submodular다. similarity 정규화와 kernel 정의를 확인해야 하며 raw XYZ에 기본 cosine을 적용하면 원점 의존성이 생길 수 있다. Kaushal et al. 2022, [arXiv:2202.10680](https://arxiv.org/abs/2202.10680).
- Kulesza & Taskar 2012, DOI [10.1561/2200000044](https://www.alexkulesza.com/pubs/dpps_fnt12.pdf)는 DPP의 품질·다양성 모델링 근거다. [DPPy](https://github.com/guilgautier/DPPy)는 MIT 범용 sampling 구현이며 단백질 전용 selector나 일반 MAP solver로 소개하지 않는다. [JMLR 2019 논문](https://www.jmlr.org/papers/v20/19-179.html). raw XYZ linear Gram은 rank가 최대 3이므로 큰 subset에 그대로 쓰는 것도 적절하지 않을 수 있다.

이번 확인 범위에서 단백질 잔기 분산 선정의 표준 완성 도구를 확립하지 못했다. 범용 기하 선정기와 단백질 구조 분석 도구를 연결할 수 있지만 앞선 mapping·결측·단위 계약이 필요하다. KUMA는 이미 Cα 거리와 maximin 형태의 반복 선정을 구현하고 있으므로 “외부 알고리즘이 없어서 3D를 못 쓴다”는 문제가 아니다. 현재의 잘못된 frame·fallback을 바로잡고 목적과 평가를 분명히 하는 일이 선행한다.

### 분산을 보는 화면과 수치의 설계 방향

다음 항목은 향후 비교·표시 설계이며 이번 PR에서 구현하거나 성능 검증하지 않았다.

- 3D 구조 위에 고유 선택 위치를 표시하고 가까운 선택 쌍을 확인한다. 변이 후보 수와 고유 residue 수를 분리한다.
- 선택점의 최소 쌍거리와 최근접거리 분포를 표시한다. 평균 쌍거리만 쓰면 먼 outlier가 가까운 중복을 가릴 수 있다.
- 전체 eligible residue에서 nearest-selected 거리의 평균·상위분위수·최댓값과 coverage curve를 별도로 표시한다. “선택점끼리 흩어짐”과 “전체가 덮임”을 같은 점수로 합치지 않는다.
- 같은 eligible universe와 같은 개수에서 random subset을 반복 비교하는 null을 사용하되 기존 제약도 일치시킨다. clustering이 유의하지 않다는 사실만으로 dispersion을 입증하지 않는다.
- 여러 치환의 centroid는 서로 다른 residue 집합을 같은 점으로 축약할 수 있다. 고유 residue union의 coverage와 후보별 centroid를 구별한다.
- 구조 상태·chain/assembly·domain 배치가 달라질 때 결과 안정성을 따로 본다. pLDDT는 국소 confidence이며 상대 domain 배치를 보장하지 않는다. [AlphaFold 공식 FAQ](https://alphafold.ebi.ac.uk/faq)의 PAE 설명처럼 residue 간 상대 위치의 불확실성도 고려해야 한다.

향후 검증은 균일 점군, 서로 다른 밀도의 두 lobe, core+outlier, 서열상 멀지만 공간상 가까운 hairpin, 중복 좌표, 같은 centroid의 다른 점 집합, 결측 좌표를 가진 합성 기하부터 비교할 수 있다. 작은 합성 집합에서는 각 목적의 전수 subset 결과와 비교할 수 있다. 이 비교는 geometry의 의미와 실패 조건을 검증하기 위한 것이며 생물학적 이득을 선언하는 실험이 아니다.

## 이번 증거의 범위와 재실행

`reproduce.py`와 `observations.json`은 이 문서 게시 준비 과정에서 **새로 실행한 합성 증거**다. 이전 보고서나 대화에 있던 테스트 수·공개 구조 통계·원시 로그를 이 PR의 새 검증으로 재사용하지 않는다.

script는 위 고정 SHA의 관련 파일과 현재 파일 bytes가 같아야 실행한다. core 함수는 이 checkout에서 직접 import한다. sidecar guard는 원본 AST의 함수 node를 변경 없이 실행하고 cached sequence lookup만 stub한다. 전체 sidecar import에 필요한 primer3 의존성을 확보하지 못했으므로 **sidecar 통합 테스트가 아니다**. dispersion의 네트워크 fetch는 합성 값으로 대체한다. 모델 호출과 외부 서열 제출은 없다.

```bash
# 감사 commit을 포함한 checkout. 프로젝트 Python 의존성 환경을 사용한다.
PYTHONDONTWRITEBYTECODE=1 python docs/audit/structure-projection-20261008/reproduce.py
```

이번 실행 결과는 합성 assertion 14개 PASS(exit 0)다. 기존 focused regression은 아래 명령으로 새 실행하여 79 passed(exit 0)를 얻었다. `focused-tests.log`에 출력이 있다.

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/test_structure_file.py tests/test_structure_parser_contracts.py tests/test_interface_residues.py -q -p no:cacheprovider
```

결과 JSON에는 감사 SHA, core source hashes, Python/Biopython version, expected/observed가 있다. Python 3.12.14와 Biopython 1.84에서 수행했다. 전체 CI·GUI·실제 프로젝트 입력·실험적 성능은 이 합성 증거의 범위 밖이다. 소스가 달라지면 기존 값을 통과시키려고 fixture 기대값을 자동 갱신하지 않는다.

## 고정 소스 링크

- [interface.py:194–289](https://github.com/gyuminlee-repo/kuma/blob/9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4/kuma_core/kuro/interface.py#L194-L289)
- [alphafold.py:91–157](https://github.com/gyuminlee-repo/kuma/blob/9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4/kuma_core/kuro/alphafold.py#L91-L157)
- [alphafold.py:364–386](https://github.com/gyuminlee-repo/kuma/blob/9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4/kuma_core/kuro/alphafold.py#L364-L386)
- [misc.py:236–353](https://github.com/gyuminlee-repo/kuma/blob/9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4/python-core/sidecar_kuro/handlers/misc.py#L236-L353)
- [evolvepro.py:1080–1370](https://github.com/gyuminlee-repo/kuma/blob/9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4/kuma_core/kuro/evolvepro.py#L1080-L1370)
- [dispersion.py:100–264](https://github.com/gyuminlee-repo/kuma/blob/9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4/kuma_core/kuro/dispersion.py#L100-L264)
- [structure_file.py:99–224](https://github.com/gyuminlee-repo/kuma/blob/9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4/kuma_core/kuro/structure_file.py#L99-L224)
