# H: kuma PR #14 독립 검토 기록

검토 범위에서 신규 결함이 재현되지 않았다는 과거 기록을 보존한다. 정규 Python 회귀, 프런트엔드 테스트와 전체 타입 검사가 차단되어 전체 승인 판정은 유보한다. 아래 PASS는 2026-10-12의 기존 실행 기록이며 이번 문서 수정에서 제품을 재검증한 결과가 아니다.

## 문서 재구성 고지

이 문서는 PR #15의 손상된 한국어를 **편집 재구성**한 것이다. 깨끗한 원문을 확보하지 못했으므로 바이트 단위 원문 복원으로 간주하지 않는다. 근거는 [PR #15 본문](https://github.com/gyuminlee-repo/kuma/pull/15), [publication-state.json](publication-state.json), 보존된 스크립트·JSON·로그와 기존 보고서의 읽을 수 있는 토큰이다. 손실된 문장의 정확한 표현은 미확인이다.

수정 전 문서 커밋은 `8888a990cca9205c14e64edbe0cd644d2bf6f7fb`이다. 해당 커밋에서 `REVIEW-ko.md`에는 U+FFFD 2,911개, `REPRODUCE.md`에는 495개가 있다. `logs/models-explicit-python.log`의 U+FFFD 2개는 **과거 캡처의 인코딩 손실**로 남긴다. 원래 바이트를 확보하지 못했으므로 로그를 추정 복원하거나 새 실행처럼 바꾸지 않는다. 이 로그는 [현재 Markdown 인코딩 검사](REPRODUCE.md)의 대상에서 명시적으로 제외한다. 기존 비 Markdown 파일 25개는 그대로 보존한다.

## 대상과 역사적 범위

- 검토 PR: https://github.com/gyuminlee-repo/kuma/pull/14
- 검토 head: `0b5fb940ad9effc4eb9b9cb1f4bf96819c574efa`
- 검토 base: `c857b3560f45d2c5fd132b51bfd0920c25043983`
- head 브랜치: `feat/strict-spatial-confidence-topn-20261012`
- base 브랜치: `feat/variant-budget-residue-mapping-20261009`
- 보고서 게시 출발점 main: `9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4`

기존 보고서는 base...head의 변경 파일 25개를 검토 대상으로 기록했다. 저신뢰 좌표의 거리 계산 제외, 후보 풀 보존, 요청 개수의 자동 축소나 서열 거리 대체 여부, raw Top-N과 site 대표 Top-N 구분, 입력 잔기와 구조 좌표의 대응을 살폈다. PR의 AlphaFold TITLE 식별 규칙과 pLDDT < 50 정책을 전제로 한 검토다. 정책의 실험적 효용이나 assay 성능을 입증하는 범위는 아니다.

`publication-state.json`은 게시 직전 PR #14가 동일 head/base의 open draft였고 조회한 PR 14개에서 H 리뷰 중복을 찾지 못했다고 기록한다. PR #14의 base를 main으로 바꾸지 않았다. `logs/remote-refs-final.log`에는 당시 두 원격 SHA가 남아 있다. `logs/locale-tree.log`와 게시 상태에는 de, en, es, fr, ja, ko, pt-BR, ru, zh-CN, zh-TW가 기록되어 있다. 이는 현재 원격 상태에 관한 주장이 아니다.

기존 실행은 공개 소스의 별도 `source` checkout을 대상으로 했다. `logs/source-clean.log`는 당시 `git status --porcelain`의 빈 출력을 기록한다. 사용자 작업 checkout이나 미게시 locale·녹화 자료는 검토 입력으로 삼지 않았다.

## 기존 실행 기록

