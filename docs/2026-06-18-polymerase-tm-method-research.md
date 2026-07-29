# 폴리머라제별 Tm 계산 방법·버퍼 조성 조사 (출처)

작성: 2026-06-18. 목적: KURO 프라이머 설계의 폴리머라제 인지 Tm 계산 배선(브랜치 feat/polymerase-aware-tm)의 근거. 모든 수치는 1차 출처 기준, 미확인 항목은 명시.

## 1. 제조사 Tm 계산 방법 (계산기/문서)

| 제조사 | NN 테이블 | salt correction | annealing(Ta) 규칙 | 확인도 |
|---|---|---|---|---|
| NEB (Q5/Phusion/Taq) | SantaLucia 1998 | Q5·Taq: Owczarzy 2004 / Phusion: Schildkraut-Lifson | Q5: Tm+6~12°C, Phusion: Tm+3°C, Taq: Tm−5°C | 확인 |
| Thermo (Phusion/DreamTaq) | Breslauer 1986 (추정) | 미공개 | 미공개 | 부분 |
| Takara PrimeSTAR GXL | ≤25mer Wallace, >25mer NN | 미공개 | 고정 55~60°C | 부분 |
| Toyobo KOD | Wallace 2(A+T)+4(G+C) | 미공개 | Tm−5°C(3-step), min(Tm)(2-step) | 최소 |

## 2. 버퍼 조성 (1X 반응, primer3 calc_tm 입력용)

| 폴리머라제 | monovalent(mM) | Mg2+(mM) | dNTP total(mM) | primer(nM) | 확인도 |
|---|---|---|---|---|---|
| Q5 (NEB) | ~50 KCl (재현연구) | 2.0 | 0.8 | 250~500 | Mg/dNTP 확인, mv 중간 |
| Q5 SDM (NEB Hot Start 2X MM) | ~50 | 2.0 | 0.8 | 250~500 | 동상 |
| Phusion HF (NEB) | ~50 KCl(1X), 5X=100 | 1.5 | 0.8 | 500 | Mg/dNTP 확인, mv 중간 |
| Standard Taq (NEB) | 50 KCl | 1.5 | 0.8 | 500 | 확인 |
| ThermoPol Taq (NEB) | 10 KCl + 10 (NH4)2SO4 | 2.0 | 0.8 | 500 | 확인 |
| DreamTaq (Thermo) | 미공개 | 2.0 | 0.8 | 500 | Mg 확인, mv 불가 |
| KOD (Toyobo) | 문헌 10 KCl + 6 (NH4)2SO4 | 2.0 | 0.8 | 250~500 | 미공개(문헌만) |
| PrimeSTAR GXL (Takara) | 미공개 | 1.0 | 0.8 | 200~300 | Mg 확인, mv 불가 |

주의: primer3 calc_tm은 total Mg2+를 받고 dNTP chelation(Owczarzy 2008)을 내부 보정. free Mg2+ 아님.

## 3. 현재 프로파일(polymerase_profiles.json) 대조

- salt_correction: Q5=owczarzy, Phusion=schildkraut, Taq=owczarzy 로 NEB 문서와 일치 (잘 설정됨).
- monovalent: Q5=150, Phusion=222 로 NEB 1X(~50 mM)과 불일치 (교정 후보, 5X/이온세기 혼입 의심).
- Mg2+/dNTP: 6개 프로파일이 0/0 이던 것을 위 확인값으로 교정 완료(이 브랜치).

## 4. 출처 URL

### NEB
- NEB Tm Calculator: https://tmcalculator.neb.com/
- NEB Tm API: https://tmapi.neb.com/
- NEB Q5: https://www.neb.com/en-us/products/m0491-q5-high-fidelity-dna-polymerase
- NEB Q5 Hot Start 2X MM: https://www.neb.com/en-us/products/m0494-q5-hot-start-high-fidelity-2x-master-mix
- NEB Phusion HF: https://www.neb.com/en-us/products/m0530-phusion-high-fidelity-dna-polymerase
- NEB Phusion 최적화: https://www.neb.com/en/protocols/guidelines-for-pcr-optimization-with-phusion-high-fidelity-dna-polymerase
- NEB Standard Taq: https://www.neb.com/en-us/products/m0273-taq-dna-polymerase-with-standard-taq-buffer
- NEB ThermoPol FAQ: https://www.neb.com/en/faqs/what-is-the-composition-of-the-thermopol-df-detergent-free-buffer
- NEB OneTaq 최적화: https://www.neb.com/en-us/tools-and-resources/usage-guidelines/guidelines-for-pcr-optimization-with-onetaq-and-onetaq-hot-start-dna-polymerases
- NEB Q5 primer 농도 FAQ: https://www.neb.com/faqs/2012/08/21/what-should-my-primer-concentration-be-when-using-q5-high-fidelity-dna-polymerase-products
- NEB buffer formulation table: https://www.neb.com/en-us/tools-and-resources/selection-charts/buffer-and-diluent-formulation-table

### NEB 계산기 재현·비교 (2차)
- pydna issue #237 (NEB Tm calculator 재현): https://github.com/pydna-group/pydna/issues/237
- phiweger/prime (primer3 vs NEB 노트): https://github.com/phiweger/prime/blob/master/notes.md
- ToolUniverse NEB Tm tools: https://zitniklab.hms.harvard.edu/ToolUniverse/en/tools/neb_tm_tools.html
- Calcgator NEB Tm guide (Q5 Ta): https://calcgator.com/neb-tm-calculator-guide/

