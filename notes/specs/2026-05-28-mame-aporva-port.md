---
date: 2026-05-28
type: spec
project: kuma-mame
status: approved
---

# MAME Aporva Pipeline Port: 3-Phase Plan

## 결정사항
- UI 흐름: combinatorial_demux (Aporva 방식) 정식 sort 경로로 채택
- Legacy sort_barcode.py sliding+edlib 코드 즉시 삭제 방침
- 3-PR 단계 분할로 점진적 머지

## Phase 0 (완료, PR #28)
- 백엔드 라이브러리 + CLI script

## Phase 1 (PR-A, v0.10.3.0)

### Backend (Python)
- 신규 RPC: `python-core/sidecar_mame/handlers/combinatorial_demux.py` 안 `handle_run_combinatorial_demux(params: dict)`
- Pydantic params 모델 `python-core/sidecar_mame/models.py` 에 `CombinatorialDemuxParams` 추가
- dispatcher `_METHODS` 등록
- progress notification: align/coverage/demux/consensus 단계별 비율

### Frontend (TS/React)
- 신규 slice 또는 inputSlice 확장: coverage_fraction(0.98), edit_dist_ratio(0.25), chimera_split(true)
- ParameterPanel.tsx: Input Source raw_run 선택 시 Aporva 활성화, Advanced 섹션에 3개 파라미터 노출, Trim Adapters/Rev Primer/Min Barcode Score 영역 숨김
- selectors.selectCanRun: 필수 입력 검증
- Run 버튼 -> 새 RPC 호출
- pnpm gen:models 자동 재생성

### Cross-layer
- _METHODS <-> RpcMethodMap sync
- Pydantic <-> TS generated freshness

### Tests
- Python RPC handler 통합 테스트
- TS ParameterPanel 렌더링 + legacy 필드 숨김 검증

## Phase 2 (PR-B, v0.11.0.0)

### 삭제
- kuma_core/mame/ingest/sort_barcode.py 의 sliding+edlib 함수
- python-core/sidecar_mame/handlers/sort_barcode.py RPC
- ParameterPanel.tsx의 Trim Adapters/Rev Primer/Min Barcode Score UI
- tests/mame/test_sort_barcode.py 46개 정리

### 문서
- CHANGELOG.md (v0.10.3.0 + v0.11.0.0)
- docs/inputs/barcodes.md (xlsx 스키마)
- docs/mame-pipeline.md (Aporva 흐름 다이어그램)
- $OBSIDIAN_VAULT 분석 노트 끝에 통합 완료 섹션

## 출력 구조

```
{export_dest}/
├── sort_barcode{NN}/
│   ├── A01_V5F_F1_R1.fasta
│   └── ...
├── consensus/{NN}/A01_consensus.fasta
└── {export}.xlsx
```

## 위험
- mappy/edlib Windows wheel 가용성
- 96-well consensus 약 수분 소요, progress notification 필수
- Legacy 삭제 시 다른 모듈 의존 grep 선행 필수
