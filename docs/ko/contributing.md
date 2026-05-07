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

## 라이선스

MIT — [LICENSE](https://github.com/gyuminlee-repo/kuma/blob/main/LICENSE) 참고.