| 검사 | 당시 상태 | 보존 근거 |
|---|---|---|
| 원격 SHA와 locale 파일 | PASS 기록 | `publication-state.json`, `logs/remote-refs-final.log`, `logs/locale-tree.log` |
| 실제 Python 선택기·CSV 로더 합성 검사 26건 | PASS 기록, 실패 0 | `synthetic_checks.py`, `synthetic-results.json`, `logs/synthetic.log` |
| 공개 AlphaFold v6 구조 2건 | PASS 기록 | `public_checks.py`, `public-results.json`, `logs/public.log` |
| 실제 TS validator 5건 | PASS 기록 | `validator-check.mjs`, `logs/validator.log` |
| i18n lint | PASS 기록, exit 0 | `logs/i18n-lint.log` |
| i18n parity | PASS 기록, 번역 baseline 출력 포함 | `logs/i18n-parity.log` |
| sync-check-groups | PASS with warnings, 80 passed / 6 warned / 0 failed | `logs/sync-groups.log` |
| strict sync-check | FAIL, 92 passed / 2 failed | `logs/sync-check-explicit-python.log` |
| 정규 pytest 대상 3개 | BLOCKED, pytest 부재, exit 1 | `logs/python-focused.log` |
| RPC handler import와 전체 JSON-RPC 호출 | BLOCKED, Bio 부재, exit 1 | `logs/rpc-import.log` |
| strict 프런트엔드 Vitest 대상 6개 | BLOCKED, Vitest 부재, exit 1 | `logs/strict-six.log` |
| 전체 TypeScript 검사 | BLOCKED, TypeScript 부재, exit 1 | `logs/typecheck.log` |
| generated-model 일치 검사 | BLOCKED, json2ts 실행 실패, exit 1 | `logs/models-explicit-python.log` |

`sync-check-groups` 경고 6건은 로그에 남은 HEAD의 일부 그룹 파일 변경 경고다. `sync-check`의 실패 두 건은 `resources/NOTICE.md` 부재와 generated-model 검사 실패다. 게시 기준 루트 `AGENTS.md`는 NOTICE.md가 `scripts/build-notice.mjs`로 릴리스 빌드 때 생성되는 gitignore 대상임을 설명한다. 새 전체 checkout의 부재를 부분 수집 오류나 PR #14 신규 결함으로 집계하지 않는다. json2ts 부재는 generated-model 검사를 차단한다. 원래 92 PASS / 2 FAIL 기록을 그대로 유지하며 전체 gate 통과로 바꾸지 않는다. 당시 빌드와 pre-push wrapper는 실행하지 않았다.

## 합성 검사에서 보존된 관찰

아래 내용은 `synthetic_checks.py`의 단언과 `synthetic-results.json`의 기록을 대조해 재구성했다.

1. pLDDT 49.99는 제외되고 50은 포함된다. 저신뢰 후보는 FPS 시작점과 비교용 Top-N에서 제외된다. 모두 저신뢰인 입력은 `Strict spatial count 1 exceeds 0 eligible unique sites`로 거부되며 적격 좌표 2개에 count 3도 거부된다.
2. 비유한 좌표는 `missing_or_nonfinite_coordinate`로 제외된다. 좌표가 전부 없으면 요청 count를 충족하지 못한다. CA 레코드 누락으로 잔기 번호가 불연속인 PDB는 거부된다.
3. AlphaFold 입력의 빈 pLDDT, -1, 101, NaN, inf는 거부된다. 실험 구조 TITLE의 B-factor는 pLDDT 필터로 사용하지 않으며 confidence는 `unavailable`로 기록된다.
4. 구조 `MACDE`와 reference `ACDE`는 입력 1..4를 구조 2..5에 대응시킨다. WT 잔기 불일치, 범위 초과, 다중 치환과 모호한 반복 reference는 거부된다.
5. raw Top-N은 적격 variant 풀에서 budget/cap 정책 적용 전에 계산된다. 합성 예의 raw Top-N은 A2C/A2D이고 대표 Top-N은 A2C/A3C다. 선택은 A2C/A5C이며 asc/desc 모두 `score_gap_to_top_n=1.5`, 선택 집합의 `coverage_mean_distance=0.5`를 기록한다. raw Top-N의 coverage 값은 5.5다.
6. distinct-variant 모드의 5개 site, 95개 variant 입력에서 count 95는 허용되고 96은 거부된다. site cap 1에서는 capacity 5이며 count 6은 거부된다. site 수와 variant 수를 구분한다.
7. count 0, -1, True, 1.5는 거부된다. 실제 CSV 로더는 저신뢰 A2G/C3G를 `pool_variants`에 보존하고 D4G/E5G를 선택한다. 시작 위치 생략 1건과 중복 생략 1건은 `fixtures/csv-result.json`에 기록되어 있다.
8. `annotation_status`의 Pydantic Literal과 TS validator 허용값은 `error`, `no_matching_features`, `present`로 일치한 기록이다.
9. `validator-check.mjs`는 CSV 반환값을 허용하고 threshold 49, 잘못된 제외 개수, 이전 universe와 누락된 secondary baseline을 거부하는 5건을 담는다. Node의 TypeScript 실행과 확장자 resolve hook을 사용한 검사이며 tsc나 React/Vitest 검사를 대신하지 않는다.

