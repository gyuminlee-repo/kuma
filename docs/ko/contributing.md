# 기여

## 이슈 제보

[이슈 트래커](https://github.com/gyuminlee-repo/kuma/issues) 사용. 포함할 정보:
- OS + kuma 버전 (Help → About 또는 installer 파일명)
- 재현 단계
- sidecar 크래시 관련 시 `~/.kuma/crash.log` 내용 (이전 설치는 `~/.kuro/crash.log`)
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

kuma 배포 패키지에는 Rust·Node·Python 의존성의 라이선스 본문을 담은 `NOTICE.md`
파일이 포함된다.

이 파일은 태그 기반 빌드(`.github/workflows/build.yml`)에서 자동 생성되며
저장소에 커밋되지 않는다. 사용 도구는 다음과 같다:

| 레이어 | 도구 | 출력 |
|---|---|---|
| Rust | `cargo-about` (`src-tauri/about.hbs` 템플릿) | `NOTICE-rust.md` |
| Node | `pnpm licenses list --json --prod` + `scripts/collect-node-licenses.mjs` | `NOTICE-node.md` |
| Python | `pip-licenses --format=markdown` | `NOTICE-python.md` |

`scripts/build-notice.mjs`가 세 파일을 `NOTICE.md`로 합치고
`src-tauri/resources/NOTICE.md`로 복사해 Tauri 번들에 포함시킨다.

로컬에서 재생성하려면 (Python + Node 설치 완료 후):

```bash
# Rust
cd src-tauri && cargo about generate -m Cargo.toml about.hbs > ../NOTICE-rust.md && cd ..

# Node
pnpm licenses list --json --prod > pnpm-licenses.json
node scripts/collect-node-licenses.mjs pnpm-licenses.json NOTICE-node.md

# Python (kuma venv 내)
pip install pip-licenses
pip-licenses --format=markdown --output-file NOTICE-python.md \
  --packages primer3-py biopython openpyxl pydantic pandas python-calamine pyinstaller

# 병합
node scripts/build-notice.mjs
```

세 파일 중 하나라도 없으면 `build-notice.mjs`가 exit 1로 종료된다
(silent skip 비활성화).

## 라이선스

MIT — [LICENSE](https://github.com/gyuminlee-repo/kuma/blob/main/LICENSE) 참고.
