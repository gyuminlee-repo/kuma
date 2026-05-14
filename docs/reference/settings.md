# Settings Dialog

`Ctrl+,` / `Cmd+,` 로 열린다 (v0.7.0.0 phase 3 full-stack).

## 섹션

### Theme

| 옵션 | 값 |
|---|---|
| `theme.mode` | `light` / `dark` / `system` |
| `theme.density` | `comfortable` / `compact` |

`localStorage` 유지. v0.7.0.1 에서 `bundle.theme undefined` guard 추가 (upgrade 시 기존 값 보존).

### Network

| 옵션 | 의미 |
|---|---|
| `network.allowUniprot` | UniProt BLAST 호출 허용 |
| `network.allowAlphafold` | AlphaFold Cα fetch 허용 |
| `network.allowInterpro` | InterPro domain fetch 허용 |
| `network.proxy` | HTTP proxy URL (선택) |

### Sidecar

| 옵션 | 의미 |
|---|---|
| `sidecar.kuroPath` | custom binary 경로 (dev) |
| `sidecar.mamePath` | custom binary 경로 (dev) |
| `sidecar.startupTimeout` | spawn timeout ms |
| `sidecar.healthCheckInterval` | health ping 주기 |

### Telemetry

| 옵션 | 의미 |
|---|---|
| `telemetry.enabled` | 익명 사용 통계 전송 (default off) |

## 저장 위치

`~/.kuma/settings.json` (OS 별 config dir). 즉시 반영.
