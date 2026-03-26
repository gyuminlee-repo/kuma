# KURO 업데이트 노트 — v0.9.5 → v0.9.27

**한국어** | [English](UPDATE-NOTES.md)

배포일: 2026-03-26

---

## Export

- **Excel List 시트에 Tm 및 코돈 데이터 추가**: Fwd/Rev List 시트에 기존 Well, Primer Name, Sequence, Length, Mutation 외에 Tm, Tm_Overlap, WT_Codon, MT_Codon 컬럼 포함
- **정렬 순서가 export에 반영**: 결과 테이블에서 적용한 컬럼 정렬이 Excel plate map 출력에도 유지됨

## Parameters

- **프라이머 길이 제한**: Advanced Options에서 Fwd/Rev min/max 프라이머 길이를 선택적으로 설정 가능. 기본값: Fwd 18-45 bp, Rev 18-30 bp
- **Fill on failure** (기본 ON): 일부 mutation 설계 실패 시 다음 순위 후보로 자동 대체하여 요청 수를 채움. 비활성화하면 지정 수만큼만 시도하고 실패분은 차감
- **Mutations 파라미터 = 최종 성공 개수**: Mutations 숫자가 입력 제한이 아닌 최종 성공 설계 목표를 의미
- **프라이머 최소 길이 상향**: 기본 최소 프라이머 길이가 12 bp에서 18 bp로 변경

## EVOLVEpro

- **도메인 다양성(Domain diversity)**: 단백질 구조 도메인 간 Top-N variant 선택을 분산. UniProt accession 입력 시 InterPro/Pfam에서 도메인 경계를 자동 조회하거나 수동 정의 가능. 비례 배분(proportional) 또는 균등 배분(equal) 전략 지원
- **Pareto 다양성(Pareto diversity)**: MODIFY 방식의 fitness-diversity 동시 최적화. Greedy maximin 알고리즘으로 선택된 variant 간 위치 분산을 최대화. 단독 사용 또는 도메인 다양성과 결합 가능 (도메인 내에서 Pareto 적용)
- **위치 다양성(Position diversity) 필터**: 아미노산 위치당 mutation 수를 제한하는 선택적 체크박스. 같은 위치의 고점수 mutation(예: Q10A, Q10L, Q10V)이 선택을 독점하는 것을 방지. 위치당 최대 수 조절 가능 (기본값 1)
- 세 가지 다양성 필터(Position, Domain, Pareto)는 독립 토글 — 어떤 조합이든 사용 가능. 모두 OFF = 순수 y_pred Top-N (기본 동작)

## 결과 테이블

- **모든 컬럼 정렬 가능**: Forward/Reverse Primer 서열을 제외한 모든 컬럼을 헤더 클릭으로 정렬 가능. Hairpin(HP) 컬럼도 최악 Tm 기준 정렬 지원
- **실패 mutation 표시 개선**: 사용자가 의도한 상위 N개 mutation 중 실패한 것만 표시. 버퍼 초과분의 실패는 숨김. "Failed (N/목표)" 형식으로 표시

## 실패 Mutation 복구

- **파라미터 조절 재시도**: 실패한 mutation 태그 클릭 → Tm 목표, GC% 범위, 프라이머 길이 제한, tolerance 최대값을 조절할 수 있는 팝업이 열림. **Retry** 클릭 시 해당 mutation만 커스텀 파라미터로 재설계. 최대 10개 후보가 penalty 순으로 표시됨. **Select** 클릭으로 결과 테이블에 추가
- **수동 입력 유지**: 기존 수동 프라이머 입력 기능은 같은 팝업의 "Or enter manually..." 아래에서 사용 가능

## UI

- **Advanced Options 섹션 재구성**: 기존 평면 나열을 Tm / GC% / Primer Length / Design 섹션 라벨로 시각적 그루핑. Primer Length 체크박스와 입력이 더 적은 줄 수로 압축됨
- **상태 메시지 개선**: 상태 바에 성공/목표 수, Tm 조건 충족 비율, 실패 수 표시

## 개발자

- **버전 자동 동기화**: post-commit git hook(`scripts/sync-version.sh`)이 커밋 메시지에서 `vX.Y.Z:` 패턴을 감지하면 `package.json`, `tauri.conf.json`, `Cargo.toml` 버전을 자동 동기화
- **새 JSON-RPC API**: `retry_failed_mutation` — 커스텀 Tm/GC/길이/tolerance 파라미터로 단일 실패 mutation을 재설계, 최대 10개 후보 반환
