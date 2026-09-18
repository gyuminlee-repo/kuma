# 기여

## 이슈 제보

[이슈 트래커](https://github.com/gyuminlee-repo/kuma/issues) 사용. 포함할 정보:
- OS + kuma 버전 (Help → About 또는 installer 파일명)
- 재현 단계
- sidecar 크래시 관련 시 `~/.kuma/kuro/crash.log` 내용 (이전 설치는 `~/.kuro/crash.log`)
- 가능하면 샘플 서열 / CSV (최소 재현 셋)

## 개발 환경

Linux 빌드는 `cargo check`, `pnpm tauri dev`, `pnpm run build:all` 실행 전에
Tauri/WebKitGTK 개발 패키지가 필요하다:

```bash
sudo apt-get update
sudo apt-get install -y \
  libwebkit2gtk-4.1-dev \
  libjavascriptcoregtk-4.1-dev \
  libsoup-3.0-dev \
  libappindicator3-dev \
  librsvg2-dev \
  patchelf \
  libgtk-3-dev
```

Windows 타겟 빌드는 Node 의존성 설치와 Tauri 패키징을 WSL이 아니라 Windows
네이티브 터미널에서 실행한다.

```bash
git clone https://github.com/gyuminlee-repo/kuma.git
cd kuma
pip install -e '.[build]'
pnpm install
pnpm run sidecar:build
pnpm tauri dev
```

테스트:
```bash
python -m pytest tests/ -v
npx tsc --noEmit
cd src-tauri && cargo check
```

## 코드 스타일

- TypeScript: `as any` 금지, `@ts-ignore` 금지
- Python: RPC 경계 검증은 Pydantic, `kuro/` 라이브러리는 순수 유지 (Tauri import 금지)
- 커밋: `vX.Y.Z: summary in English`

## PR 체크리스트

1. 테스트 통과 (`pytest`, `tsc`, `cargo check`)
2. `UPDATE-NOTES.md` / `UPDATE-NOTES.ko.md` 업데이트
3. UI 변경 시 스크린샷 재생성 (`pnpm run capture-guide`)
4. 신규 기능은 Wiki 업데이트 (이 repo의 `.wiki.git`)

## 서드파티 라이선스 수집

배포 빌드는 변경하지 않은 프로젝트 LICENSE, Rust 본문, 실제 설치된 Node
production 의존성, Python 런타임 전이 의존성과 별도 표시한 패키징 의존성,
바이너리용 `NOTICE-bundled.md`를 합쳐 `NOTICE.md`를 생성한다.
자동 생성한 고지문은 저장소에 커밋하지 않는다.

| 레이어 | 도구 | 출력 |
|---|---|---|
| Rust | `cargo-about`와 `src-tauri/about.hbs` | `NOTICE-rust.md` |
| Node | pnpm production 목록 + `scripts/collect-node-licenses.mjs` | `NOTICE-node.md`와 `.json` |
| Python | `scripts/collect-python-licenses.py --include-build` | `NOTICE-python.md`와 `.json` |

Node 수집기는 SPDX 이름뿐 아니라 패키지의 실제 고지 본문을 읽는다.
Python 수집기는 pyproject.toml의 선언에서 시작해 설치된 전이 의존성,
플랫폼 조건과 요청된 extra를 따라간다. 별도의 패키지 이름 목록 때문에
certifi나 새 전이 의존성이 조용히 빠지지 않도록 한다.

Python build 의존성과 Node 의존성을 설치한 뒤 실행한다:

```bash
# Rust
cd src-tauri && cargo about generate -m Cargo.toml about.hbs > ../NOTICE-rust.md && cd ..
# Node
pnpm licenses list --json --prod > pnpm-licenses.json
node scripts/collect-node-licenses.mjs pnpm-licenses.json NOTICE-node.md
# Python
python scripts/collect-python-licenses.py --include-build
# 병합하고 src-tauri/resources/NOTICE.md에 복사
node scripts/build-notice.mjs
# 회귀 테스트
python -m pytest tests/scripts/test_license_notices.py -q
```

근거 누락이나 빈 내용은 수집·병합 실패로 처리한다. License evidence CI는
세 운영체제에 설치한 Node·Python 패키지에서 실제 수집을 실행한다.
수집 성공은 호환성·상용화 승인이 아니다. 소스 제공, 네이티브 런타임, 자산,
데이터, 외부 약관과 권리자 허가는 [배포 검토표](license-compliance.md)를 따른다.

## 라이선스

GNU GPL version 2 — [LICENSE](../../LICENSE) 참고. 기존 MIT 오표기를
바로잡는 것이며 루트 라이선스의 허락 범위나 서드파티 조건은 바꾸지 않는다.
