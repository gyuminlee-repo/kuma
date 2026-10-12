# H 검토 자료의 재현과 문서 인코딩 검사

이 안내는 손상된 원문을 PR #15 본문, `publication-state.json`, 보존된 스크립트·로그와 읽을 수 있는 원문 토큰에서 **편집 재구성**했다. 깨끗한 원문이 없어 바이트 단위 복원은 아니다. 기존 제품 실행은 2026-10-12의 PR #14 head `0b5fb940ad9effc4eb9b9cb1f4bf96819c574efa`를 대상으로 했으며 base는 `c857b3560f45d2c5fd132b51bfd0920c25043983`이다. 게시 단계와 이번 문서 수정에서는 제품 검사를 재실행하지 않았다.

## 현재 게시 문서 검사

저장소 루트에서 다음 표준 Python 명령을 실행한다. 이 자료 폴더 아래 모든 Markdown을 strict UTF-8로 읽고 U+FFFD가 있으면 exit 1로 실패한다. 정상일 때는 검사 문서 수와 PASS를 출력하고 exit 0으로 끝난다. 문서가 없는 경로도 실패한다. 새 도구 설치는 필요하지 않다.

`logs/models-explicit-python.log`의 U+FFFD 2개는 과거 캡처의 인코딩 손실이다. 원래 바이트를 확보하지 못해 그대로 보존하며 **현재 Markdown 검사에서 이 역사적 로그를 명시적으로 제외한다**. 이 예외는 Markdown의 손상을 허용하지 않는다. 나머지 로그·JSON·스크립트도 이 인코딩 명령의 범위가 아니며 기존 비 Markdown 25개는 수정 전 커밋과 SHA256으로 별도 비교한다.

```sh
python3 - docs/audit/h-pr14-independent-review-20261012 <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
files = sorted(root.rglob("*.md"))
if not files:
    raise SystemExit("FAIL: no Markdown documents")
failed = False
for path in files:
    try:
        content = path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        print(f"FAIL {path}: malformed UTF-8 at byte {error.start}")
        failed = True
        continue
    count = content.count("\ufffd")
    print(f"{'FAIL' if count else 'PASS'} {path}: U+FFFD={count}")
    failed = failed or count > 0
print(f"{len(files)} Markdown documents; {'FAIL' if failed else 'PASS'}")
raise SystemExit(int(failed))
PY
```

회귀 확인은 같은 명령을 수정 전 커밋 `8888a990cca9205c14e64edbe0cd644d2bf6f7fb`에서 추출한 문서 사본에 적용해 실패하는지 확인한 뒤 현재 문서에서 통과하는지 확인한다. 원본 `REVIEW-ko.md`의 U+FFFD 2,911개와 `REPRODUCE.md`의 495개를 탐지해야 한다. 잘못된 UTF-8 바이트도 별도 실패 입력으로 확인한다. 이 검사는 문서 인코딩만 확인하며 문장의 사실성이나 제품 동작을 검증하지 않는다.

## 기존 제품 검사를 다시 실행할 때의 안내

아래는 향후 재현용 절차이며 이번 문서 수정에서는 실행하지 않았다. 기록된 환경은 Python 3.12.14와 Node.js 24.14.0이다. Python 스크립트는 실제 소스를 직접 import하며 dependency stub을 쓰지 않는다. Pydantic과 typing_extensions가 준비되어 있어야 한다. Node 스크립트는 TypeScript 실행과 확장자 resolve hook을 사용하므로 기존 Node 24 환경이 필요하다. 이 안내는 의존성을 자동 설치하지 않는다.

보존 자료를 덮어쓰지 않도록 저장소 루트에서 새 scratch 디렉터리에 사본을 만든다. 스크립트 옆의 `source`가 검토 대상 checkout이어야 한다. 보고서 PR의 main 기반 소스가 PR #14 구현을 포함한다고 가정하지 않는다.

```sh
set -eu
audit_dir="$(git rev-parse --show-toplevel)/docs/audit/h-pr14-independent-review-20261012"
scratch_dir="$(mktemp -d)"
cp -R "$audit_dir/." "$scratch_dir/"
cd "$scratch_dir"
git clone --no-checkout --single-branch --branch feat/strict-spatial-confidence-topn-20261012 https://github.com/gyuminlee-repo/kuma.git source
git -C source checkout --detach 0b5fb940ad9effc4eb9b9cb1f4bf96819c574efa
python3 -X utf8 synthetic_checks.py
node validator-check.mjs
python3 -X utf8 public_checks.py
```

`synthetic_checks.py`는 `fixtures/candidates.csv`, `fixtures/csv-result.json`과 `synthetic-results.json`을 사본 안에 쓴다. validator는 이 CSV 반환 JSON을 사용하므로 합성 검사가 먼저다. 공개 구조 검사는 네트워크를 사용하며 다운로드한 PDB를 `fixtures/`에 저장하고 `public-results.json`을 쓴다. 원본 PDB는 게시 자료에 없으므로 기존 JSON의 URL과 SHA256을 대조해야 한다. 공개 좌표에 합성 점수를 부여한 검사이며 assay 벤치마크가 아니다. 다운로드 실패는 스크립트가 NETWORK SKIP으로 기록하므로 exit 0만으로 두 구조 PASS를 주장하지 않는다.

정규 pytest 대상은 `tests/test_strict_confidence_topn.py`, `tests/test_strict_spatial.py`, `tests/test_strict_variant_budget.py`다. 당시 pytest 부재로 실행하지 못했다. Vitest 대상 6개의 정확한 명령은 `logs/strict-six.log` 첫 줄의 `command` 배열에 있다. 기존 문서의 초기 `ipc.strictSpatial.test.ts` 경로는 최종 기록에서 `inputSlice.helpers.test.ts`로 대체되었다. Vitest 자체가 없어 테스트 본문은 실행되지 않았다.

## 유지해야 할 제한

- 합성 26건, TS validator 5건과 공개 구조 2건의 기존 PASS는 정규 회귀나 전체 승인으로 확대할 수 없다.
- pytest, Biopython, Vitest, TypeScript, json2ts 부재에 따른 BLOCKED를 유지한다. 전체 RPC, React store/component, 전체 타입과 generated-model 검사는 미완료다.
- strict sync-check의 92 PASS / 2 FAIL을 유지한다. NOTICE.md는 릴리스 때 생성되는 gitignore 대상이며 새 전체 checkout의 부재는 PR #14 신규 결함이나 부분 수집 오류가 아니다. 다른 실패는 json2ts 부재다.
- 로컬 녹화 의존 GUI, React/native UI, drag-and-drop은 SKIP_LOCAL_RECORDING이다. 18회 assay 벤치, construct와 Windows Tauri 실행·완료 검증은 SKIP_SCOPE다.
- 로그의 `<local>`은 개인정보 제거용 치환이다. 기존 종료코드와 초기 실패 로그를 보존하며 과거 제품 검사와 게시·문서 수정 검사를 구분한다.

검토 범위와 근거별 해석은 [REVIEW-ko.md](REVIEW-ko.md)에 있다.
