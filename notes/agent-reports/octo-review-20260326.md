# KURO Octopus Code Review Report

**Date**: 2026-03-26
**Target**: 전체 코드베이스 (v0.9.27 → v0.9.28)
**Provenance**: AI-assisted code
**Status**: ALL FIXES APPLIED — 83 tests passed (38 existing + 45 new)
**Reviewers**: Code Reviewer (Python), Security Auditor, Frontend Developer, Backend Architect

---

## Executive Summary

| Severity | 건수 | 주요 영역 |
|----------|------|-----------|
| **Critical** | 6 | 프로파일 오염, reverse primer 추출 오류, IPC race, 권한 과다, 상태 분리, 타입 불일치 |
| **Major** | 16 | CLI 로직 오류, 스키마 부재, sidecar 테스트 0건, 접근성, CSV race condition |
| **Minor** | 18 | 코드 구조, 의존성, a11y 세부, 기본값 불일치 |
| **Info** | 8 | 아키텍처 적절성, 긍정적 보안 관행 |

**즉시 수정 필요 (Top 5)**:
1. PolymeraseProfile 공유 객체 직접 변이 -- 실험 데이터 오염 위험
2. `_extend_reverse` non-overlap 추출 위치 오류 -- 프라이머 서열 부정확
3. `shell:allow-execute` 불필요 권한 -- 임의 명령 실행 가능
4. IPC spawn 실패 시 좀비 프로세스 -- 앱 크래시
5. CLI `generate_plate_map` 반환값 처리 오류 -- 런타임 에러

---

## Critical Findings (6건)

### C-1. PolymeraseProfile 공유 객체 직접 변이 (Python + Sidecar)

| 항목 | 내용 |
|------|------|
| 파일 | `sdm_engine.py:841-846`, `sidecar_main.py:780-783` |
| 발견 | Code Reviewer + Architect (교차 확인) |
| 영향 | retry 호출 후 "Benchling" 프로파일 Tm이 영구 변경, 이후 모든 설계에 잘못된 Tm 적용 |
| 수정 | `dataclasses.replace(profile, opt_tm_fwd=tm_fwd_target)` -- 1줄 수정 |

```python
# Before (오염)
profile = registry.get(polymerase)
profile.opt_tm_fwd = tm_fwd_target

# After (안전)
profile = dataclasses.replace(registry.get(polymerase), opt_tm_fwd=tm_fwd_target)
```

### C-2. `_extend_reverse` non-overlap 추출 위치 오류

| 항목 | 내용 |
|------|------|
| 파일 | `sdm_engine.py:220` |
| 발견 | Code Reviewer |
| 영향 | `reverse_binding` 필드가 실제 template-binding 부분이 아닌 overlap의 rc를 저장. UI 표시 및 off-target 판정에 영향 |
| 수정 | `candidate[:ext_len]` -> `candidate[-ext_len:]` (rc 후 extension은 뒤쪽에 위치) |

```python
# Before (오류)
nonoverlap = candidate[:ext_len] if ext_len > 0 else ""

# After (정확)
nonoverlap = candidate[-ext_len:] if ext_len > 0 else ""
```

### C-3. Tauri `shell:allow-execute` 권한 과다 (보안)

| 항목 | 내용 |
|------|------|
| 파일 | `src-tauri/capabilities/default.json:10` |
| 발견 | Security Auditor |
| 영향 | 프론트엔드에서 임의 시스템 명령 실행 가능. XSS나 악성 의존성 주입 시 호스트 OS 장악 |
| 수정 | `"shell:allow-execute"` 라인 삭제. sidecar는 `shell:allow-spawn`으로 이미 동작 |

### C-4. IPC spawnSidecar 레이스 컨디션 + 좀비 프로세스

| 항목 | 내용 |
|------|------|
| 파일 | `src/lib/ipc.ts:65-117` |
| 발견 | Frontend Developer |
| 영향 | spawn 실패 시 `child`가 non-null로 남아 좀비 프로세스 발생, ready 대기 timeout 시 복구 불가 |
| 수정 | spawn 실패 시 `child?.kill()` + `child = null` 명시적 정리 |

### C-5. 전역 상태 별칭(`_last_*`)과 `_state` 객체 분리

| 항목 | 내용 |
|------|------|
| 파일 | `sidecar_main.py:67-72, 254-260` |
| 발견 | Code Reviewer + Architect (교차 확인) |
| 영향 | `global _last_results` 재바인딩 후 `_state.results`와 분리. 혼용 시 silent data loss |
| 수정 | 레거시 별칭 제거, `_state` 인스턴스를 단일 진실 소스로 통일 |

### C-6. `design_sdm_primers` 반환 타입 힌트 불일치

| 항목 | 내용 |
|------|------|
| 파일 | `sdm_engine.py:811` (선언) vs `:910` (실제 반환) |
| 발견 | Code Reviewer |
| 영향 | 2-tuple 선언이지만 3-tuple 반환. mypy/정적 분석 통과 불가 |
| 수정 | 타입 힌트를 `tuple[list[...], dict[...], dict[str, str]]`로 수정 |

---

## Major Findings (16건)

### Python 코어 (7건)