### Thermo / Takara / Toyobo
- Thermo Tm Calculator: https://www.thermofisher.com/us/en/home/brands/thermo-scientific/molecular-biology/molecular-biology-learning-center/molecular-biology-resource-library/thermo-scientific-web-tools/tm-calculator.html
- Thermo DreamTaq buffer: https://www.thermofisher.com/order/catalog/product/B65
- Takara PrimeSTAR GXL manual: https://takara.co.kr/file/manual/pdf/R050A_e.v1906Da.pdf
- Toyobo KOD: https://lifescience.toyobo.co.jp/detail/detail.php?product_detail_id=165
- Toyobo KOD manual: https://www.toyobo-global.com/sites/default/static_root/products/lifescience/support/manual/KOD-201.pdf

### 방법론 논문
- Breslauer et al. 1986, PNAS 83:3746-3750, "Prediction of DNA duplex stability using empirical parameters" https://doi.org/10.1073/pnas.83.11.3746
- Allawi & SantaLucia 1997, Biochemistry 36:10581-10594, "Thermodynamics and NMR of internal G.T mismatches in DNA" https://doi.org/10.1021/bi9724873
- SantaLucia 1998, PNAS 95:1460-1465, "A unified view of polymer, dumbbell, and oligonucleotide DNA nearest-neighbor thermodynamics" https://doi.org/10.1073/pnas.95.4.1460
- Owczarzy et al. 2004, Biochemistry 43:3537-3554, "Effects of sodium ions on DNA duplex oligomers: improved predictions of melting temperatures" https://doi.org/10.1021/bi034621r
- Owczarzy et al. 2008, Biochemistry 47:5336-5353, "Predicting stability of DNA duplexes in solutions containing magnesium and monovalent cations" https://doi.org/10.1021/bi702363u
- Schildkraut & Lifson 1965, Biopolymers 3:195-208, "Dependence of the melting temperature of DNA on salt concentration" https://doi.org/10.1002/bip.360030207

### primer3 / Biopython
- primer3-py calc_tm: tm_method(breslauer|santalucia), salt_corrections_method(schildkraut|santalucia|owczarzy) 지원 (로컬 검증)
- Biopython MeltingTemp: https://biopython.org/docs/1.76/api/Bio.SeqUtils.MeltingTemp.html

## 5. NEB Tm API 실측 대조 (2026-06-18, ground truth)

NEB Tm API(https://tmapi.neb.com/tm/{q5|phusion|taq}/0.5/{seq}/{seq}/?fmt=long, 500nM)로 6개 시퀀스 실측. KURO(primer3 santalucia + 프로파일 salt) 대비 차이:

| 시퀀스 | NEB Q5 | NEB Phusion | NEB Taq | KURO−NEB Q5 | KURO−NEB Phusion | KURO−NEB Taq |
|---|---|---|---|---|---|---|
| S1 GCTAGCTAGCTAGCTAGCTA | 62.36 | 57.24 | 55.37 | -0.9 | +2.7 | +4.7 |
| S2 GGCGGCGGCGGCGGCGGCGG | 91.86 | 82.60 | 86.37 | -2.6 | +2.7 | +1.8 |
| S3 CAGGAAACAGCTATGACCATG | 63.03 | 58.28 | 55.91 | -0.8 | +2.7 | +4.9 |
| S4 GTAAAACGACGGCCAGT | 62.27 | 56.57 | 55.43 | -0.9 | +2.7 | +4.3 |
| S5 ACGACTCACTATAGGGCGAATTGG | 68.33 | 63.82 | 61.10 | -0.9 | +2.7 | +5.1 |
| S6 GACCATGATTACGCCAAGCTTG | 66.37 | 61.65 | 59.22 | -0.9 | +2.7 | +4.9 |

판정:
- primer3(KURO)는 NEB 계산기를 수치 재현 못 함. NEB는 SantaLucia+Owczarzy에 product별 보정 추가 (pydna #237과 동일 관찰).
- Phusion: mv 222 -> ~110 으로 낮추면 NEB와 일치 (schildkraut는 monovalent 민감). mv=222는 오류로 판단.
- Q5(-0.9 근접, dna=2000 효과), Taq(+4.7 과대): monovalent 튜닝으로 해소 불가, NEB product 보정이 원인.
- 결론: NEB 기준 정확도가 필요하면 NEB Tm API 호출 또는 NEB 알고리즘 재구현 필요. primer3+버퍼는 self-consistent 근사이나 NEB-동일 아님.

출처: https://tmapi.neb.com/ , https://tmapi.neb.com/docs/productcodes , https://github.com/pydna-group/pydna/issues/237

## 6. NEB 보정 테이블 (A2 구현, 2026-06-18)

NEB Tm API로 72개 샘플(fixture substring, len 17-39, GC 40-60) x q5/phusion/taq 수집, primer3(고정 ref_config) 대비 offset을 선형 fit. 결과 kuma_core/kuro/resources/neb_tm_offsets.json:

- 모델: neb_tm = primer3(ref_config, seq) + (c0 + c1*len + c2*gc_percent)
- q5: coef=[2.2176,-0.0508,0.0357], 보정후 |est-NEB| 최대 0.22도
- phusion: coef=[2.8067,0,0] (상수), 최대 0.00도
- taq: coef=[-5.012,-0.0827,0.0515], 최대 0.30도
- 상수 offset은 q5/taq에 불충분(잔차 1.2/1.8도)이라 선형 채택. phusion만 상수 충분.
- ref_config는 편집 프로파일과 독립(고정). NEB poly만 적용, 비-NEB는 raw primer3.
- 재생성: python-core/scripts/regen_neb_offsets.py (NEB API 호출).
