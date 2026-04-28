# 설치

kuma는 플랫폼별 단일 데스크톱 installer로 배포. 각 [릴리스](https://github.com/gyuminlee-repo/kuma/releases) 첨부 파일에서 다운로드.

## Windows
- `kuma_<version>_x64-setup.exe` 또는 `.msi` 다운로드
- installer 실행, SmartScreen 경고 허용 (코드 서명 예정)
- 시작 메뉴에서 실행

## macOS
- `kuma_<version>_aarch64.dmg` 다운로드
- DMG 열고 kuma.app을 Applications로 드래그
- 첫 실행: 우클릭 → 열기로 Gatekeeper 우회

## Linux (Debian/Ubuntu)
- `kuma_<version>_amd64.deb` 다운로드
- `sudo apt install ./kuma_<version>_amd64.deb`

## Linux (AppImage)
- `kuma_<version>_amd64.AppImage` 다운로드
- `chmod +x kuma_<version>_amd64.AppImage` 후 실행

## 최초 실행

Python sidecar(kuro, mame)는 첫 탭 활성화 시 lazy 기동. 상태 표시줄에 **Ready** 표시까지 대기. 처음 실행 시 방화벽 프롬프트가 뜨면 허용 — UniProt / BLAST / AlphaFold 조회용.
