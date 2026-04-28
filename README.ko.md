# kuma — 프라이머 설계(Kuro) + NGS 검증(Mame)

**한국어** | [English](README.md)

`kuma`는 두 서브툴을 하나의 Tauri 데스크톱 앱으로 묶는다:

- **Kuro** — *Kernel for Upstream Recombination Oligodesign.* Gibson Assembly 기반 SDM 프라이머 일괄 설계.
- **Mame** — *Mutagenesis Assessment & Microplate Export.* Oxford Nanopore NGS 판정. 어떤 클론이 의도한 돌연변이를 가졌는지 검증.

Kuro 탭에서 프라이머를 설계하고 실험·시퀀싱 후 Mame 탭으로 넘어가 의도한 돌연변이가 제대로 들어갔는지 판정한다.

![kuma overview](docs/kuro_overview.png)

프로젝트 폴더로 Kuro 설계 결과와 Mame 검증 결과를 연결해, 올리고 주문부터 시퀀싱 판독까지 수 주의 시간차가 있어도 작업이 이어진다. Kuro가 내보내는 xlsx에 숨김 시트 `__kuma_meta__`를 삽입해, 나중에 Mame에서 파일을 드롭만 해도 출처 프로젝트를 자동 인식한다.

---

## 탭 구성

### Kuro — SDM 프라이머 설계

변이 목록(텍스트 / EVOLVEpro CSV / MULTI-evolve CSV)과 템플릿 시퀀스(GenBank / SnapGene)를 입력하면, overlap extension 방식의 SDM 프라이머 쌍을 자동 설계한다.

- **EVOLVEpro / MULTI-evolve CSV 입력**: EVOLVEpro(`variant`, `y_pred`) 또는 MULTI-evolve(`mutation`, `property_value`) 출력 CSV 로드 — 컬럼 형식 자동 감지. 점수 내림차순 정렬 → 설정 개수만큼 자동 선정. **위치 다양성** 필터로 아미노산 위치당 최대 N개 제한 가능 (동일 위치 후보 점수 차이 2% 이내 시 Grantham 1974 거리가 낮은 보수적 치환 우선). **도메인 다양성** 필터로 단백질 구조 도메인 간 분산 선택 (InterPro/Pfam 자동 조회 또는 수동 입력). **Pareto 다양성** 으로 MODIFY 방식의 위치 분산 최대화. **σ-Adaptive Pool**: EVOLVEpro Round와 Round size 입력 시 누적 데이터 기반으로 후보 풀 범위와 entropy 가중치 자동 보정 (K = 0.50→0.25, entropy = 0.30→0.15, Round 1→5+)
- **배치 변이 파싱**: `Q232A` 형식의 변이 목록 → 코돈 위치 자동 계산 + WT 코돈 검증
- **코돈 전략 선택**: Min. changes (WT 대비 최소 염기 변이) 또는 Optimal (E. coli 최적 코돈)
- **Overlap upstream 설계**: overlap 영역이 mutation codon 바로 앞(upstream)에 위치 (EVOLVEpro 방식)
- **Polymerase 프로파일**: 7종 내장 (Benchling, Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL). 각 프로파일은 제조사 매뉴얼 기준 Tm 방법·염 농도·DNA 농도·GC 범위 보정. Custom Polymerase 다이얼로그로 사용자 정의 프로파일을 만들면 `~/.kuma/kuro/custom_polymerases.json`에 영구 저장됨
- **Tm 계산**: SantaLucia 1998 nearest-neighbor 모델. 염/DNA/divalent 농도는 선택한 polymerase 프로파일에 따라 달라짐. 기본 Tm 타겟 Fwd 62°C, Rev 58°C, Overlap 42°C
- **점진적 Tm tolerance**: Fwd/Rev 각각 ±0.5°C부터 시작, ±0.5씩 독립 확장 (최대 ±3.0°C)
- **GC% 범위**: 기본 40-60%. 범위 밖 프라이머에 패널티 부여
- **프라이머 길이 제한**: Fwd/Rev min/max 길이 제약 (선택적)
- **Hairpin / Homodimer 검증**: primer3 calc_hairpin/calc_homodimer. Tm, dG(kcal/mol) 표시
- **AlphaFold 3D 거리**: Pareto 다양성이 1차원 위치 거리가 아닌 AlphaFold DB 예측 구조의 실제 Cα 유클리드 거리 사용. UniProt accession 입력 후 자동 조회, `~/.kuma/kuro/embeddings/{accession}_ca.json`에 캐싱
- **Benchmark framework**: Kuro 선택(Pareto/Domain) vs Random vs Top-N을 fitness landscape에서 비교. 지표: hit rate, mean fitness, position coverage
- **합성 품질 점수**: IDT/Twist 가이드라인 기반 올리고 합성 난이도 평가(0-100). Homopolymer, GC-rich 연속, 디뉴클레오타이드 반복, 극단 GC% 감점
- **Sequence Map**: 접이식 SVG 선형 CDS 맵. 변이 위치, 도메인 영역, 밀도 히스토그램
- **후보 비교 및 교체**: 프라이머 서열 클릭 시 후보 비교 팝오버
- **커스텀 프라이머 평가**: 후보 팝오버에서 직접 서열 입력 → Tm, GC%, hairpin, off-target 즉시 계산
- **실패 돌연변이 재시도**: 실패한 mutation 클릭 → 파라미터 조절 → 재설계
- **Position Rescue**: 설계 실패 시 EVOLVEpro pool에서 같은 위치 대안 variant를 자동 시도(Pool Cascade), 이후 Tm tolerance(±5.0°C)와 GC 범위(±5%)를 완화하여 재시도(Auto-Relax)
- **실패 시 자동 채움**: 활성화 시 일부 mutation 실패해도 추가 후보로 요청 수만큼 자동 채움
- **Off-target 검증**: template sense/antisense에서 비특이적 결합 자동 검출
- **96-well Plate Map**: Fwd/Rev 쌍 연동 플레이트. 96개 초과 시 multi-plate 슬라이드
- **Echo 525 / JANUS export**: 액체 핸들러 매핑 XLSX workbook. Echo는 384-well 소스 레이아웃 + 전송 목록, JANUS는 Fwd/Rev 96-well 래크

