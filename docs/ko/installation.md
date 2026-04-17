# 설치

KURO는 플랫폼별 단일 데스크톱 installer로 배포. 각 [릴리스](https://github.com/gyuminlee-repo/KURO/releases) 첨부 파일에서 다운로드.

## Windows
- `KURO_<version>_x64-setup.exe` 또는 `.msi` 다운로드
- installer 실행, SmartScreen 경고 허용 (코드 서명 예정)
- 시작 메뉴에서 실행

## macOS
- `KURO_<version>_aarch64.dmg` 다운로드
- DMG 열고 KURO.app을 Applications로 드래그
- 첫 실행: 우클릭 → 열기로 Gatekeeper 우회

## Linux (Debian/Ubuntu)
- `kuro_<version>_amd64.deb` 다운로드
- `sudo apt install ./kuro_<version>_amd64.deb`

## Linux (AppImage)
- `kuro_<version>_amd64.AppImage` 다운로드
- `chmod +x kuro_<version>_amd64.AppImage` 후 실행

## 최초 실행

Python sidecar가 자동 기동. 상태 표시줄에 **Ready** 표시까지 대기. 처음 실행 시 방화벽 프롬프트가 뜨면 허용 — UniProt / BLAST / AlphaFold 조회용.

*스텁 — 스크린샷 추가 예정.*
