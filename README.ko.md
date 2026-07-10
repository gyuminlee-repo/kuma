# kuma — 프라이머 설계(Kuro) + NGS 검증(Mame)

**한국어** | [English](README.md)

`kuma`는 두 서브툴을 하나의 Tauri 데스크톱 앱으로 묶는다:

- **Kuro** — *Kernel for Upstream Recombination Oligodesign.* Gibson Assembly 기반 SDM 프라이머 일괄 설계.
- **Mame** — *Mutagenesis Assessment & Microplate Export.* Oxford Nanopore NGS 판정. 어떤 클론이 의도한 돌연변이를 가졌는지 검증.

Kuro 탭에서 프라이머를 설계하고 실험·시퀀싱 후 Mame 탭으로 넘어가 의도한 돌연변이가 제대로 들어갔는지 판정한다.

![kuma overview](docs/kuro_overview.png)

프로젝트 폴더로 Kuro 설계 결과와 Mame 검증 결과를 연결해, 올리고 주문부터 시퀀싱 판독까지 수 주의 시간차가 있어도 작업이 이어진다. Kuro가 내보내는 xlsx에 숨김 시트 `__kuma_meta__`를 삽입해, 나중에 Mame에서 파일을 드롭만 해도 출처 프로젝트를 자동 인식한다.

## 목차

