# Sidecar `-32601 Method not found`

## 증상

```
JSON-RPC error: -32601 Method not found: generate_mame_package
```

또는 KURO 쪽:

```
JSON-RPC error: -32601 Method not found: load_evolvepro_csv
```

## 원인

릴리스 번들의 PyInstaller 사이드카 binary 가 frontend/python 소스보다 구버전이다. dispatcher `_METHODS` 등록 후 사이드카를 재빌드하지 않은 상태.

## 해결

```bash
pnpm run sidecar:build
```

이후 KUMA 재실행.

## 친화 메시지 (v0.9.2.01+)

frontend 가 `-32601` 을 감지하면 raw 에러 대신 다음 메시지로 변환한다.

> "MAME 사이드카가 구버전입니다. `pnpm run sidecar:build` 후 재시도하세요."

i18n key: `errors.sidecar.methodNotFound`.

## 사전 검증

```bash
python -c "from sidecar_mame.dispatcher import _METHODS; print('generate_mame_package' in _METHODS)"
```

`True` 면 source 는 정상. binary 만 stale 한 경우다.

## 회귀 방지

`cross-layer-sync` group `mame-dispatcher` 가 `sidecar_mame.dispatcher._METHODS` ↔ `src/lib/ipc-mame/*` registry drift 를 감지한다. CI 에서 사이드카 binary freshness 도 함께 체크.
