# Variant budgets and residue evidence: frozen implementation contract

Base: PR #5, `2b9218268cce7cba876742fda8a4ff94369ab505`. This follow-up does not merge that PR.

## Application slice

The existing exact-frame single-site mode and legacy defaults remain available. A new explicit `distinct_variants` budget keeps different substitutions at one reference site. N counts distinct canonical variant IDs, not sites. Exact duplicate IDs collapse; conflicting scores, invalid identities and multisite rows fail this opt-in path. Missing/nonfinite coordinates and no-op substitutions are excluded and counted. The prior source parser/start-position policy remains separately reported.

The default cap in this new mode is unlimited. An optional positive per-site cap is a user constraint, checked before selection. Within a site only the highest configured-rank substitutions up to that explicit cap are eligible; equal scores use variant ID. No unseen substitutions are fabricated. Infeasible N fails without shrinking or rescue replacement.

Reuse existing full-pool FPS at kappa=0 with no anchors. Seed uses configured score rank. Distance ties use score, reference position then variant ID. Once every eligible coordinate is represented, additional selections have zero geometric gain and follow score/tie order. This is budget allocation, not fitness optimization or additional spatial spread. Report variant count, occupied-site count, multiplicities and both duplicate-inclusive and unique-site distances. Coordinate uncertainty is separate from finite-coordinate validity.

Certificates include budget and cap. Changing them invalidates the preview. Design revalidates the same source/reference/candidate bytes and forwards exactly the reviewed IDs once. No automatic rescue or count expansion. Viewer may highlight each occupied site once while the candidate table retains every selected substitution.

## Experimental evidence slice

Residue mapping utilities are initially offline: complete polymer sequence and observed C-alpha records are separate, full residue identity is retained, missing/indel positions never acquire interpolated coordinates. Exact mapping remains the app default. Opt-in homolog alignment rejects ambiguous equally optimal correspondence; SIFTS claims require actual residue-level evidence and matching identities. No universal sequence-identity cutoff is introduced.

Confidence records need declared source/frame. pLDDT is local confidence, PAE is pairwise and directional; missing evidence stays unknown. No universal filtering threshold or functional interpretation is inferred. Unsupported scientific integration stays offline until actual consumers preserve these identities.

The independent retrospective pilot freezes available public assay/scorer pairs before outcome evaluation, uses N=95 distinct variants and unlimited cap, and compares the same eligible pool. Assay outcomes never drive selection or tuning. Functional labels are evidence-bearing overlapping sets with no duplicate reward; absent labels are unknown, not negative. Public data availability, mapping and scored-pool feasibility are gates. Geometry, model score and measured assay outcomes are reported separately. No algorithm is promoted merely because one metric improves.

## Acceptance and limits

Test repeated-site variants, exact duplicates, capacity/cap failures, score direction, rigid transforms, input order, invalid coordinates, stale policy and exact design forwarding. Re-run focused and full suites plus exact-head CI. Mapping tests distinguish synthetic contracts from public-file checks. Native UI evidence requires an actual launch/test; build or mocked RPC passes are insufficient.

한국어 요약: N은 서로 다른 변이 ID 수이며 위치 수와 따로 센다. 같은 위치의 다른 치환은 유지하고 위치별 상한은 사용자가 명시한 경우만 적용한다. 모든 좌표가 대표된 뒤의 추가 선정은 공간 분산 증가가 아니라 점수·동점 규칙에 따른 배치다. 잔기 대응과 구조 불확실성의 실험적 도구는 검증되지 않은 앱 기능으로 소개하지 않는다. 실측 결과를 선정 입력으로 사용하지 않으며 실행한 검사와 미실행 영역을 구분한다.