| ID | 파일 | 내용 |
|----|------|------|
| M-P1 | `cli.py:48-50` | `generate_plate_map` 반환 tuple을 단일 변수로 처리 -- `AttributeError` 발생 |
| M-P2 | `sdm_engine.py:756-766` | `_detect_orfs` CDS end convention이 GenBank와 불일치 (stop codon 포함 여부) |
| M-P3 | `cli.py:100-104` | `Off_Target` 값으로 `tm_condition_met` 판정 -- 논리적으로 독립 속성 |
| M-P4 | `sdm_engine.py:282-286` | antisense off-target 좌표 변환 시 음수 start 미처리 |
| M-P5 | `sidecar_main.py:808` | accession 입력 검증 없이 외부 URL 구성 (SSRF 위험) |
| M-P6 | tests/ | `polymerase.py`, `codon_table.py` 단위 테스트 없음 |
| M-P7 | `codon_table.py:12` | 빈도 정렬 주석과 실제 순서 불일치 |

### 프론트엔드 (5건)

| ID | 파일 | 내용 |
|----|------|------|
| M-F1 | `appStore.ts:1-791` | 791줄 단일 스토어에 비즈니스 로직 과다 집중 |
| M-F2 | `appStore.ts:201-255` | setter 5개가 `loadEvolveproCsv` 연쇄 호출 -- stale state 덮어쓰기 |
| M-F3 | `appStore.ts:671-673` | `resetAll()`이 `INITIAL_STATE`의 Set 인스턴스를 재사용 (이전 세션 데이터 잔류) |
| M-F4 | `ResultTable.tsx` | 커스텀 모달 3개에 접근성 부재 (role, focus trap, ESC, aria 없음) |
| M-F5 | `AppLayout.tsx:135` | StatusBar에서 `useSidecar` 호출 -- 리마운트 시 sidecar kill/respawn |

### 아키텍처 (2건)

| ID | 파일 | 내용 |
|----|------|------|
| M-A1 | `models.ts` / `sidecar_main.py` | IPC 계약에 공식 스키마 없음. 양쪽 독립 수정 시 런타임 `undefined` |
| M-A2 | `cli.py` / `sidecar_main.py` | CLI와 Sidecar 간 파이프라인 로직 중복 (sidecar 전용 기능 CLI 미지원) |

### 보안 (2건)

| ID | 파일 | 내용 |
|----|------|------|
| M-S1 | `sidecar_main.py:107-129` | 파일 경로 검증에 path traversal 방어 미비 |
| M-S2 | `sidecar_main.py:337` | 임시 CSV 파일 권한 0o644 (다른 사용자 읽기 가능) |

---

## Minor Findings (18건, 요약)

**Python**: SdmPrimerResult 23필드 평면 구조, `setattr` 타입 안전성 상실, sidecar 850줄 단일 파일, codon_table E. coli only placeholder, `overlap.py` step 파라미터 미사용, private `_design_single_sdm` import

**Frontend**: ResultTable.tsx 1163줄/7 컴포넌트, wellName/ROWS 중복 정의, restoreWorkspace 기본값 불일치(18 vs 12), InputPanel 27개 selector, tailwind.config.js require() 구문

**보안**: DEV 모드 글로벌 스토어 노출, `.gitignore`에 `.env*`/`*.pem` 누락, Python/JS 버전 불일치, `index.html` title "SDMBench", SSL 컨텍스트 미명시, Rust 의존성 메이저 버전만 명시

**접근성**: PlateMap table aria-label/caption 없음, ResultTable 정렬 헤더 키보드 불가, label-input htmlFor 미연결, StatusBar 상태 표시등 스크린리더 미지원

---

## 긍정적 평가

| 항목 | 평가 |
|------|------|
| **아키텍처 선택** | Tauri + Python sidecar (JSON-RPC over stdin/stdout) -- 이 유스케이스에 최적 |
| **입력 검증** | mutation notation 정규식 검증, 파일 확장자 화이트리스트, 심볼릭 링크 차단 |
| **보안 기본기** | `eval()/exec()` 미사용, CSP `default-src 'self'`, React XSS 자동 방어 |
| **CI/CD** | Node.js 24 호환 Actions 버전, 3-platform 빌드 매트릭스 |
| **테스트** | 38 passed, integration 수준 커버리지 양호. assertion 품질 적절 |
| **MOCK_MODE** | Vite alias 기반 Tauri stub -- 브라우저 UI 개발 가능 |

---

## 수정 로드맵 (권장 순서)

### Phase 1: 즉시 수정 (데이터 정확성 + 보안)
1. **C-1**: PolymeraseProfile `dataclasses.replace()` -- 1줄
2. **C-2**: `_extend_reverse` non-overlap 인덱스 수정 -- 1줄
3. **C-3**: `shell:allow-execute` 제거 -- 1줄
4. **C-6**: 반환 타입 힌트 수정 -- 1줄
5. **M-P1**: CLI `generate_plate_map` 반환값 언패킹 수정

### Phase 2: 안정성 (1-2일)
6. **C-4**: IPC spawn 실패 시 child 정리
7. **C-5**: `_state` 단일 소스 통일 + 레거시 별칭 제거
8. **M-F3**: `INITIAL_STATE`를 팩토리 함수로 전환
9. **M-F2**: CSV 로드에 debounce/AbortController 적용

### Phase 3: 품질 향상 (1주)
10. **M-A1**: JSON Schema 기반 IPC 계약 정의
11. **M-P6**: polymerase, codon_table 단위 테스트 추가
12. **M-F4**: 커스텀 모달을 Radix Dialog로 교체
13. **M-S1**: 파일 경로 allowlist 검증 추가

### Phase 4: 구조 개선 (장기)
14. **M-A2**: CLI/Sidecar 공통 서비스 레이어 추출
15. **M-F1**: appStore 액션 모듈 분리
16. sidecar_main.py 모듈 분리
