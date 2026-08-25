# Settings Dialog

`Ctrl+,` / `Cmd+,` 로 열린다.

세 개 탭이다. General, Network, Sidecar. Telemetry 탭은 v0.16.37 에서 없앴다. 크래시 로그 자동 전송과 익명 사용 통계 두 토글이 있었으나 읽는 곳이 없었다. 헌장 §10 [필수] 가 외부 송신 0건을 릴리스 차단 요건으로 두므로 켤 수도 없는 항목이었다. 진단은 **실행 → 진단 번들 생성** 이 만드는 로컬 zip 으로만 나간다(헌장 §16).

변경은 즉시 반영되고 0.5초 디바운스로 자동 저장된다. Apply 버튼이 없다.

## General

| 항목 | 저장 위치 | 비고 |
|---|---|---|
| 테마 | `localStorage` + 번들 `theme` | `light` / `dark` / `system`. 번들은 `auto` 로 적고 `mapThemeFromBundle` 이 변환한다 |
| 언어 | i18next `localStorage` | 번들에도 `language` 필드가 있으나 읽는 곳이 없다. 선택은 i18next 쪽이 담당한다 |
| 색각 보조 모드 | `localStorage` (`kuma:kuro:colorblindMode`) | 판정 색에 패턴을 함께 입힌다 |
| 알림 | OS 권한 | 권한 상태 표시와 요청 버튼 |
| 절전 방지 | 실행 중 자동 | 상태 표시만 |
| 데이터 폴더 | 앱 설정 | 현재 경로 표시와 변경 |

## Network

| 필드 | 의미 |
|---|---|
| `network.offline_mode` | 켜면 외부 호출 전부 차단. 진입점 9곳이 이 값을 먼저 본다 |
| `network.consent_uniprot` | UniProt 조회 허용 |
| `network.consent_blast` | EBI 경유 NCBI BLAST 허용. UniProt 검색 안의 2차 단계라 끄면 그 단계만 빠지고 직접 accession 조회는 계속된다 |
| `network.consent_alphafold` | 구조 조회 허용 (AlphaFold, RCSB, ESMFold) |
| `network.consent_interpro` | InterPro·Pfam 도메인 조회 허용 |

네 개 동의 스위치는 기본값이 켜짐이다. 최초 1회 전역 동의 모달이 따로 있다. 이 스위치는 그 위에서 서비스별로 끄는 용도다. v0.16.37 이전에는 저장만 되고 아무것도 차단하지 못했다.

거부 사유는 세 가지를 구분해 표시한다. 오프라인 모드, 해당 서비스가 설정에서 꺼짐, 전역 동의 미완료.

## Sidecar

| 필드 | 의미 |
|---|---|
| `sidecar.persist_on_cancel` | `partial`(기본) 이면 취소해도 이미 만든 프라이머를 유지한다. `discard` 면 전부 버린다 |

동시 실행 수와 취소 대기 시간은 v0.16.37 에서 없앴다. 설계는 돌연변이를 한 건씩 처리하므로 상한을 걸 병렬 풀이 없다(96웰 실측 약 2초). 종료 대기는 헌장 §22 가 5초로, 취소 상한은 §1 이 5초로 고정한다.

## 저장 위치

`$KUMA_PREFERENCES_PATH` 가 있으면 그 경로, 없으면 `~/.kuma/preferences.json`. 임시 파일에 쓰고 `os.replace` 로 바꾸므로 쓰다 죽어도 깨진 파일이 남지 않는다.

구버전이 쓴 파일에 지금 없는 키가 남아 있어도 무시하고 읽는다. 거부하면 나머지 설정까지 기본값으로 되돌아가기 때문이다. 이 동작은 양쪽에 테스트로 고정돼 있다(`tests/sidecar_kuro/test_settings_contract.py`, `src/lib/ipc.bypass.test.ts`).

## 설정을 추가할 때

번들에 필드를 더하면 `tests/sidecar_kuro/test_settings_contract.py` 가 그 필드를 **배선됨** 또는 **미배선** 중 하나로 선언하라고 요구한다. 배선됨이면 동작시키는 파일과 그 파일에 있어야 할 문자열을 함께 적는다. 미배선이면 아무것도 하지 않는 이유를 적는다. 선언 전까지 CI 를 통과하지 못한다.

아직 이행할 수 없는 설정은 `SettingsDialog.tsx` 의 `INACTIVE_SETTINGS` 에 넣고 비활성 상태로 `settings.inactiveHint` 를 함께 띄운다. 값을 저장하면서 아무 동작도 하지 않는 컨트롤을 그대로 두지 않기 위한 장치다.