### Mame — NGS 스크리닝 판정

Kuro가 만든 `expected_mutations.xlsx`, 참조 FASTA, Oxford Nanopore 바코드 모드 consensus FASTA들을 입력받아 바코드별 돌연변이 판정과 96-well Final Excel을 만든다.

- **Consensus FASTA ingest**: Nanopore basecaller 바코드 모드 출력. 모의 fixture가 `tests/mame/fixtures/`에 포함됨
- **6-class 판정**: 각 바코드를 6가지 결과로 분류 (exact match, partial, off-target, WT retained, no coverage, ambiguous)
- **3-replicate best pick**: 삼중 바코드 중 최고 점수 클론 선택
- **96-well Final Excel**: column-major 96-well 레이아웃에 웰별 판정. Kuro의 plate map 순서와 동기화
- **Single-view 워크벤치**: 입력 파일 패널, 파라미터 패널(mode / CDS end / cutoffs), NB01/NB02/NB03/ALL 필터가 있는 판정 테이블, 색맹 친화 토글이 있는 96-well 맵
- **치환(Substitution) 지원**: Phase 1은 단일 잔기 치환 중심. 결실/삽입은 이후 단계

## 선택 전략 (Kuro, EVOLVEpro / MULTI-evolve 모드)

EVOLVEpro 또는 MULTI-evolve CSV 로드 시 어떤 mutation을 프라이머 설계 대상으로 선정할지 결정. 독립 체크박스로 자유 조합 가능.

| 전략 | 설명 | 사용 시점 |
|------|------|-----------|
| **Top-N by score** | 예측 적합도(y_pred / property_value) 내림차순 상위 N개 선택. N = 최대 프라이머 수 (기본 95). | 기본 랭킹. 예측 적합도만 기준일 때. |
| **Position diversity** | 아미노산 위치당 최대 mutation 수 제한 (기본 1). 동일 위치 두 후보 점수 차이 2% 이내 시 Grantham 1974 거리가 낮은 보수적 치환 우선. 다른 전략 적용 전 사전 필터. | 특정 위치에 mutation이 과도 집중되는 것을 방지. |
| **Domain diversity** | 단백질 구조 도메인별 할당량 배분 (비례 또는 균등). 도메인 정보는 UniProt accession으로 InterPro/Pfam 자동 조회 또는 수동 입력. | 한 도메인이 y_pred 상위를 독점할 때 전 도메인 탐색. |
| **Pareto diversity** | Greedy maximin 위치 선택. 이미 선택된 mutation과 가장 먼 위치를 반복 선택하여 공간적 분산 극대화. | 좁은 영역에 mutation이 밀집되는 것을 방지. MODIFY 접근법(Ding et al., *Nature Communications*, 2024). |
| **Entropy-guided** (β) | 위치별 y_pred 분포의 Shannon entropy(가중치 0.3)를 Pareto 점수에 혼합. | 적합도 경관에 여러 봉우리가 있을 때 국소 최적 탈출. Pareto 활성화 필요. |

