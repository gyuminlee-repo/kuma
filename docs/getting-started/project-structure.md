# 프로젝트 구조

KUMA의 모든 데이터는 `projects root` 폴더 아래에 프로젝트 단위로 저장된다.

```
<projects_root>/
└── Sample_42/
    ├── kuma.project.json            # 프로젝트 메타데이터 (schema v1)
    ├── design/
    │   ├── workspace.kuro.json      # KURO workspace (legacy .kuro.json 호환)
    │   └── expected_mutations.xlsx  # __kuma_meta__ 숨김 시트 포함
    └── analysis/
        ├── consensus/               # MAME-generated consensus FASTA/output
        └── verdict.xlsx             # MAME 출력
```

## 숨김 메타 시트 `__kuma_meta__`

KURO에서 export 된 `expected_mutations.xlsx`에는 `__kuma_meta__` 라는 숨김 시트가 포함된다. MAME가 이 시트의 `project_id`, `kuro_version`, `cds_start`, `organism` 을 읽어 현재 프로젝트와 자동 매칭한다. 다른 프로젝트의 expected 시트를 잘못 드롭하면 MAME가 mismatch 경고를 띄운다.

## Stage 자동 추론

`kuma.project.json` 의 `stage` 필드는 파일 존재 여부로 자동 산출된다.

| stage | 조건 |
|---|---|
| `draft` | `design/workspace.kuro.json` 만 존재 |
| `design_complete` | `design/expected_mutations.xlsx` 생성됨 |
| `analyzing` | `analysis/consensus/` 에 FASTA 1개 이상 |
| `done` | `analysis/verdict.xlsx` 생성됨 |

## Scratch 모드

프로젝트 폴더를 만들지 않고 단일 `.kuro.json` 만 열어 작업하는 legacy 호환 모드도 지원한다. File → Open Workspace.
