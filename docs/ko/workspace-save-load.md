# 워크스페이스 저장·불러오기

세션 전체를 영속화 — 서열, 변이, 파라미터, 설계 결과, UI 상태.

## 파일 형식

`*.kuro.json` — `version` 필드 (v1 또는 v2)가 포함된 plain JSON.

## 저장

File 메뉴 → *Save Workspace*. 기본 파일명 `YYMMDD_<gene>_workspace.kuro.json`.

## 불러오기

File 메뉴 → *Load Workspace*. KURO가 복원:

- 로드된 서열 및 선택 유전자
- 변이 텍스트 / CSV 경로
- 모든 파라미터 값
- 설계 결과 및 플레이트 매핑
- UniProt accession (구조는 필요 시 재다운로드)

## 호환성

v1 워크스페이스는 v2+ 클라이언트에서 로드 가능; v2는 하위 호환 유지.

## 포함 안 되는 항목

커스텀 폴리머레이즈 프로파일은 `~/.kuro/custom_polymerases.json`에 별도 저장 — 워크스페이스와 독립.

*스텁 — 저장·불러오기 스크린샷 추가 예정.*
