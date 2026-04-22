# 설정

사용자별 설정은 `~/.kuro/`에 저장.

## `~/.kuro/config.json`

```json
{
  "contact_email": "you@example.com"
}
```

### `contact_email`

EBI BLAST 및 UniProt API 요청용. **UniProt BLAST 검색 필수** — 미설정 시 EBI가 요청 거부하고 gene-name 텍스트 매칭으로 fallback되어 유사도 낮은 후보만 올라옴.

환경변수 `KURO_CONTACT_EMAIL`이 우선.

둘 다 미설정이면 v1.33.6부터 기본값 `kuro-app@example.com`이 사용되어 BLAST는 동작함. EBI ToS 준수 위해 본인 이메일 설정 권장.

## `~/.kuro/custom_polymerases.json`

[커스텀 폴리머레이즈 에디터](custom-polymerase-editor.md)가 자동 관리. 수동 편집도 보존되지만 기본 프로파일 스키마 준수 필요.

## `~/.kuro/crash.log`

최근 50건의 sidecar 예외 기록 (timestamp, method, truncated traceback). `Sidecar process exited` 오류 보고 시 유용.
