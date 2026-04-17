# 다양성 전략

![위치 다양성](../screenshots/08-diversity-position.png)

![InterPro 도메인 기반 다양성](../screenshots/09-diversity-domain.png)

EVOLVEpro / MULTI-evolve 모드에서만 사용 가능. 전략들은 누적 적용 — 여러 개 활성화 시 필터가 결합됨.

## Position diversity

같은 위치의 변이 수 제한. 단일 hotspot 과샘플링 방지.

- **max-per-position**: 1 / 2 / 3 (0 = 비활성)

## Domain diversity

선택된 UniProt accession에서 InterPro/Pfam으로 가져온 도메인별로 픽을 분배.

- **Strategy**: proportional (도메인 크기 비례) / equal (도메인당 동일 quota)
- **Overlap policy**: first / largest (도메인 겹칠 때)
- **Linker handling**: include / exclude / separate-bin
- **Quota min**: 도메인당 최소 픽 수 (0–20)

개별 도메인은 인라인에서 비활성 가능; quota가 재계산됨.

## Pareto diversity

예측 fitness × diversity 점수의 frontier에서 선택.

- **Distance mode**: auto / 1d (잔기 위치) / 3d (AlphaFold Cα 유클리드 거리)
- **Pool multiplier**: 타깃 수의 배수로 후보 풀 크기 (1–10)

## Entropy weight

위치별 `y_pred` Shannon entropy를 Pareto 점수에 혼합. 예측 불확실성이 높은 위치에 가중.

- **Weight**: 0.0–1.0 (기본 0.3)

## σ-Adaptive pool

EVOLVEpro 라운드·라운드 사이즈에 따라 풀 크기 스케일링. 라운드 높을수록 풀 좁아짐.

*스텁 — 전략 패널 스크린샷 추가 예정.*
