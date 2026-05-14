# 설치

## Release 다운로드

[Releases](https://github.com/gyuminlee-repo/kuma/releases) 페이지에서 OS별 인스톨러를 받는다.

| OS | 파일 | 비고 |
|---|---|---|
| Windows | `kuma_X.Y.Z_x64_en-US.msi` | x64 |
| macOS | `kuma_X.Y.Z_universal.dmg` | Intel + Apple Silicon |
| Linux | `kuma_X.Y.Z_amd64.AppImage` | 또는 `.deb` |

## 사이드카 바이너리

릴리스 번들에는 PyInstaller로 패키징된 `kuro-sidecar`, `mame-sidecar` 실행파일이 포함된다. 별도 Python 설치 없이 동작한다. 첫 실행 시 Tauri 셸이 OS에 맞는 사이드카를 spawn 한다.

## 첫 실행

1. 앱 실행 → projects root 선택 dialog 표시.
2. 기본 경로 `~/Documents/kuma` 또는 사용자 지정.
3. New Project → 프로젝트 이름 입력 → KURO 탭으로 진입.

<!-- TODO: insert screenshot of first-run dialog -->

## 개발 모드 (소스에서 빌드)

```bash
pnpm install
pnpm run sidecar:build   # 사이드카 PyInstaller 빌드
pnpm tauri dev
```

자세한 빌드 절차는 repo `README.md` 의 Development 섹션을 참고한다.
