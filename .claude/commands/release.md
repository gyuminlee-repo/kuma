---
description: "릴리스 태그 생성 + 빌드 트리거. /push 후 빌드/릴리스가 필요할 때 사용."
---
인자: $ARGUMENTS

아래 절차를 순서대로 실행한다.

## 1단계: 현재 상태 확인

다음 명령을 병렬로 실행한다:
- `git log --oneline -5` — 최근 커밋 확인
- `git tag --sort=-v:refname | head -10` — 기존 태그 확인
- `git status -s` — 커밋되지 않은 변경 확인

커밋되지 않은 변경이 있으면 **먼저 `/push`를 실행하라**고 안내하고 종료한다.

## 2단계: 버전 결정

`$ARGUMENTS` 값에 따라 분기한다:

| 인자 패턴 | 버전 결정 |
|-----------|----------|
| 빈 값 | 최근 커밋의 `vX.X.X` 패턴을 사용. 없으면 `v0.1.0` |
| `vX.X.X` 패턴 | 지정된 버전 사용 |
| `major` | 메이저 +1 (예: v0.2.3 → v1.0.0) |
| `minor` | 마이너 +1 (예: v0.2.3 → v0.3.0) |
| `patch` | 패치 +1 (예: v0.2.3 → v0.2.4) |

이미 동일한 태그가 존재하면 사용자에게 알리고 종료한다.

## 3단계: 소스 파일 버전 동기화

태그 버전(v 접두사 제외)을 아래 파일에 반영한다. 파일이 존재하는 경우에만 수정.

1. `package.json` — `"version": "X.X.X"`
2. `src-tauri/tauri.conf.json` — `"version": "X.X.X"`
3. `src-tauri/Cargo.toml` — `version = "X.X.X"`

변경된 파일이 있으면 커밋한다:
```bash
git add package.json src-tauri/tauri.conf.json src-tauri/Cargo.toml
git commit -m "chore: bump version to X.X.X"
```

## 4단계: 태그 생성 및 푸시

```bash
git tag <버전>
git push origin main <버전>
```

> main과 태그를 함께 푸시하여 버전 커밋이 빌드에 포함되도록 한다.

## 5단계: 결과 요약

```
🏷️ 릴리스 태그 생성 완료
- 태그: vX.X.X
- 커밋: <short hash> <message>
- 버전 동기화: package.json, tauri.conf.json, Cargo.toml
- 빌드: GitHub Actions Build & Release 워크플로우 트리거됨
- 확인: https://github.com/<owner>/<repo>/actions
```
