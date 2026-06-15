# Step 3. Parameters

설계 방식(design method), polymerase profile, codon strategy, Tm/GC 범위를 지정한다.

## 설계 방식 (Design method)

run 단위로 클로닝 방식을 고른다.

| 값 | 의미 |
|---|---|
| Overlap-extension | (기본) overlap extension SDM. 출력은 기존과 byte-identical |
| Golden Gate (Type IIS) | 변이 코돈 주변에 효소 인식 부위 + fidelity 점수 overhang 을 삽입 |

**Golden Gate 선택 시**

- **효소**: 내장 6종 (BsaI, BsmBI, BbsI, SapI, PaqCI, BspMI). BsaI·BsmBI 는 on-target ligation fidelity 표(Potapov 2018)로 최적 overhang 을 고르고, 나머지는 functional unscored overhang 으로 대체. **Custom enzyme…** 항목으로 사용자 효소 추가 → `~/.kuma/kuro/custom_enzymes.json` 에 영구 저장. ParameterPanel 이 인식 부위·cut 위치·overhang 길이를 표시.
- **코돈 사용**: 선택 organism 의 Kazusa 빈도 기반(frequency 내림차순 + 결정적 tiebreak). 설계 window(변이 코돈 중심 15 nt) 안에 forbidden Type IIS 부위를 만드는 코돈은 자동 제외.
- **Junction**: junction prefix(spacer + 인식 부위 + spacer)와 forbidden overhang(기본 `AATG`, `AGGT`)을 run 단위로 오버라이드. 비워두면 효소 카탈로그 기본값 사용. 인식 부위 누락·cut 위치 오류 prefix 는 각 결과에 경고로 표시.
- **Tm**: SantaLucia 1998(SnapGene) 모델을 overlap-extension 과 공유. annealing 영역을 최저 초기 Tm + 4 °C 이내로 batch 정규화(하한 20 nt). 아래 PCR Tm/GC/길이 파라미터는 Golden Gate 에 적용되지 않는다.

## Polymerase profile

8 종 내장 + custom:

- Benchling, Taq, Phusion, Q5, Q5 SDM, KOD, DreamTaq, TAKARA_GXL
- Custom profile 은 `~/.kuma/kuro/custom_polymerases.json` 에 저장.

profile 선택 시 Tm method · salt · DNA · GC 범위가 manufacturer manual 기준으로 즉시 갱신된다.

## Codon strategy

| 값 | 의미 |
|---|---|
| Min. changes | WT 코돈에서 최소 염기 변경 |
| Optimal | E. coli 최적 codon |

## Tm / GC

- Default: Fwd 62 °C, Rev 58 °C, Overlap 42 °C
- Tolerance: ±0.5 ~ ±10.0 °C (default 3.0)
- GC range: 40-60 % (Advanced Options 에서 조정)

## Length

Fwd/Rev min/max length 제한 옵션.

## v0.9.2.x 변경

- ParameterPanel 의 모든 local state 가 Next 클릭 시 store 로 flush 된다. Submit step 의 Design summary 카드 값이 항상 일치.

→ [Step 4. Submit Design](04-submit.md)
