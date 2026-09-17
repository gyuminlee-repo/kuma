# Workspace 포맷 (`.kuro.json` / `workspace.kuro.json`)

KURO workspace의 현재 직렬화 포맷은 `schema_version: "0.3"`이다. 확장자만으로 호환성을 판단할 수 없으며, 과거 `.kuro.json` 파일은 아래 호환성 제한을 확인해야 한다.

## 최상위 구조

아래는 최상위 필드 구조를 보여주는 축약 예시이며, 그대로 불러올 수 있는 완전한 워크스페이스는 아니다. 전체 필드는 `src/types/models.ts`의 `WorkspaceV3`, 저장 구현은 `src/store/slices/exportSlice.ts`의 `getWorkspaceSnapshot`이 기준이다.

```json
{
  "schema_version": "0.3",
  "kuma_version": "0.16.63",
  "rounds": [],
  "active_round_id": null,
  "inputs": {},
  "settings": {},
  "results": {},
  "ui": {},
  "cache": {}
}
```

`kuma_version`은 저장 당시 앱 버전으로, 과거 파일에는 없을 수 있다. `inputs`에는 서열 경로와 변이 입력, `settings`에는 설계 설정, `results`에는 설계 결과가 들어간다. `cache`는 선택 사항이다. 원본 서열 파일은 경로에서 다시 읽으므로 워크스페이스와 함께 보존해야 한다.

## 호환성

- 현재 로더는 `schema_version`이 없거나 `0.3`보다 오래된 파일(v1/v2 포함)을 거부한다.
- 자동 레거시 변환이나 일괄 마이그레이션 도구는 제공하지 않는다. 원본을 보존하고 서열과 변이 입력으로 현재 앱에서 새 워크스페이스를 만든다.
- 미래 스키마와의 호환성은 보장하지 않는다.

## node:fs 의존성 제거 (v0.9.1.2)

workspace lib는 `node:fs/path/crypto` 대신 Tauri `plugin-fs` + Web Crypto API를 사용한다. 파일 read/write에는 Tauri 런타임과 허용된 파일시스템 범위가 필요하다.
