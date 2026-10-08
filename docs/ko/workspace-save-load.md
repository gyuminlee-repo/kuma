# 워크스페이스 저장·불러오기

세션 전체를 영속화 — 서열, 변이, 파라미터, 설계 결과, UI 상태.

## 파일 형식

`*.kuro.json` — `schema_version: "0.3"`이 포함된 plain JSON. 별도 `kuma_version` 필드는 저장한 앱 버전을 기록함.

## 저장

File 메뉴 → *Save Workspace*. 기본 파일명 `YYMMDD_<gene>_workspace.kuro.json`.

## 불러오기

File 메뉴 → *Load Workspace*. Kuro가 복원:

- 로드된 서열 및 선택 유전자
- 변이 텍스트 / CSV 경로
- 모든 파라미터 값
- 설계 결과 및 플레이트 매핑
- UniProt accession (구조는 필요 시 재다운로드)

## 호환성

현재 로더는 `schema_version`이 없거나 `0.3`보다 오래된 워크스페이스(v1/v2 포함)를 거부함. 자동 레거시 마이그레이션이나 일괄 변환 도구는 제공하지 않음. 원본 파일을 보존하고 현재 앱에서 서열과 변이 입력으로 워크스페이스를 다시 생성해야 함. [포맷 참조](../reference/workspace-format.md).

## 포함 안 되는 항목

커스텀 폴리머레이즈 프로파일은 `~/.kuma/kuro/custom_polymerases.json`에 별도 저장 — 워크스페이스와 독립.

*스텁 — 저장·불러오기 스크린샷 추가 예정.*
