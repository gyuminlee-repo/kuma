# KUMA 사용자 가이드

KUMA는 부위 특이적 돌연변이 실험을 위한 데스크톱 앱이다. **KURO**는 Gibson Assembly 템플릿에서 SDM 프라이머 쌍을 일괄 설계한다. **MAME**는 돌아온 Oxford Nanopore 시퀀싱을 읽어 어느 클론에 의도한 변이가 들어갔는지 판정한다.

![Kuro 출력 단계: 설계한 변이 91개의 서열 맵, 프라이머 요약 표, forward 플레이트 맵, 설계 리포트](https://raw.githubusercontent.com/gyuminlee-repo/kuma/main/docs/screenshots/04-design-complete.png)

<small>내장 데모 프로젝트로 띄운 Kuro 출력 단계. 이전 빌드에서 찍은 화면이다.</small>

## 설치

[Releases](https://github.com/gyuminlee-repo/kuma/releases)에서 운영체제에 맞는 설치 파일을 받는다.

| 운영체제 | 파일 |
|---|---|
| Windows (x64) | `kuma_<버전>_x64-setup.exe` |
| macOS (Apple Silicon) | `kuma_<버전>_aarch64.dmg` |
| Linux (x64) | `kuma_<버전>_amd64.AppImage` 또는 `kuma_<버전>_amd64.deb` |

처음 실행하면 프로젝트 폴더를 묻는다(기본 `~/Documents/kuma`). macOS는 첫 실행 때 확인되지 않은 개발자 경고를 띄운다. 넘어가는 두 방법은 [README](https://github.com/gyuminlee-repo/kuma/blob/main/README.ko.md#설치)에 있다.

## 어디서 시작할까

- [KURO 안내](kuro-index.md): 서열 불러오기부터 프라이머 주문서와 장비 이송 파일까지.
- [MAME 안내](mame-index.md): MinKNOW 런 폴더부터 판정과 EVOLVEpro 입력까지.

앱의 도움말 패널이 보여 주는 문서와 같은 문서다. 그래서 가이드와 앱이 같은 버전을 설명한다.
