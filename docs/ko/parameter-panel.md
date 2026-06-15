# 파라미터 패널

![Advanced options 확장](../screenshots/06-parameter-advanced.png)

설계 방식(design method), 폴리머레이즈 프로파일, 코돈 전략, 프라이머 Tm/GC/길이 제약을 관리.

## 설계 방식 (Design method)

run 단위로 클로닝 방식을 고른다:

- **Overlap-extension** (기본) — overlap-extension SDM. 출력은 기존과 동일.
- **Golden Gate (Type IIS)** — 변이 코돈 주변에 효소 인식 부위 + ligation fidelity 점수 overhang 을 삽입하는 프라이머를 설계.

Golden Gate 선택 시:

- **효소** — 내장 6종 (BsaI, BsmBI, BbsI, SapI, PaqCI, BspMI). BsaI·BsmBI 는 on-target ligation fidelity 표(Potapov 2018)로 최적 overhang 선택, 나머지는 functional unscored overhang 으로 대체. **Custom enzyme…** 로 사용자 효소 추가 → `~/.kuma/kuro/custom_enzymes.json` 저장.
- **코돈 사용** — organism 별 Kazusa 빈도 기반. 설계 window 안에 forbidden Type IIS 부위를 만드는 코돈은 자동 제외.
- **Junction** — junction prefix(spacer + 인식 부위 + spacer)와 forbidden overhang(기본 `AATG`, `AGGT`)을 벡터에 맞게 오버라이드. 인식 부위 누락·cut 위치 오류 prefix 는 각 결과에 경고.
- **Tm** — SantaLucia 1998(SnapGene) 모델을 overlap-extension 과 공유. 아래 PCR Tm/GC/길이 파라미터는 Golden Gate 에 적용되지 않음.

## Polymerase

기본 7개 프로파일 (Q5, KOD, Phusion, Herculase II, PfuUltra II, KAPA HiFi, Takara PrimeSTAR GXL). 선택 시 해당 프로파일의 Tm target, salt/Mg²⁺ 보정, GC 범위가 자동 로드됨.

커스텀 프로파일 — [커스텀 폴리머레이즈 에디터](custom-polymerase-editor.md).

## Codon 전략

- **Min. changes** (기본): WT 코돈에서 가장 적은 nt 변경
- **Optimal**: 선택 organism의 최다 빈도 코돈

## Mutations 수

목표 성공 설계 수. 기본 95 (플레이트 1장에서 control 제외). 기본 organism은 *E. coli* — 메뉴에서 전환 가능.

상한: 10,000 (v1.33.6+).

입력 아래에 플레이트 프리뷰 표시 (`Math.ceil(N / 96)`).

## Advanced options

- **Tm targets**: fwd / rev / overlap (°C)
- **GC 범위**: min / max (%)
- **프라이머 길이 범위**: fwd-min/max, rev-min/max — 폴리머레이즈 기본값 오버라이드
- **Fill on failure**: 실패 시 버퍼 후보로 자동 채움