- [탭 구성: Kuro & Mame](#탭-구성)
- [선택 전략](#선택-전략-kuro-evolvepro-모드)
- [프로젝트 워크플로](#프로젝트-워크플로)
- [설치](#설치)
- [사용법](#사용법)
- [활성 데이터 통합](#활성-데이터-통합-v027)
- [아키텍처](#아키텍처)

---

## 탭 구성

### Kuro — SDM 프라이머 설계

변이 목록(텍스트 / EVOLVEpro CSV)과 템플릿 시퀀스(GenBank / SnapGene)를 입력하면 overlap-extension 방식의 SDM 프라이머 쌍을 자동 설계한다.

**Highlights**

- **EVOLVEpro 기반 선정** — Top-N + 위치 / 도메인 / Pareto / entropy / structural 다양성, σ-Adaptive 후보 풀
- **보정된 화학 조건** — polymerase 8종(+커스텀), SantaLucia 1998 Tm, GC / 길이 / tolerance 제어
- **내장 QC** — primer3 hairpin/homodimer, off-target 스캔, 올리고 합성 품질 점수, AlphaFold 3D 거리
- **후보 3D 구조 분석** — Output 단계 3Dmol 뷰어로 후보를 AlphaFold/PDB 구조 위에 표시. active/binding-site 강조, 무작위 null 대비 공간 분산, 클릭형 color legend, surface, PNG 내보내기(선정 필터가 아니라 해석·QC 보조)
- **모드별 실패 복구** — multi-stage Position Rescue + 원클릭 변이별 재시도
- **플레이트 출력** — 정렬 가능한 결과 표, 96-well plate map, Echo 525 / JANUS 내보내기

<details>
<summary><b>전체 Kuro 기능 목록</b></summary>

#### 설계 방식

- **Overlap-extension SDM**: overlap 을 mutation codon upstream 에 배치하는 forward/reverse 프라이머. overlap 모드 2종, *Partial overlap (Gibson)*(기본, forward·reverse 독립)와 *Full overlap (Q5 SDM)*(reverse = forward 의 reverse-complement). annealing Tm 은 SantaLucia 1998(SnapGene) 모델 사용
- **Overlap upstream 설계**: overlap 영역이 mutation codon 바로 앞(upstream)에 위치 (EVOLVEpro 방식)

#### 변이 입력 & 후보 선정

- **EVOLVEpro CSV 입력**: EVOLVEpro(`variant`, `y_pred`) 출력 CSV 로드. 점수 내림차순 정렬 후 설정 개수만큼 자동 선정. **위치 다양성** 필터로 아미노산 위치당 최대 N개 제한 가능 (동일 위치 후보 점수 차이 2% 이내 시 Grantham 1974 거리가 낮은 보수적 치환 우선). **도메인 다양성** 필터는 불러온 참조 단백질 서열을 InterProScan으로 직접 분석하거나 수동 입력한 참조 좌표 도메인에 따라 선택을 분산하며, AlphaFold 색칠용 UniProt accession 도메인은 별도로 유지한다. **Pareto 다양성** 으로 MODIFY 방식의 위치 분산 최대화. **structural 다양성** 으로 전체 후보 풀을 3D Cα-centroid 공간에서 greedy farthest-point 선택 — 이전 라운드에서 이미 테스트한 변이 집합을 anchor로 삼아 멀어지도록 고르며, 예측 적합도 쪽으로 κ 블렌드 가능. 초기·저데이터 라운드의 epistatic 조합 타깃에서만 Top-N을 이김(조건부; 그 외엔 무익~해로움, `benchmark/REPORT.md` §6.7–6.12). **σ-Adaptive Pool**: EVOLVEpro Round와 Round size 입력 시 누적 데이터 기반으로 후보 풀 범위와 entropy 가중치 자동 보정 (K = 0.50→0.25, entropy = 0.30→0.15, Round 1→5+)
- **배치 변이 파싱**: `Q232A` 형식의 변이 목록 → 코돈 위치 자동 계산 + WT 코돈 검증
- **AlphaFold 3D 거리**: Pareto·structural 다양성이 1차원 위치 거리가 아닌 AlphaFold DB 예측 구조의 실제 Cα 유클리드 거리 사용. UniProt accession 입력 후 자동 조회, `~/.kuma/kuro/embeddings/{accession}_ca.json`에 캐싱

> 다양성 필터(위치 / 도메인 / Pareto / entropy / structural)의 상세는 아래 [선택 전략](#선택-전략-kuro-evolvepro-모드) 표를 참고.

#### 코돈 & 열역학 파라미터

- **코돈 전략 선택**: Min. changes (WT 대비 최소 염기 변이) 또는 Optimal (E. coli 최적 코돈)
- **Polymerase 프로파일**: 8종 내장 (Benchling, Taq, Phusion, Q5, Q5 SDM, KOD, DreamTaq, TAKARA_GXL). 각 프로파일은 제조사 매뉴얼 기준 Tm 방법·염 농도·DNA 농도·GC 범위 보정. Custom Polymerase 다이얼로그로 사용자 정의 프로파일을 만들면 `~/.kuma/kuro/custom_polymerases.json`에 영구 저장됨
- **Tm 계산**: SantaLucia 1998 nearest-neighbor 모델. 염/DNA/divalent 농도는 선택한 polymerase 프로파일에 따라 달라짐. 기본 Tm 타겟 Fwd 62°C, Rev 58°C, Overlap 42°C
- **점진적 Tm tolerance**: Fwd/Rev 각각 ±0.5°C부터 시작, ±0.5씩 독립 확장 (최대 ±3.0°C)
- **Tm tolerance 사용자 설정**: Advanced Options 에서 ±°C 직접 지정 (범위 0.5–10.0, step 0.5, 기본 3.0). Cascade rescue 단계는 이 base 값에 delta 추가. 권장 2–5°C
- **GC% 범위**: 기본 40-60%. 범위 밖 프라이머에 패널티 부여
- **프라이머 길이 제한**: Fwd/Rev min/max 길이 제약 (선택적)

#### 품질 & 특이성 검증

- **Hairpin / Homodimer 검증**: primer3 calc_hairpin/calc_homodimer. Tm, dG(kcal/mol) 표시
- **합성 품질 점수**: IDT/Twist 가이드라인 기반 올리고 합성 난이도 평가(0-100). Homopolymer, GC-rich 연속, 디뉴클레오타이드 반복, 극단 GC% 감점
- **Off-target 검증**: template sense/antisense에서 비특이적 결합 자동 검출

#### 실패 복구

- **Position Rescue**: 모드별 multi-stage cascade.
  - **Top-N + Fill-on-failure ON** → 위치 고정 4-stage 조건완화 (length → +GC → +mild Tm → strong). 배지 `🎯¹` length / `🎯²` +GC / `🎯³` +mild Tm / `🎯⁴` strong
  - **Pipeline + Fill-on-failure ON** → 6-stage: ① 동일 위치 대안 variant (`↻¹`) → ② 다른 위치 substitution (`↻²`) → ③–⑥ 동일 4-stage 완화
  - **Fill-on-failure OFF** → 위치 고정 2-stage 자동재시도 (mild → strong). 성공 primer 들로부터 도출한 파라미터 사용
  - 백엔드의 legacy pool cascade (`↻ cascade`) 와 auto-relax (`⚡ relaxed`) 는 frontend cascade 이전에 자동 적용
  - Stage 카운터 Design Report 에 표시
- **실패 시 자동 채움**: 기본 ON. 켜져 있으면 selection mode 에 따라 위 cascade 발동. OFF 면 2-stage 자동재시도만 실행
- **실패 돌연변이 재시도**: 실패한 mutation 클릭 → 파라미터 조절 → 재설계. popover 의 **Use suggestion** 버튼은 같은 run 에서 성공한 primer 들의 median Tm, GC/길이 관측 범위, tol ±5°C 를 한 번에 채워줌

#### 검토 · 시각화 · 내보내기

- **Sequence Map**: 접이식 SVG 선형 CDS 맵. 변이 위치, 도메인 영역, 밀도 히스토그램
- **후보 3D 구조 분석**: Output 단계 접이식 패널에 3Dmol 뷰어 내장(열 때만 로드). 후보 위치를 fetch한 AlphaFold/PDB 구조(또는 업로드한 PDB/CIF) 위에 매핑하고, UniProt active-site·binding-site 잔기를 강조하며, 공간 분산(무작위 동일 개수 null 대비 평균 pairwise Cα 거리, 백분위 `P1`/`P99`)을 보고. Color legend가 각 색 의미를 설명하고 항목 클릭으로 3D 레이어를 토글하며, surface 렌더·PNG 내보내기 지원. dispersion·pLDDT·site 오버레이는 선정 필터가 아니라 해석·QC 보조 — 무엇을 설계할지는 EVOLVEpro `y_pred` 랭킹이 결정
- **후보 비교 및 교체**: 프라이머 서열 클릭 시 후보 비교 팝오버
- **커스텀 프라이머 평가**: 후보 팝오버에서 직접 서열 입력 → Tm, GC%, hairpin, off-target 즉시 계산
- **96-well Plate Map**: Fwd/Rev 쌍 연동 플레이트. 96개 초과 시 multi-plate 슬라이드
- **Echo 525 / JANUS export**: 액체 핸들러 매핑 XLSX workbook. Echo는 384-well 소스 레이아웃 + 전송 목록, JANUS는 Fwd/Rev 96-well 래크
- **Benchmark framework**: Kuro 선택(Pareto/Domain) vs Random vs Top-N을 fitness landscape에서 비교. 지표: hit rate, mean fitness, position coverage

</details>

### Mame — NGS 스크리닝 판정

Kuro가 만든 `expected_mutations.xlsx`, 참조 FASTA, MAME가 생성한 barcode-mode consensus FASTA들을 입력받아 바코드별 돌연변이 판정과 96-well Final Excel을 만든다.

**Highlights**

- **MAME consensus 입력** — barcode-mode consensus 또는 raw FASTQ(Phred-aware demux→consensus)
- **8-class 판정**, PASS / WRONG_AA / AMBIGUOUS / MIXED / FRAMESHIFT / MANY / LOWDEPTH / NO_CALL
- **설명가능 QC** — read depth, N fraction, low-depth 위치, low-quality 제외, MAPQ/span drop
- **96-well 출력** — Kuro plate map 순서와 동기화된 column-major Final Excel, single-view 워크벤치

<details>
<summary><b>전체 Mame 기능 목록</b></summary>

#### 입력 & consensus

- **MAME consensus FASTA ingest**: MAME 자체 demux→consensus pipeline의 barcode-mode 출력. Consensus header의 `depth=N`, low-depth 위치, N fraction, mixed-allele metric이 `LOWDEPTH`/`MIXED` 판정 근거가 된다.
- **Phred-aware consensus**: raw FASTQ에서 시작하면 read ID와 quality string을 내부 demux 단계에서 보존해 저품질 base call이 consensus vote를 이기지 못하게 한다.

#### 판정 & QC 근거

- **8-class 판정**: 각 바코드를 8가지로 분류, `PASS`(관찰 변이가 설계와 정확 일치), `WRONG_AA`(기대 위치 불일치·기대 변이 누락·예상밖 추가 변이), `AMBIGUOUS`(기대 변이는 모두 일치하나 인접 window 추가 변이 또는 indel 이벤트 신호), `MIXED`(well 내 유의한 2nd allele 혼합), `FRAMESHIFT`(frame window 내 연속 nucleotide indel), `MANY`(cutoff·설계를 모두 초과한 과다 변이), `LOWDEPTH`(read depth 미달), `NO_CALL`(consensus N 과다)
- **Mixed-well guard**: minor-allele metric이 있는 consensus는 within-well mixture 근거가 충분할 때 다수결 PASS 대신 `MIXED`로 표시한다.
- **Explainable QC evidence**: 판정 테이블과 Excel export에 read depth, N fraction, low-depth 위치, low-quality base 제외 수, MAPQ/span drop counter를 표시한다.
- **3-replicate best pick**: 삼중 바코드 중 최고 점수 클론 선택
- **치환(Substitution) 지원**: Phase 1은 단일 잔기 치환 중심. 결실/삽입은 이후 단계

#### 출력 & 워크벤치

- **96-well Final Excel**: column-major 96-well 레이아웃에 웰별 판정. Kuro의 plate map 순서와 동기화
- **Single-view 워크벤치**: 입력 파일 패널, 파라미터 패널(mode / CDS end / cutoffs), NB01/NB02/NB03/ALL 필터가 있는 판정 테이블, 색맹 친화 토글이 있는 96-well 맵

</details>

## 선택 전략 (Kuro, EVOLVEpro 모드)

EVOLVEpro CSV 로드 시 어떤 mutation을 프라이머 설계 대상으로 선정할지 결정. 독립 체크박스로 자유 조합 가능.

| 전략 | 설명 | 사용 시점 |
|------|------|-----------|
| **Top-N by score** | 예측 적합도(y_pred / property_value) 내림차순 상위 N개 선택. N = 최대 프라이머 수 (기본 95). | 기본 랭킹. 예측 적합도만 기준일 때. |
| **Position diversity** | 아미노산 위치당 최대 mutation 수 제한 (기본 1). 동일 위치 두 후보 점수 차이 2% 이내 시 Grantham 1974 거리가 낮은 보수적 치환 우선. 다른 전략 적용 전 사전 필터. | 특정 위치에 mutation이 과도 집중되는 것을 방지. |
| **Domain diversity** | 불러온 참조 단백질 서열을 InterProScan으로 직접 분석하거나 참조 좌표로 수동 입력한 도메인에 따라 할당량을 비례 또는 균등 배분. AlphaFold 구조 표시용 UniProt accession 도메인은 별도로 유지. | 참조 좌표와 accession 잔기 번호를 섞지 않고 기능 영역 전반을 탐색. |
| **Pareto diversity** | Greedy maximin 위치 선택. 이미 선택된 mutation과 가장 먼 위치를 반복 선택하여 공간적 분산 극대화. | 좁은 영역에 mutation이 밀집되는 것을 방지. MODIFY 접근법(Ding et al., *Nature Communications*, 2024). |
| **Entropy-guided** (β) | 위치별 y_pred 분포의 Shannon entropy(가중치 0.3)를 Pareto 점수에 혼합. | 적합도 경관에 여러 봉우리가 있을 때 국소 최적 탈출. Pareto 활성화 필요. |
| **Structural diversity** | 전체 후보 풀을 3D Cα-centroid 공간(AlphaFold)에서 greedy farthest-point(maximin) 선택. 이전 라운드에서 이미 테스트한 변이 누적 집합을 anchor로 삼고, 예측 적합도 쪽으로 κ 블렌드 가능(κ=0 순수 다양성 → κ=1 순수 Top-N). 조합 변이는 모든 치환 위치의 centroid 사용, 구조 없으면 서열 위치 거리로 폴백. | 다라운드 epistatic 조합 캠페인의 초기·저데이터 라운드. **조건부**: 진짜 epistatic·분산형 경관에선 Top-N을 이기지만 그 외엔 무익~해로우며 라벨이 ~1 플레이트 쌓이면 사라짐(`benchmark/REPORT.md` §6.7–6.12). |

**참고 문헌**
- Ding D, Shaw AY, Sinai S, et al. Protein design using structure-predicted residue preferences and sequence-predicted fitness. *Nature Communications*, 15:6729 (2024). PMID:39080249 — MODIFY: Pareto fitness-diversity 공동 최적화

> **벤치마크 caveat (`benchmark/REPORT.md` §6).** in-silico active-learning 벤치에서 **structural 다양성**만 Top-N을 이겼고, 그것도 조건부(초기·저데이터, 진짜 epistatic)였다. **도메인**·**Pareto** 다양성은 Top-N을 못 이겼고, 도메인 다양성은 단일-활성부위 단백질엔 해로울 수 있다(기능 영역 밖으로 픽 낭비). 모든 다양성 필터는 Top-N의 범용 개선이 아니라 초기-라운드 헤지로 취급하라.

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
        ├── consensus/             # MAME-generated consensus FASTAs
        └── verdict.xlsx           # Mame 출력
```

`stage` 필드(draft / design_complete / analyzing / done)는 파일 존재 여부로 자동 계산된다. 기존 Kuro workspace(`.kuro.json`)를 단일 파일로 여는 Scratch 모드도 계속 지원.

## 설치

[Releases](https://github.com/gyuminlee-repo/kuma/releases)에서 최신 인스톨러 다운로드.

- **Windows**: `kuma_x.x.x_x64-setup.exe` (NSIS)
- **macOS**: `kuma_x.x.x_aarch64.dmg`
- **Linux**: `.deb` + `.AppImage`

Kuma는 시작할 때 GitHub의 최신 공개 릴리스를 확인하고, 설치된 버전보다 새 버전일 때만 업데이트를 권장한다. **도움말 → 업데이트 확인**에서 수동으로 다시 확인할 수 있으며, 확인 실패가 앱 시작을 막지는 않는다.

### 개발자 — Windows에서는 `pnpm install` 대신 `pnpm setup`

Windows에서 `pnpm install`은 Defender나 IDE 파일 워처가 `node_modules`를 잠가 첫 시도에 `EACCES`/`EBUSY`로 실패할 수 있다. 대신 래퍼 스크립트를 쓴다:

```powershell
pnpm setup
```

`scripts/safe-install.mjs`는 Windows에서 `package-import-method=copy`를 임시 적용(hardlink 락 우회)하고, retryable 에러 발생 시 최대 3회 자동 재시도한다. macOS/Linux에서는 일반 `pnpm install`과 동일한 동작 + 재시도만.

3회 재시도 후에도 실패하면 원인별 해결 가이드를 출력한다(IDE 종료, Defender 예외, `node_modules` 수동 정리 등).

### macOS — 첫 실행 시 Gatekeeper 경고

kuma는 유료 Apple Developer ID 없이 ad-hoc 서명만 적용된다. 첫 실행 시 "확인되지 않은 개발자" 경고가 표시될 수 있다. 만약 **"손상되었기 때문에 열 수 없습니다"** 메시지가 뜨면 다운로드 시 quarantine bit가 붙은 것이므로 한 번만 풀어주면 된다:

```bash
xattr -cr /Applications/kuma.app
```

이어서 Gatekeeper는 다음 중 한 가지 방법으로 우회한다:

1. Finder에서 `kuma.app` 우클릭(Control+클릭) → **열기** → **열기**
2. 시스템 설정 → 개인정보 보호 및 보안 → kuma 항목 → **그래도 열기**

이후 실행부터는 경고 없이 열린다.

## 사용법

새로 만든 프로젝트에서는 건너뛸 수 있는 spotlight 투어가 실행된다. 짧은 프로젝트 개요와 Kuro 안내가 먼저 나오며, Mame은 처음 진입할 때 별도 투어를 제공한다. 기존 프로젝트에는 자동으로 표시되지 않는다. 현재 탭의 투어는 **도움말 → 가이드 투어 보기**에서 다시 실행할 수 있다.

**Kuro 탭**
1. **Help → Load Sample Data** 메뉴로 예제 자동 로드. 또는:
2. 시퀀스 파일 로드 (GenBank `.gb` / SnapGene `.dna`)
3. Target Gene 드롭다운에서 타겟 CDS 확인(자동 선택)
4. 변이 입력 (텍스트 / EVOLVEpro CSV)
5. 코돈 전략 선택 (Min. changes / Optimal)
6. *(선택)* Advanced Options에서 Tm, GC%, 길이 조정
7. **Design Primers** 클릭
8. File → Export Excel (현재 프로젝트의 `design/expected_mutations.xlsx`에 `__kuma_meta__` 포함하여 저장)

**Mame 탭** (실험·시퀀싱 후)
1. **Help → Load Sample Data** 메뉴로 예제 자동 로드. 또는:
2. MAME-generated consensus FASTA를 입력 패널에 드롭
3. 참조 FASTA + `expected_mutations.xlsx` (활성 프로젝트가 가지고 있으면 자동 제안)
4. CDS end / mode / cutoffs 설정
5. **Run** → 판정 테이블 + 96-well plate map
6. **Export** → final xlsx

다른 프로젝트가 활성화된 상태에서 Kuro-export xlsx를 Mame 탭에 드롭하면 `__kuma_meta__ → project_id` 매칭으로 "출처 프로젝트로 로드하시겠어요?" 다이얼로그가 뜬다.

## 활성 데이터 통합 (v0.2.7)

KUMA가 ALE 전체 사이클을 연결한다: Kuro가 라운드 N 변이의 프라이머를 설계하고, 실험실에서 변이를 도입하고, NGS 지노타이핑으로 성공한 클론을 확인한 뒤, 활성 측정 데이터를 MAME에서 처리해 단일 "Handoff" 클릭으로 Kuro 라운드 N+1에 피드백한다.

### 사용 흐름

```
1. KURO 설계      →  라운드 N 변이 프라이머 목록
2. 실험실          →  SDM + 발현
3. MAME NGS       →  클론별 지노타입 판정 (8-class)
4. 활성 측정       →  플레이트 리더 / 형광 측정
5. MAME 활성      →  long format CSV 로드; fold_change / log2_fc 계산
6. EVOLVEpro export →  variant + y_pred CSV (다음 라운드 입력)
7. Round Handoff  →  1-click: 라운드 N+1 생성 + EVOLVEpro CSV를 Kuro에 로드
8. 반복            →  Kuro가 업데이트된 점수로 라운드 N+1 설계
```

<details>
<summary><b>활성 입력 형식 · Round 엔티티 · v0.3 xlsx 파이프라인</b></summary>

### Long Format CSV 입력 형식

활성 데이터 로더는 측정값 1개당 행 1줄의 **long format** CSV(또는 Excel)를 기대한다:

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `plate_id` | string | 플레이트 식별자. 예: `P01` |
| `well_id` | string | A01–H12 형식의 웰 주소 |
| `value` | float | 원시 측정값 |
| `replicate_idx` | int | 반복 인덱스 (1-based). 동일 웰 × 동일 index = 1회 측정 |

WT 웰은 `plate_meta.json`에 선언한다:

```json
{
  "plates": [
    { "plate_id": "P01", "wt_wells": ["A01", "A12", "H01", "H12"] }
  ]
}
```

Fold change와 log2_fc는 플레이트별 WT 평균을 기준으로 계산된다. log2_fc 값이 EVOLVEpro `y_pred`에 직접 매핑된다.

### Round 엔티티

각 ALE 라운드는 워크스페이스(schema v0.3)에서 `Round` 엔티티로 추적된다. 라운드는 다음 정보를 가진다:
- `round_n`: 순차 라운드 번호 (1-based)
- `status`: `design` → `sequencing` → `activity` → `exported`
- `plate_meta`: 해당 라운드의 WT 웰 배치
- 해당 라운드의 Kuro workspace와 MAME NGS 결과 경로

**schema v0.2 이하 워크스페이스 파일은 자동 마이그레이션 없음.** v0.2.6 이하에서 업그레이드 전 설계 데이터를 내보낼 것.

### v0.3 xlsx 파이프라인 (v0.2.8+)

실험실 산출물에 직접 대응하는 xlsx reader: `mutants-well position.xlsx`, Agilent GC-FID raw export(standard / rep-batch), EVOLVEpro xlsx. `kuma_core/mame/activity/evolvepro_xlsx.py:detect_format`이 포맷 자동 분기.

`mame.activity.merge_for_evolvepro` (v0.2.9.0)가 EVOLVEpro 내보내기용 병합을 대체: 활성-지노타입 join + `merge_replicates_priority` (authoritative 우선·mismatch 플래그) + 라벨 교체 가드. 응답에 `replicate_stats`·`export_blocked` 노출. 5/12 데모는 기존 `activity.merge`를 그대로 사용하며 v0.3 버튼 "EVOLVEpro용 병합 (v0.3)"이 패널에 병행 배치.

기본 reference 는 `ref_seq` 미전달 시 `fixtures/egfp.fa` 를 BioPython translate 로 자동 로드합니다 (OQ-④ 결정, v0.9.9.9). 레거시 IspS 라운드용 `fixtures/ispS.fa` (Populus alba ispS CDS, AB198180.1) 도 보존됩니다. UI 추가 배선 불필요.

</details>

---

## 아키텍처

Tauri v2 + React 19 shell과 두 개의 Python sidecar (kuro-sidecar, mame-sidecar). 탭 첫 활성화 시 lazy spawn. Rust가 프로젝트 CRUD, config, sidecar 생명주기를 소유. 두 sidecar 모두 `kuma_core.shared` 공통 유틸 공유 — config 경로, 로깅, JSON-RPC 에러 포맷, `kuma_core.shared.sidecar` 헬퍼(`JsonRpcWriter`, bounded crash-log append, private config 디렉토리, path validation).

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

## 공통 프론트엔드 헌장 (Common Frontend Standards)

Kuro·Mame 는 `docs/standards/common-frontend-standards.md` (v1.1 stable) 의 22 카테고리를 따른다 — 복구, 관측성, 입력 검증, 에러 UX, 결과 영속성, 설정, UI 안전, 접근성, 버전·업데이트, 텔레메트리, 빌드, 재현성(`run.json`), 장시간 작업(잡 큐 + OS 알림 + sleep inhibit), 데이터 무결성(입력/출력 SHA-256, sidecar binary hash, schema dry-run 마이그레이션), 온보딩, 로컬 진단, 크로스플랫폼, 부분 실패, 성능 가드레일, 인용·라이선스, 멀티 워크스페이스, 안전한 종료. PrimerBench 도 Phase A-E 로 동일 헌장을 적용한다.

## 라이선스

[GPL v2](LICENSE)
