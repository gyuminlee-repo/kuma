# Step 3. Parameters

polymerase profile, codon strategy, Tm/GC 범위를 지정한다.

## Polymerase profile

7 종 내장 + custom:

- Taq, Phusion, Q5, Q5 SDM, KOD, DreamTaq, TAKARA_GXL (기본값 KOD)
- Custom profile 은 `~/.kuma/kuro/custom_polymerases.json` 에 저장.

profile 선택 시 설계에 반영되는 값은 GC 범위와 overlap 모드다. 설계 시점 Tm 은 SantaLucia 1998 (Benchling) 고정 스케일이라 profile 을 바꿔도 변하지 않는다. profile 의 Tm method · salt · DNA 값은 권장 annealing 온도(Ta) 계산에만 쓰인다.

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
