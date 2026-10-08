# Phase 1 Help-Icon Targets (40)

> **Status: completed** (Phase 1 구현 머지 PR #13, v0.9.9.1)

**작성**: 2026-05-18 (Phase P2-T0, Task 0 인벤토리)

## 인벤토리 도출 과정

`rg -n "InlineHelp|HelpTip" src/components/` 결과로 기존 적용 위치 식별 후 미적용 Label/field 카탈로그.

**plan 예시 fields 중 이미 적용된 항목 (재적용 제외)**:
- Mame: `targetAmpliconLength`, `lengthTolerance`, `trimAdapters`, `universalRevPrimer`, `normalizeHeaders`, `minFilteredDepth`, `legacyKb`, `minQscore`, `minBarcodeScore` (NumericField helpText 경유), `cdsStart`, `cdsEnd`, `manyCutoff`. `src/components/mame/panels/ParameterPanel.tsx`에 이미 9개 InlineHelp 적용 완료
- Kuro: `strategy`, `polymerase`, `codonStrategy` (codonLabel), `mutations` (maxPrimers), `gc` (range). `src/components/panels/ParameterPanel.tsx`에 이미 5개 InlineHelp + 2개 HelpTip(tmTol, primerLen) 적용
- DiversitySections: `linker`, `round`, `positionCap`, `domainStrategy`, `distance`, `poolK`, `entropyGuided`, `randomSeed`(benchmark). `HelpTip` 10개 이미 적용

**범위 확장 정당화**: kuro ParameterPanel.tsx 단일 파일에는 미적용 Label이 약 11개에 불과. 25개를 채우려면 InputPanel 서브트리(DiversitySections, MutationInput, SequenceInput) 및 BarcodeSetupPanel(mame 측 추가)까지 확장. 본 인벤토리는 사용자 혼란 가능성이 큰 numeric threshold, mode toggle을 우선 선택.

**컴포넌트 주의**: DiversitySections는 `HelpTip` 컴포넌트(다른 구현체)를 사용. 본 Phase에서는 신규 위치에 `InlineHelp` 적용. 기존 HelpTip 옆에 InlineHelp 중복 금지.

---

## Mame Parameters (12)

| # | File | Line | Field | i18n Key | en | ko |
|---|---|---|---|---|---|---|
| 1 | src/components/mame/panels/ParameterPanel.tsx | 400 | mode | mame.parameters.modeHelp | Analysis mode: amplicon (linear PCR product) or plasmid (circular). Choose plasmid for whole-vector consensus. | 분석 모드: amplicon(선형 PCR 산물) 또는 plasmid(원형). 전체 벡터 consensus는 plasmid 선택. |
| 2 | src/components/mame/panels/ParameterPanel.tsx | 425 | ingest | mame.parameters.ingestHelp | Ingest layout: barcode (per-well demultiplexed) or amplicon (single bulk read set). | Ingest 레이아웃: barcode(well별 분리) 또는 amplicon(단일 read 집합). |
| 3 | src/components/mame/panels/ParameterPanel.tsx | 450 | inputSource | mame.parameters.inputSourceHelp | Input source: consensus (pre-called), sorted_barcode (per-well FASTQ), or raw_run (MinKNOW run folder). | 입력 소스: consensus(이미 계산됨), sorted_barcode(well별 FASTQ), raw_run(MinKNOW run 폴더). |
| 4 | src/components/mame/panels/BarcodeSetupPanel.tsx | 388 | cdsCandidate | mame.barcodeSetup.cdsCandidateHelp | CDS candidate auto-detected from the FASTA. Coordinates apply on selection. | FASTA에서 자동 감지된 CDS 후보. 선택 시 좌표가 자동 입력됨. |
| 5 | src/components/mame/panels/BarcodeSetupPanel.tsx | 480 | geneName | mame.barcodeSetup.geneNameHelp | Short gene identifier used in output filenames and labels (e.g. ispS). | 출력 파일명/라벨에 사용되는 짧은 gene 식별자(예: ispS). |
| 6 | src/components/mame/panels/BarcodeSetupPanel.tsx | 492 | polymerase | mame.barcodeSetup.polymeraseHelp | Polymerase profile used to set default Tm/binding constraints. Q5 recommended for high-fidelity PCR. | 기본 Tm/binding 제약을 정하는 polymerase profile. 고정밀 PCR은 Q5 권장. |
| 7 | src/components/mame/panels/BarcodeSetupPanel.tsx | 440 | geneStart | mame.barcodeSetup.geneStartHelp | CDS start coordinate (0-based, inclusive). | CDS 시작 좌표 (0-based, inclusive). |
| 8 | src/components/mame/panels/BarcodeSetupPanel.tsx | 451 | geneEnd | mame.barcodeSetup.geneEndHelp | CDS end coordinate (0-based, exclusive). | CDS 종료 좌표 (0-based, exclusive). |
| 9 | src/components/mame/panels/BarcodeSetupPanel.tsx | 524 | flankMin | mame.barcodeSetup.flankMinHelp | Minimum flank length (nt) around CDS for barcode primer search. Default 100. | barcode primer 탐색용 CDS 양옆 flank 최소 길이(nt). 기본 100. |
| 10 | src/components/mame/panels/BarcodeSetupPanel.tsx | 533 | flankMax | mame.barcodeSetup.flankMaxHelp | Maximum flank length (nt). Larger windows give more primer candidates but slow search. | flank 최대 길이(nt). 클수록 후보는 많아지나 탐색이 느려짐. |
| 11 | src/components/mame/panels/BarcodeSetupPanel.tsx | 553 | bindingMinLen | mame.barcodeSetup.bindingMinLenHelp | Minimum primer binding length (nt). Typical 18-22 for stable PCR priming. | primer binding 최소 길이(nt). 안정적 PCR은 18-22 권장. |
| 12 | src/components/mame/panels/BarcodeSetupPanel.tsx | 562 | bindingMaxLen | mame.barcodeSetup.bindingMaxLenHelp | Maximum primer binding length (nt). Above 35 increases secondary structure risk. | primer binding 최대 길이(nt). 35 초과 시 secondary structure 위험 증가. |

## Kuro Parameters (25)

| # | File | Line | Field | i18n Key | en | ko |
|---|---|---|---|---|---|---|
| 1 | src/components/panels/ParameterPanel.tsx | 254 | tmPrimerLabel | parameterPanel.tmPrimerHelp | Target Tm (°C) for symmetric full-overlap primers. Default 62. | 대칭형 full-overlap primer 목표 Tm(°C). 기본 62. |
| 2 | src/components/panels/ParameterPanel.tsx | 261 | tmFwdLabel | parameterPanel.tmFwdHelp | Target Tm (°C) for forward primer in partial-overlap mode. Lower value increases mismatch tolerance. | partial-overlap 모드에서 forward primer 목표 Tm(°C). 낮을수록 mismatch 허용 증가. |
| 3 | src/components/panels/ParameterPanel.tsx | 266 | tmRevLabel | parameterPanel.tmRevHelp | Target Tm (°C) for reverse primer. Should approximate tmFwd for balanced PCR. | reverse primer 목표 Tm(°C). 균형 잡힌 PCR은 tmFwd와 근접 권장. |
| 4 | src/components/panels/ParameterPanel.tsx | 271 | tmOverlapLabel | parameterPanel.tmOverlapHelp | Target Tm (°C) of the overlap region between two primers. | 두 primer 간 overlap 영역의 목표 Tm(°C). |
| 5 | src/components/panels/ParameterPanel.tsx | 297 | gcRangeLabel | parameterPanel.gcRangeHelp | Accepted GC content range (%) for primer regions. Recommended 40-60. | primer 영역 허용 GC content 범위(%). 권장 40-60. |
| 6 | src/components/panels/ParameterPanel.tsx | 323 | primerLenLimit | parameterPanel.primerLenLimitHelp | Toggle to bound primer length. When off, engine uses Tm-only optimization. | primer 길이 제한 토글. off 시 Tm 단독 최적화로 길이 자유. |
| 7 | src/components/panels/ParameterPanel.tsx | 334 | primerLenFwdLabel | parameterPanel.primerLenFwdHelp | Forward primer length range (nt). Default 17-39 covers most SDM cases. | forward primer 길이 범위(nt). 기본 17-39이 대부분 SDM 케이스 포괄. |
| 8 | src/components/panels/ParameterPanel.tsx | 344 | primerLenRevLabel | parameterPanel.primerLenRevHelp | Reverse primer length range (nt). Default 19-27. | reverse primer 길이 범위(nt). 기본 19-27. |
| 9 | src/components/panels/ParameterPanel.tsx | 368 | autoRescueLabel | parameterPanel.autoRescueHelp | Auto-fill failed mutations with relaxed constraints in a second pass. | 1차 실패 mutation을 완화된 제약으로 2차 시도하여 자동 채움. |
| 10 | src/components/panels/ParameterPanel.tsx | 380 | seedLabel | parameterPanel.seedHelp | Random seed for reproducible primer ranking. Leave empty for auto (time-based). | 재현 가능한 primer 순위용 random seed. 비우면 자동(시간 기반). |
| 11 | src/components/panels/InputPanel/DiversitySections.tsx | 306 | evolveproRoundLabel | diversitySections.evolveproRoundHelp | EVOLVEpro round number for adaptive primer selection. | 적응형 primer 선택용 EVOLVEpro round 번호. |
| 12 | src/components/panels/InputPanel/DiversitySections.tsx | 316 | roundSizeLabel | diversitySections.roundSizeHelp | Number of primers per round (1-960). Multiples of 96 align with plate capacity. | 라운드당 primer 개수(1-960). 96의 배수는 plate 용량과 정합. |
| 13 | src/components/panels/InputPanel/DiversitySections.tsx | 441 | overlapLabel | diversitySections.overlapHelp | Domain overlap policy when adjacent domains share residues. | 인접 domain이 잔기 공유 시 overlap 정책. |
| 14 | src/components/panels/InputPanel/DiversitySections.tsx | 450 | minQuotaLabel | diversitySections.minQuotaHelp | Minimum primer quota per domain (0-20). Ensures each domain represented. | domain별 최소 primer 할당(0-20). 각 domain 대표성 보장. |
| 15 | src/components/panels/InputPanel/DiversitySections.tsx | 477 | poolKLabel | diversitySections.poolKLabelHelp | Pool-K diversity weighting target. Auto value derived from sequence properties. | Pool-K 다양성 가중치 목표. 자동값은 서열 특성에서 유도. |
| 16 | src/components/panels/InputPanel/DiversitySections.tsx | 506 | entropyWeight | diversitySections.entropyWeightHelp | Weight (0-1) for entropy-guided primer selection vs pure diversity. | entropy-guided primer 선택 vs 순수 다양성 가중치(0-1). |
| 17 | src/components/panels/InputPanel/DiversitySections.tsx | 541 | autoRedesignOnLoad | diversitySections.autoRedesignOnLoadHelp | Re-run primer design automatically when a workspace is loaded. | workspace 로드 시 primer design 자동 재실행. |
| 18 | src/components/panels/InputPanel/DiversitySections.tsx | 545 | savePipelineCache | diversitySections.savePipelineCacheHelp | Save intermediate pipeline outputs to disk for faster re-runs. | 재실행 가속을 위해 파이프라인 중간 결과를 디스크에 저장. |
| 19 | src/components/panels/InputPanel/DiversitySections.tsx | 580 | topPercentile | diversitySections.topPercentileHelp | Benchmark top percentile (1-100) cutoff for primer scoring. | primer 채점 benchmark 상위 백분위(1-100) 컷오프. |
| 20 | src/components/panels/InputPanel/DiversitySections.tsx | 593 | randomTrials | diversitySections.randomTrialsHelp | Number of random baseline trials for benchmark (1-1000). Higher value yields more reliable estimate. | benchmark용 random baseline 시행 횟수(1-1000). 클수록 안정. |
| 21 | src/components/panels/InputPanel/DiversitySections.tsx | 605 | randomSeed | diversitySections.benchmarkRandomSeedHelp | Random seed for benchmark reproducibility. Empty value defaults to auto. | benchmark 재현성용 random seed. 비우면 자동. |
| 22 | src/components/panels/InputPanel/SequenceInput.tsx | 51 | sequenceFile | sequenceInput.sequenceFileHelp | Reference sequence file (.fasta/.gb) used as template for primer design. | primer design template으로 사용되는 참조 서열 파일(.fasta/.gb). |
| 23 | src/components/panels/InputPanel/MutationInput.tsx | 61 | mutations | mutationInput.mutationsHelp | Mutations in HGVS or plain format (e.g. A123V, L45*). One per line or comma-separated. | HGVS 또는 단순 형식 mutation(예: A123V, L45*). 줄 단위 또는 콤마 구분. |
| 24 | src/components/panels/InputPanel/DiversitySections.tsx | 143 | linkerLabel | diversitySections.linkerLabelHelp | How to treat known linker regions during primer search. | primer 탐색 중 알려진 linker 영역 처리 방식. |
| 25 | src/components/panels/InputPanel/DiversitySections.tsx | 411 | positionCap | diversitySections.positionCapLabelHelp | Maximum primers per residue position (1-20). Caps over-representation. | 잔기 위치당 최대 primer 수(1-20). 과대 대표 방지. |

## Section Headers (3)

| # | File | Line | Section | i18n Key | en | ko |
|---|---|---|---|---|---|---|
| 1 | src/components/panels/ParameterPanel.tsx | 251 | tmSectionLabel | parameterPanel.tmSectionHelp | Melting temperature targets define how the engine balances primer stability and selectivity. | Tm 목표값은 engine이 primer 안정성과 선택성을 균형 잡는 기준. |
| 2 | src/components/panels/InputPanel/DiversitySections.tsx | 304 | roundSectionLabel | diversitySections.roundSectionHelp | EVOLVEpro round controls iterative primer batches with adaptive selection. | EVOLVEpro round는 적응형 선택을 통한 반복적 primer 배치 제어. |
| 3 | src/components/panels/InputPanel/DiversitySections.tsx | 578 | benchmarkSectionLabel | diversitySections.benchmarkSectionHelp | Benchmark compares designed primers against random baselines to estimate quality lift. | benchmark는 설계된 primer와 random baseline을 비교하여 품질 향상도 추정. |

---

## 작업 후속 에이전트 지침

- **Task 1 (i18n)**: 위 40 키를 `src/locales/en.json`, `src/locales/ko.json`에 추가. 다른 8 언어는 i18n-parity 정책에 따라 분기 (parity strict 시 en 그대로 fallback 복사).
- **Task 2 (mame ParameterPanel)**: row #1-3 (3개) 위치 정확히 Edit. `<Label>` 직후 `<InlineHelp text={t("...Help")} />` 추가.
- **Task 2b (mame BarcodeSetupPanel)**: row #4-12 (9개) 위치 동일 패턴. import 추가 필요 (`import { InlineHelp } from "@/components/ui/InlineHelp";`).
- **Task 3 (kuro ParameterPanel)**: row #1-10 (10개) 위치 정확히 Edit. import 이미 있음.
- **Task 3b (kuro DiversitySections)**: row #11-21, #24-25 (13개) + section header row #2-3. 파일은 `HelpTip` 사용. 신규 위치는 `InlineHelp` 추가 가능하나 일관성 위해 `HelpTip` 재사용 검토 권장. import 두 방법 다 가능.
- **Task 3c (kuro SequenceInput, MutationInput)**: row #22, #23 (2개). import 추가 필요.
- **Task 4 (section headers)**: row #1-3 (3개). `<div>` 또는 `<h3>` 내부 텍스트 옆 `<InlineHelp>` 추가.

## 검증

- 40 row = 12 + 25 + 3 정확
- 각 row의 File:Line은 본 작성 시점 (2026-05-18) git HEAD 기준. 후속 에이전트는 작업 직전 `rg -n "<현재 텍스트>" <file>` 로 라인 재확인.
- i18n 키 중복 없음 (모두 `*Help` suffix).

karpathy-guidelines 준수: 가정 명시 (plan 12+25+3 중 일부는 ParameterPanel 외 확장), 추측 금지 (모든 row는 코드 직접 확인), 최소 코드 (InlineHelp/HelpTip 재사용, 신규 컴포넌트 0).
