# KURO — Kernel for Upstream Recombination Oligodesign


**한국어** | [English](README.md)

Gibson Assembly 기반 SDM 프라이머 배치 설계 데스크톱 앱.

![KURO Overview](docs/kuro_overview.png)

https://github.com/user-attachments/assets/f95e65ca-22d2-4479-a06b-8dcd553571be

변이 목록(텍스트/EVOLVEpro CSV/MULTI-evolve CSV)과 템플릿 시퀀스(GenBank/SnapGene)를 입력하면, overlap extension 방식의 SDM 프라이머 쌍을 자동 설계한다.

## 주요 기능

- **EVOLVEpro / MULTI-evolve CSV 입력**: EVOLVEpro(`variant`, `y_pred`) 또는 MULTI-evolve(`mutation`, `property_value`) 출력 CSV 로드 — 컬럼 형식 자동 감지. 점수 내림차순 정렬 → 설정 개수만큼 자동 선정. **위치 다양성(position diversity)** 필터로 아미노산 위치당 최대 N개 제한 가능 (동일 위치 후보 점수 차이 2% 이내 시 Grantham 1974 거리가 낮은 보수적 치환 우선). **도메인 다양성(domain diversity)** 필터로 단백질 구조 도메인 간 분산 선택 (InterPro/Pfam 자동 조회 또는 수동 입력). **Pareto 다양성** 으로 MODIFY 방식의 위치 분산 최대화. **σ-Adaptive Pool**: EVOLVEpro Round와 Round size 입력 시 누적 데이터 기반으로 후보 풀 범위와 entropy 가중치를 자동 보정 (K = 0.50→0.25, entropy = 0.30→0.15, Round 1→5+)
- **배치 변이 파싱**: `Q232A` 형식의 변이 목록 → 코돈 위치 자동 계산 + WT 코돈 검증
- **코돈 전략 선택**: Min. changes (WT 대비 최소 염기 변이) 또는 Optimal (E. coli 최적 코돈) 중 선택 가능
- **Overlap upstream 설계**: overlap 영역이 mutation codon 바로 앞(upstream)에 위치 (EVOLVEpro 방식)
- **Polymerase 프로파일 선택**: 7종 내장 프로파일 (Benchling, Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL). 각 프로파일은 제조사 매뉴얼 기준으로 Tm 계산 방법·염 농도·DNA 농도·GC 범위가 보정되어 있음. Custom Polymerase 다이얼로그로 사용자 정의 프로파일을 생성하면 `~/.kuro/custom_polymerases.json`에 영구 저장됨. 프로파일 변경 시 UI의 Tm 타겟과 GC 범위가 즉시 갱신
- **Tm 계산**: SantaLucia 1998 nearest-neighbor 모델 사용. 염/DNA/divalent 농도는 선택한 polymerase 프로파일에 따라 달라짐 (예: Phusion HF 222 mM monovalent, Q5 150 mM monovalent + 2000 nM DNA). 기본 Tm 타겟 Fwd 62°C, Rev 58°C, Overlap 42°C — Advanced Options에서 조정 가능
- **점진적 Tm tolerance**: Fwd/Rev 각각 ±0.5°C부터 시작, ±0.5씩 독립 확장 (최대 ±3.0°C)
- **GC% 범위**: 기본 40-60% (Advanced Options에서 변경 가능). 범위 밖 프라이머에 패널티 부여
- **프라이머 길이 제한**: Fwd/Rev min/max 길이 제약 (Advanced Options에서 선택적 활성화)
- **Hairpin / Homodimer 검증**: primer3 calc_hairpin/calc_homodimer로 이차 구조 체크. Tm, dG(kcal/mol) 표시
- **합성 품질 점수**: IDT/Twist 가이드라인 기반 올리고 합성 난이도 평가 (0-100). Homopolymer, GC-rich 연속, 디뉴클레오타이드 반복, 극단 GC% 감점
- **Sequence Map**: 접이식 SVG 선형 CDS 맵. 돌연변이 위치, 도메인 영역, 밀도 히스토그램으로 클러스터링 감지. 히스토그램 바 hover 시 해당 AA 구간의 mutation 수 툴팁 표시
- **컬럼 정렬**: 모든 결과 컬럼 정렬 가능 (y_pred, 합성 점수 포함). Plate map export에도 정렬 순서 반영
- **후보 비교 및 교체**: 프라이머 서열 클릭 시 후보 비교 팝오버 (candidate 1개여도 클릭 가능). 수동 교체 시 결과 테이블에 amber 하이라이트
- **커스텀 프라이머 평가**: 후보 팝오버에서 직접 서열 입력 → Tm, GC%, hairpin, off-target 즉시 계산
- **실패 돌연변이 재시도**: 실패한 mutation 클릭 → Tm/GC%/길이/tolerance 조절 → 조절된 파라미터로 재설계 → 후보 선택
- **Position Rescue**: 프라이머 설계 실패 시 EVOLVEpro pool에서 같은 위치의 대안 variant를 자동 시도(Pool Cascade)하고, 그래도 실패하면 Tm tolerance(±5.0°C)와 GC 범위(±5%)를 완화하여 재시도(Auto-Relax). 결과 테이블에 rescue 뱃지 표시 (초록 `↻` pool cascade, 노랑 `⚡` auto-relax), Design Report에 rescue 통계 표시
- **실패 시 자동 채움(Fill on failure)**: 활성화 시(기본 꺼짐) 일부 mutation 실패해도 추가 후보로 요청 수만큼 자동 채움
- **Off-target 검증**: template sense/antisense strand에서 비특이적 결합 자동 검출. OT `!!` 클릭 시 결합 위치·strand·Tm 상세 팝오버
- **96-well Plate Map**: Fwd/Rev 쌍 연동 플레이트. 96개 초과 시 multi-plate 슬라이드 (Plate N Fwd ↔ Plate N Rev). 테이블 정렬 연동
- **Echo 525 / JANUS export**: 액체 핸들러 매핑을 XLSX 워크북으로 내보내기. Echo: 384-well 소스 플레이트 레이아웃(Fwd/Rev 홀짝행 인터리브) + 전송 목록. JANUS: Fwd/Rev 96-well 래크 레이아웃 + 전송 목록. CSV도 지원
- **Workspace 저장/불러오기**: 파라미터 + 설계 결과를 `.kuro.json`으로 저장하여 세션 간 이동 가능
- **데스크톱 GUI**: Windows / macOS / Linux 크로스플랫폼 앱

