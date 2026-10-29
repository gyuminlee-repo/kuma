# Step 3. Parameters

polymerase profile, Tm/GC 범위, 프라이머 길이 제한을 지정한다. 코돈 표는 이 화면이 아니라 [Step 1](01-load.md) 의 Organism 에서 고른다.

## Polymerase profile

7 종 내장 + custom:

- Taq, Phusion, Q5, Q5 SDM, KOD, DreamTaq, TAKARA_GXL (기본값 KOD)
- Custom profile 은 `~/.kuma/kuro/custom_polymerases.json` 에 저장.

profile 선택 시 설계에 반영되는 값은 GC 범위와 overlap 모드다. 설계 시점 Tm 은 SantaLucia 1998 (Benchling) 고정 스케일이라 profile 을 바꿔도 변하지 않는다. profile 의 Tm method · salt · DNA 값은 권장 annealing 온도(Ta) 계산에만 쓰인다.

## 코돈 선택

고를 전략 값은 없다. 이 패널에 있던 Codon strategy select 는 v0.16.60 에서 빠졌다. 두 값이 같은 후보 집합을 순서만 바꿔 돌려주었고 엔진이 그 순서를 penalty 로 다시 정렬했기 때문이다.

지금은 타겟 아미노산의 동의 코돈 전부가 후보다. WT 코돈과 선택한 organism 이 그 아미노산의 10% 미만(`codon_table.CODON_USAGE_FLOOR`)으로 쓰는 코돈이 빠진다. 남은 후보를 설계 penalty 가 WT 대비 염기 변경 수(1/2/3 변경에 0/2/4)와 사용빈도(`sdm_engine.USAGE_WEIGHT` 4.0 x (1 - usage fraction))로 Tm·GC 와 함께 점수 매긴다. 코돈에 영향을 주는 사용자 입력은 Step 1 의 Organism 하나다.

## Tm / GC

- Default: Fwd 62 °C, Rev 58 °C, Overlap 42 °C
- Tolerance: ±0.5 ~ ±10.0 °C (default 4.0)
- GC range: 40-60 % (Advanced Options 에서 조정)

## Length

Fwd/Rev min/max length 제한 옵션.

## Off-target

- 기본 판정은 primer 3' 말단이 그 자리에서 연장될 수 있거나 Gibson overlap arm 이 결합을 지탱하는 자리 중 duplex Tm 이 45 °C 이상인 곳이다(`sdm_engine.check_offtarget`). hit 이 있는 후보는 탈락한다.
- v0.16.79 부터 원형 템플릿은 원점을 가로지르는 자리까지, 선형 템플릿은 서열 끝을 넘는 부분 결합 자리까지 평가한다. topology 는 `detect_topology` 가 파일 annotation 에서 읽고 FASTA 는 선형이다.
- Advanced Options 의 `Strict off-target check`(기본 꺼짐)를 켜면 15 bases 이상 연속 구간의 정확 일치(양쪽 가닥, 의도한 자리 제외)도 탈락 사유가 된다(`check_offtarget_strict`). 이 검사 때문에만 실패한 돌연변이는 실패 사유에 `strict off-target` 표시가 붙는다. 값은 workspace, autosave, 내보낸 워크북 메타에 기록된다.

## v0.9.2.x 변경

- ParameterPanel 의 모든 local state 가 Next 클릭 시 store 로 flush 된다. Submit step 의 Design summary 카드 값이 항상 일치.

→ [Step 4. Submit Design](04-submit.md)
