# 사이드카 바이너리

KUMA 의 무거운 계산(서열 파싱, primer3, mappy, pandas, openpyxl)은 두 개의 Python 사이드카 프로세스에서 수행된다.

| 사이드카 | 담당 |
|---|---|
| `kuro-sidecar` | KURO primer design, EVOLVEpro CSV 파싱, plate map export |
| `mame-sidecar` | MAME consensus 정렬, verdict 산출, MAME package 생성 |

릴리스 번들에는 PyInstaller 로 단일 실행파일로 묶여 포함된다. Tauri 셸은 OS 별 binary 를 `${RESOURCE_DIR}/sidecars/` 에서 spawn 한다.

## 재빌드

소스에서 사이드카 코드를 수정했을 때:

```bash
pnpm run sidecar:build
```

내부적으로 `python-core/sidecar_kuro/`, `python-core/sidecar_mame/` 두 패키지를 PyInstaller 로 다시 묶는다.

## `-32601 Method not found` 발생 시

UI 또는 백엔드에서 새 RPC 메소드를 추가했는데 사이드카 바이너리가 구버전인 경우 발생한다. 해결:

```bash
pnpm run sidecar:build
```

이후 KUMA 재실행. 자세한 절차는 [트러블슈팅 → Sidecar Method not found](../troubleshooting/sidecar-method-not-found.md).

## 해시 매니페스트 (v0.9.9.2+)

`pnpm run sidecar:build` 후 반드시 같은 플랫폼 머신에서 hash 갱신을 commit 한다.

```bash
pnpm run sidecar:build         # PyInstaller 로 platform binary 생성
pnpm run sidecar:hash          # src-tauri/sidecar-hashes.json merge mode 갱신
git diff src-tauri/sidecar-hashes.json
git add src-tauri/sidecar-hashes.json && git commit -m "vX.X.X: refresh <platform> sidecar hashes"
```

`sidecar-hash.mjs` 는 merge mode 로 동작한다. 본 머신 플랫폼의 triple-suffixed 키만 갱신, 타 플랫폼 키는 보존. 따라서 macOS/Windows/Linux 각자에서 hash 를 한 번씩 commit 해야 3 플랫폼 완전 manifest 가 된다.

runtime 검증 (`src-tauri/src/sidecar.rs verify_binary_hash`) 은 triple_key → ext_key 순서로 lookup 하며 매칭 실패 시 fail-fast. base-name fallback 은 제거되었다 (이전 v0.9.7 회귀 방지).