## 선택 전략 (EVOLVEpro / MULTI-evolve 모드)

EVOLVEpro 또는 MULTI-evolve CSV 로드 시 어떤 mutation을 프라이머 설계 대상으로 선정할지를 결정하는 전략. 독립 체크박스로 자유 조합 가능.

| 전략 | 설명 | 사용 시점 |
|------|------|-----------|
| **Top-N by score** | 예측 적합도(y_pred / property_value) 내림차순으로 상위 N개 선택. N = 최대 프라이머 수 설정 (기본 95). | 기본 랭킹. 예측 적합도만 기준으로 할 때. |
| **Position diversity** | 아미노산 위치당 최대 mutation 수 제한 (기본: 위치당 1개). 동일 위치 두 후보 점수 차이 2% 이내 시 Grantham 1974 거리가 낮은 보수적 치환 우선 선택. 다른 전략 적용 전 사전 필터로 동작. | 특정 위치에 mutation이 과도하게 집중되는 것을 방지. |
| **Domain diversity** | 단백질 구조 도메인별로 mutation 할당량을 배분 (비례 배분 또는 균등 배분). 도메인 정보는 UniProt accession으로 InterPro/Pfam에서 자동 조회하거나 수동 입력. 할당량 미달 도메인은 경고(⚠) 표시. | 한 도메인이 y_pred 상위를 독점할 때, 모든 기능 영역을 균형 있게 탐색하기 위해. |
| **Pareto diversity** | Greedy maximin 위치 선택: 이미 선택된 mutation과 가장 먼 위치의 mutation을 반복 선택하여 공간적 분산을 극대화. | 좁은 영역에 mutation이 밀집되는 것을 방지. MODIFY 접근법 (Ding et al., *Nature Communications*, 2024) 기반. |
| **Entropy-guided** (β) | 위치별 y_pred 분포의 Shannon entropy (가중치 0.3)를 Pareto 점수에 혼합. 동일 위치에서 다수 mutation이 비슷한 점수로 분포할 때(불확실성 높을 때) 우선 선택. | 적합도 경관에 여러 봉우리가 존재할 가능성이 있을 때 국소 최적 탈출. Pareto diversity 활성화 필요. |

**조합 예시:**
- Domain + Pareto: 도메인별 할당량 배분 후, 각 도메인 내에서 Pareto 분산 적용
- Position + Domain: 위치당 개수 제한 후, 도메인 간 배분
- Pareto + Entropy-guided: 공간 분산 + 불확실성 우선 탐색

**참고 문헌:**
- Ding D, Shaw AY, Sinai S, et al. Protein design using structure-predicted residue preferences and sequence-predicted fitness. *Nature Communications*, 15:6729 (2024). PMID:39080249 — MODIFY: Pareto fitness-diversity 공동 최적화

## 설치

[Releases](https://github.com/gyuminlee-repo/KURO/releases) 페이지에서 최신 인스톨러를 다운로드한다.

- **Windows**: `KURO_x.x.x_x64-setup.exe` (NSIS 인스톨러)

## 사용법

1. Input 패널 상단의 **Try sample →** 클릭 시 예제 파일 자동 로드 후 결과 확인 가능. 또는:
2. 시퀀스 파일 로드 (GenBank .gb / SnapGene .dna)
3. Target Gene 드롭다운에서 타겟 유전자 CDS 확인 (자동 선택)
4. 변이 입력 (텍스트 직접 입력, EVOLVEpro CSV 또는 MULTI-evolve CSV 로드)
5. 코돈 전략 선택 (Min. changes / Optimal)
6. (선택) Advanced Options에서 Tm 타겟, GC% 범위, 프라이머 길이 조정
7. **Design Primers** 클릭
8. Fwd/Rev 서열 클릭 → 후보 비교 팝오버에서 교체 가능
9. HP 컬럼 클릭 → hairpin/homodimer 상세 (Tm, dG)
10. File → Export Excel / Save Workspace

상세 설명은 [사용자 가이드](USER-GUIDE.ko.md) 참조.

## 라이선스

[GPL v2](LICENSE)