**참고 문헌**
- Ding D, Shaw AY, Sinai S, et al. Protein design using structure-predicted residue preferences and sequence-predicted fitness. *Nature Communications*, 15:6729 (2024). PMID:39080249 — MODIFY: Pareto fitness-diversity 공동 최적화

## 프로젝트 워크플로

첫 실행 시 **프로젝트 루트** 폴더를 묻는다(기본 `~/Documents/kuma`). 이후 모든 프로젝트는 루트 하위에 폴더로 생성된다:

```
<projects_root>/
└── Sample_42/
    ├── kuma.project.json          # 프로젝트 메타 (schema v1)
    ├── design/
    │   ├── workspace.kuro.json    # Kuro workspace (기존 .kuro.json 포맷 그대로)
    │   └── expected_mutations.xlsx # 숨김 __kuma_meta__ 시트 포함
    └── analysis/
        ├── consensus/             # Nanopore consensus FASTA 드롭
        └── verdict.xlsx           # Mame 출력
```

`stage` 필드(draft / design_complete / analyzing / done)는 파일 존재 여부로 자동 계산된다. 기존 Kuro workspace(`.kuro.json`)를 단일 파일로 여는 Scratch 모드도 계속 지원.

## 설치

[Releases](https://github.com/gyuminlee-repo/kuma/releases)에서 최신 인스톨러 다운로드.

- **Windows**: `kuma_x.x.x_x64-setup.exe` (NSIS)
- **macOS**: `kuma_x.x.x_x64.dmg`
- **Linux**: `.deb` + `.AppImage`

## 사용법

**Kuro 탭**
1. **Help → Load Sample Data** 메뉴로 예제 자동 로드. 또는:
2. 시퀀스 파일 로드 (GenBank `.gb` / SnapGene `.dna`)
3. Target Gene 드롭다운에서 타겟 CDS 확인(자동 선택)
4. 변이 입력 (텍스트 / EVOLVEpro CSV / MULTI-evolve CSV)
5. 코돈 전략 선택 (Min. changes / Optimal)
6. *(선택)* Advanced Options에서 Tm, GC%, 길이 조정
7. **Design Primers** 클릭
8. File → Export Excel (현재 프로젝트의 `design/expected_mutations.xlsx`에 `__kuma_meta__` 포함하여 저장)

**Mame 탭** (실험·시퀀싱 후)
1. **Help → Load Sample Data** 메뉴로 예제 자동 로드. 또는:
2. Nanopore consensus FASTA를 입력 패널에 드롭
3. 참조 FASTA + `expected_mutations.xlsx` (활성 프로젝트가 가지고 있으면 자동 제안)
4. CDS end / mode / cutoffs 설정
5. **Run** → 판정 테이블 + 96-well plate map
6. **Export** → final xlsx

다른 프로젝트가 활성화된 상태에서 Kuro-export xlsx를 Mame 탭에 드롭하면 `__kuma_meta__ → project_id` 매칭으로 "출처 프로젝트로 로드하시겠어요?" 다이얼로그가 뜬다.

## 아키텍처

Tauri v2 + React 19 shell과 두 개의 Python sidecar (kuro-sidecar, mame-sidecar). 탭 첫 활성화 시 lazy spawn. Rust가 프로젝트 CRUD, config, sidecar 생명주기를 소유. 두 sidecar 모두 `kuma_core.shared` 공통 유틸(config 경로, 로깅, JSON-RPC 에러 포맷) 공유.

```
+-------------------------+
| Tauri shell (React)     |
| ├─ Home / Onboarding    |
| └─ MainShell [Kuro|Mame]|
+-------------------------+
       ↓ sidecar_rpc(kind, method, params)
+----------------+   +----------------+
| kuro-sidecar   |   | mame-sidecar   |
| (PyInstaller)  |   | (PyInstaller)  |
+----------------+   +----------------+
```

## 라이선스

[GPL v2](LICENSE)
