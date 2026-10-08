# 빌드 버전 표기 (3-segment vs 4-segment)

## 정책

KUMA 는 두 가지 버전 표기를 병용한다.

| 위치 | 형식 | 예시 |
|---|---|---|
| `package.json` / `tauri.conf.json` / `Cargo.toml` | 3-segment SemVer `A.BB.CC` | `0.9.2` |
| git commit message / git tag | 4-segment commit ID `vA.BB.CC.DD` | `v0.9.2.21` |

3-segment 는 SemVer 호환 (Tauri/Cargo 요구). 4-segment 의 `DD` 는 patch series 내 sequential commit 번호.

## 증분 규칙

- `DD` — 버그/오타 (기본)
- `CC` — 기능/리팩토링 (DD=00 reset)
- `BB` — 신규 기능/아키텍처 (CC=00, DD=00 reset)
- `A` — 전면 재설계

## 3-way version sync

`pnpm run sync:check` 가 다음 세 파일의 SemVer 일치를 검증한다:

- `package.json`
- `src-tauri/tauri.conf.json`
- `src-tauri/Cargo.toml`

drift 발견 시 release 차단.

## Release

`/release` 스킬이 3개 파일 동시 bump → tag `vA.BB.CC.DD` 생성. tag 의 `DD` 는 release commit 만 의미하며 SemVer 와 다르다.

## 구현 상태 (v0.9.9.2+)

`vite.config.ts` 의 `getAppVersion()` 함수가 빌드 시 `git describe --tags --always` 결과에서 정규식 `^v?(\d+\.\d+\.\d+\.\d+)` 로 4-part 버전을 추출하여 `__APP_VERSION__` 상수에 주입한다. git 이 없거나 4-part tag 가 없으면 `pkg.version` (3-part) 로 fallback.

UI 표시 위치:

- `src/components/layout/SharedAboutDialog.tsx`
- `src/components/dialogs/WhatsNewDialog.tsx`
