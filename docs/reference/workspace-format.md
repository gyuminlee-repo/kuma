# Workspace 포맷 (`.kuro.json` / `workspace.kuro.json`)

KURO workspace 의 직렬화 포맷. legacy `.kuro.json` 과 신규 `design/workspace.kuro.json` 는 동일 schema.

## 최상위 구조

```json
{
  "schema": 1,
  "kuro_version": "0.9.2.21",
  "sequence": {
    "name": "pET_target",
    "path": "fixtures/pet_target.gb",
    "cds_start": 121,
    "cds_end": 850,
    "organism": "ecoli"
  },
  "mutations": {
    "mode": "evolvepro",
    "csv_path": "fixtures/df_test.csv",
    "selection": {
      "topN": 95,
      "positionDiversity": true,
      "paretoDiversity": true,
      "domainDiversity": false
    }
  },
  "parameters": {
    "polymerase": "Q5",
    "codonStrategy": "min_changes",
    "tmFwd": 62.0,
    "tmRev": 58.0,
    "tmOverlap": 42.0,
    "tmTolerance": 3.0,
    "gcMin": 0.40,
    "gcMax": 0.60
  },
  "result": { ... }
}
```

## 마이그레이션

- legacy `.kuro.json` 에 `schema` 필드 없으면 schema 0 으로 가정 → loader 가 0→1 변환.
- 향후 schema bump 시 `bin/migrate-workspace.py` 를 통해 batch 변환.

## node:fs 의존성 제거 (v0.9.1.2)

workspace lib 는 `node:fs/path/crypto` 를 사용하지 않고 Tauri `plugin-fs` + Web Crypto API 로 동작한다. WebView 단독 환경에서도 read/write 가능.