## 공개 구조 검사 기록

`public_checks.py`는 공개 좌표에 위치 기반 합성 점수를 부여했다. assay 벤치마크가 아니다. `public-results.json`과 `logs/public.log`의 기존 기록은 다음과 같다.

| 공개 구조 | 잔기 수 | pLDDT < 50 잔기 수 | 제외 variant 수 | 선택 수 |
|---|---:|---:|---:|---:|
| AF-Q9AR86-F1-model_v6.pdb | 595 | 52 | 51 | 24 |
| AF-P42212-F1-model_v6.pdb | 238 | 0 | 0 | 24 |

첫 구조는 위치 1을 합성 후보에서 제외하므로 저신뢰 잔기 수와 제외 variant 수가 다르다. 스크립트는 선택 위치의 pLDDT가 모두 50 이상인지 단언한다. 기존 JSON은 두 실행을 PASS로 기록한다.

원본 PDB는 게시물에 포함되지 않는다. 출처는 AlphaFold DB이며 URL과 콘텐츠 SHA256은 `public-results.json`에 보존되어 있다.

- Q9AR86: `59e17a5ebc8bd204ea150a7887edc5b76f17e5c289fdafd935f9c1fe270f08c5`
- P42212: `abfe2191b8474977143b60b866077b97526fa71c9d3c657304b348e21397323f`

## 차단·생략과 해석 한계

- **BLOCKED_DEPENDENCY:** pytest, Biopython, Vitest, TypeScript, json2ts 부재로 정규 회귀 전체, 전체 RPC, React store/component 런타임, 전체 타입과 generated-model 검사가 미완료다. 당시 의존성을 설치하지 않았다.
- **FAIL_GENERATED_RESOURCE:** NOTICE.md 부재에 따른 strict sync-check 실패는 위 표에 그대로 남긴다.
- **SKIP_LOCAL_RECORDING:** verify-kuma MOCK_MODE가 사용하는 `scripts/real-data.json`과 `scripts/mame-real-data.json`의 로컬 녹화 자료를 공개 checkout에서 실행하지 않았다. React/native UI와 drag-and-drop은 확인하지 않았다.
- **SKIP_SCOPE:** 18회 assay 벤치, construct 경로, Windows Tauri 실행·완료 검증은 수행하지 않았다.
- **NETWORK:** 원래 보고서는 Git schannel의 `SEC_E_NO_CREDENTIALS` 이후 공개 읽기 명령에 `-c http.sslBackend=openssl`을 사용했다고 기록한다. 최종 원격 조회 로그에 해당 옵션이 남아 있다. 공개 AlphaFold 다운로드는 당시 성공 기록이 있으므로 NETWORK SKIP으로 바꾸지 않는다.
- **PRIVATE:** 공개 저장소와 공개 AlphaFold 자료만 대상으로 삼았다. 비공개 자료를 추정 생성하지 않았다.

초기 실패도 보존한다. `logs/synthetic-attempt1.log`는 cp949 디코딩 오류와 26건 중 1건 실패를 기록한다. `logs/validator-attempt1.log`는 validator export 접근 오류를 기록한다. 후속 로그의 성공으로 초기 실패 로그를 덮어쓰지 않는다. 원문에 남은 초기 `ipc.strictSpatial.test.ts` 경로는 최종 `logs/strict-six.log`에서 `inputSlice.helpers.test.ts`로 대체되어 있다. Vitest 부재 때문에 테스트 본문 실행에는 도달하지 못했다.

## 게시와 이번 수정의 경계

PR #15는 기존 검토 자료 27개를 보존하는 문서 PR이다. 개인 경로는 로그에서 `<local>`로 치환되었다. source ZIP, PDB 원문, 토큰, Library 식별자와 운영 데이터는 포함하지 않았다.

PR #15 본문은 게시 단계에서 파일 범위·크기, 개인 경로·비밀 패턴, JSON 파싱과 Python 구문만 새로 확인했다고 명시한다. 원격 PR/head와 해당 head의 CI는 게시 후 조회 대상으로 기록했으며 원래 제품 검사 PASS와 별개다. 이번 수정도 제품 검사를 재실행하지 않는다. 현재 문서의 UTF-8/U+FFFD 검사와 기존 증거의 무변경·구문 확인만 수행한다.
