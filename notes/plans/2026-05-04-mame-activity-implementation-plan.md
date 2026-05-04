# MAME Activity Integration — 구현 계획 (5/12 데모)

**목표**: KUMA의 MAME 모듈에 활성 데이터 통합 + Round 엔티티 + 분류기 신호 계산을 5/12 PI 데모까지 구현

**아키텍처**: Round 엔티티가 KURO·MAME 상태를 wrap하는 상위 레이어. 활성 데이터는 `kuma_core/mame/activity/` 신규 모듈로 격리. Strategy 신호는 `kuma_core/strategy/`에 별도 layer. 기존 KURO·MAME 코드는 변경 최소화 (단방향 의존).

**기술 스택**: Python 3.11 (Pydantic, pandas, openpyxl), React 19 + Zustand + TailwindCSS, Tauri v2 (JSON-RPC stdin/stdout)

**스펙**: `notes/specs/2026-05-04-mame-activity-integration.md` (v0.2.6.05) [source: notes/specs/2026-05-04-mame-activity-integration.md]

**Scope**: §1–§12-A의 5/12 IN 항목만. v0.3+ 항목(advisory mode, bootstrap, 사전등록 UI, fully auto, T5/T6 신호)은 후속 계획

**기간**: 8일 (2026-05-04 ~ 2026-05-12). 작업 추정 6.5일 + slack 1.5일

---

## Phase 0 — 데이터 모델 (0.5일)

### Task 0.1: Pydantic 모델 (activity)

**파일**:
- 생성: `kuma_core/mame/activity/__init__.py`
- 생성: `kuma_core/mame/activity/models.py`
- 테스트: `tests/mame/activity/test_models.py`

스펙 §2.2 [source: notes/specs/2026-05-04-mame-activity-integration.md:86-145]

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/mame/activity/test_models.py
from kuma_core.mame.activity.models import (
    ActivityRecord, ActivityTable, MergedRow, PlateConfig, PlateMeta, MergeStats
)
from datetime import datetime

def test_activity_record_required_fields():
    r = ActivityRecord(
        plate_id="P01", well_id="A01", value=1.23,
        replicate_idx=1, is_wt=True, source_file="round1.csv"
    )
    assert r.plate_id == "P01"
    assert r.replicate_idx == 1

def test_merged_row_mutation_source_enum():
    row = MergedRow(
        plate_id="P01", well_id="B03", mutation="F89W",
        mutation_source="kuro_design",
        expected_mutation="F89W", called_mutation="F89W",
        ngs_success=True,
        activity_raw_mean=2.45, activity_raw_sd=0.12,
        activity_replicates=[2.40, 2.50, 2.45], replicate_n=3,
        fold_change=1.99, log2_fc=0.99
    )
    assert row.mutation_source in {"kuro_design", "mame_genotype", "activity_only"}

def test_merge_stats_all_fields():
    s = MergeStats(
        n_total_wells=96, n_with_activity=96, n_with_genotype=90,
        n_ngs_success=88, n_wt=4,
        n_duplicate_warnings=0, n_excluded_from_export=10
    )
    assert s.n_total_wells == 96
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
python -m pytest tests/mame/activity/test_models.py -v
```
예상: FAIL — `ModuleNotFoundError: kuma_core.mame.activity`

- [ ] **Step 3: 최소 구현**

```python
# kuma_core/mame/activity/__init__.py
from kuma_core.mame.activity.models import (
    ActivityRecord, ActivityTable, MergedRow, PlateConfig, PlateMeta, MergeStats
)

# kuma_core/mame/activity/models.py
from typing import Literal
from pydantic import BaseModel

class PlateConfig(BaseModel):
    plate_id: str
    wt_wells: list[str]
    control_wells: list[str] = []

class PlateMeta(BaseModel):
    plates: list[PlateConfig]

class ActivityRecord(BaseModel):
    plate_id: str
    well_id: str
    value: float
    replicate_idx: int = 1
    is_wt: bool
    source_file: str

class ActivityTable(BaseModel):
    records: list[ActivityRecord]
    plate_meta: PlateMeta

class MergedRow(BaseModel):
    plate_id: str
    well_id: str
    mutation: str | None
    mutation_source: Literal["kuro_design", "mame_genotype", "activity_only"]
    expected_mutation: str | None
    called_mutation: str | None
    ngs_success: bool
    activity_raw_mean: float | None
    activity_raw_sd: float | None
    activity_replicates: list[float]
    replicate_n: int
    fold_change: float | None
    log2_fc: float | None

class MergeStats(BaseModel):
    n_total_wells: int
    n_with_activity: int
    n_with_genotype: int
    n_ngs_success: int
    n_wt: int
    n_duplicate_warnings: int
    n_excluded_from_export: int
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/mame/activity/test_models.py -v
```
예상: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add kuma_core/mame/activity/ tests/mame/activity/test_models.py
git commit -m "v0.2.7.00: add activity Pydantic models for MAME integration"
```

### Task 0.2: Round Pydantic 모델

**파일**:
- 생성: `kuma_core/mame/activity/round.py`
- 테스트: `tests/mame/activity/test_round.py`

스펙 §2.1, §2.2 [source: notes/specs/2026-05-04-mame-activity-integration.md:120-145]

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/mame/activity/test_round.py
from kuma_core.mame.activity.round import Round, RoundStatus, RoundErrorInfo
from datetime import datetime

def test_round_status_includes_combinatorial():
    assert RoundStatus.COMBINATORIAL == "combinatorial"
    assert RoundStatus.ERROR == "error"

def test_round_minimal():
    r = Round(
        id="round_1", n=1, created_at=datetime.now(),
        status=RoundStatus.DESIGN,
        plate_meta={"plates": []},
        design={}, genotype={},
        activity=None, merged_table=[]
    )
    assert r.id == "round_1"
    assert r.status == RoundStatus.DESIGN

def test_round_error_info():
    info = RoundErrorInfo(stage="merge", message="WT 없음", occurred_at=datetime.now())
    assert info.stage == "merge"
```

- [ ] **Step 2: 실행 → 실패**: `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# kuma_core/mame/activity/round.py
from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel
from kuma_core.mame.activity.models import PlateMeta, ActivityTable, MergedRow

class RoundStatus(str, Enum):
    DESIGN = "design"
    ORDERED = "ordered"
    NGS_DONE = "ngs_done"
    ACTIVITY_LINKED = "activity_linked"
    EXPORTED = "exported"
    COMBINATORIAL = "combinatorial"
    CLOSED = "closed"
    ERROR = "error"

class RoundErrorInfo(BaseModel):
    stage: Literal["upload", "merge", "export", "handoff"]
    message: str
    occurred_at: datetime

class Round(BaseModel):
    id: str
    n: int
    created_at: datetime
    status: RoundStatus
    error_info: RoundErrorInfo | None = None
    plate_meta: PlateMeta
    design: dict
    genotype: dict
    activity: ActivityTable | None
    merged_table: list[MergedRow]
```

- [ ] **Step 4: 통과 확인** + **Step 5: 커밋** `v0.2.7.01: add Round Pydantic model with COMBINATORIAL status`

### Task 0.3: TypeScript 타입 미러링

**파일**:
- 생성: `src/types/mame/activity.ts`
- 생성: `src/types/round.ts`

[source: notes/specs/2026-05-04-mame-activity-integration.md:147-149]

- [ ] **Step 1: 작성**

```typescript
// src/types/mame/activity.ts
export interface PlateConfig {
  plate_id: string
  wt_wells: string[]
  control_wells: string[]
}

export interface PlateMeta {
  plates: PlateConfig[]
}

export interface ActivityRecord {
  plate_id: string
  well_id: string
  value: number
  replicate_idx: number
  is_wt: boolean
  source_file: string
}

export interface MergedRow {
  plate_id: string
  well_id: string
  mutation: string | null
  mutation_source: "kuro_design" | "mame_genotype" | "activity_only"
  expected_mutation: string | null
  called_mutation: string | null
  ngs_success: boolean
  activity_raw_mean: number | null
  activity_raw_sd: number | null
  activity_replicates: number[]
  replicate_n: number
  fold_change: number | null
  log2_fc: number | null
}

export interface MergeStats {
  n_total_wells: number
  n_with_activity: number
  n_with_genotype: number
  n_ngs_success: number
  n_wt: number
  n_duplicate_warnings: number
  n_excluded_from_export: number
}
```

```typescript
// src/types/round.ts
import type { PlateMeta, MergedRow } from "./mame/activity"

export type RoundStatus =
  | "design" | "ordered" | "ngs_done" | "activity_linked"
  | "exported" | "combinatorial" | "closed" | "error"

export interface RoundErrorInfo {
  stage: "upload" | "merge" | "export" | "handoff"
  message: string
  occurred_at: string
}

export interface Round {
  id: string
  n: number
  created_at: string
  status: RoundStatus
  error_info: RoundErrorInfo | null
  plate_meta: PlateMeta
  design: Record<string, unknown>
  genotype: Record<string, unknown>
  activity: { records: ActivityRecord[]; plate_meta: PlateMeta } | null
  merged_table: MergedRow[]
}
```

- [ ] **Step 2: TypeScript 검사**: `npx tsc --noEmit` → 예상 0 에러
- [ ] **Step 3: 커밋** `v0.2.7.02: TS types mirror activity and Round Pydantic models`

---

## Phase 1 — 백엔드 ingest + normalize + merge (1일)

### Task 1.1: Long-format CSV/Excel ingest

**파일**:
- 생성: `kuma_core/mame/activity/ingest_long_csv.py`
- 테스트: `tests/mame/activity/test_ingest_long_csv.py`

스펙 §3.3 [source: notes/specs/2026-05-04-mame-activity-integration.md:217-226]

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/mame/activity/test_ingest_long_csv.py
import pandas as pd
from pathlib import Path
from kuma_core.mame.activity.ingest_long_csv import ingest_long_csv

def test_ingest_minimal_csv(tmp_path: Path):
    csv = tmp_path / "round1.csv"
    csv.write_text("plate_id,well_id,value,replicate_idx\nP01,A01,1.23,1\nP01,B03,2.45,1\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": ["A01"]})
    assert len(result.records) == 2
    assert result.records[0].is_wt == True
    assert result.records[1].is_wt == False

def test_ingest_invalid_well_id_skipped(tmp_path: Path):
    csv = tmp_path / "bad.csv"
    csv.write_text("plate_id,well_id,value\nP01,XX,1.0\nP01,A01,2.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": ["A01"]})
    assert len(result.records) == 1
    assert result.records[0].well_id == "A01"

def test_ingest_negative_value_skipped(tmp_path: Path):
    csv = tmp_path / "neg.csv"
    csv.write_text("plate_id,well_id,value\nP01,A01,-0.5\nP01,B01,1.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert len(result.records) == 1

def test_ingest_missing_plate_id_rejects(tmp_path: Path):
    csv = tmp_path / "noplate.csv"
    csv.write_text("well_id,value\nA01,1.23\n")
    import pytest
    with pytest.raises(ValueError, match="plate_id"):
        ingest_long_csv(csv, plate_meta_wt_wells={})
```

- [ ] **Step 2: 실행 → 실패**: `ModuleNotFoundError`

- [ ] **Step 3: 최소 구현**

```python
# kuma_core/mame/activity/ingest_long_csv.py
import re
from pathlib import Path
import math
import pandas as pd
from kuma_core.mame.activity.models import ActivityRecord, ActivityTable, PlateConfig, PlateMeta

WELL_RE_96 = re.compile(r"^[A-H](0[1-9]|1[0-2])$")
WELL_RE_384 = re.compile(r"^[A-P](0[1-9]|1[0-9]|2[0-4])$")

def _is_valid_well(well: str) -> bool:
    return bool(WELL_RE_96.match(well) or WELL_RE_384.match(well))

def ingest_long_csv(path: Path, plate_meta_wt_wells: dict[str, list[str]]) -> ActivityTable:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    df.columns = [c.strip().lower() for c in df.columns]
    if "plate_id" not in df.columns:
        raise ValueError("plate_id 컬럼이 필요합니다")
    if "well_id" not in df.columns:
        raise ValueError("well_id 컬럼이 필요합니다")
    if "value" not in df.columns:
        raise ValueError("value 컬럼이 필요합니다")

    if "replicate_idx" not in df.columns:
        df["replicate_idx"] = 1

    records = []
    for _, row in df.iterrows():
        plate_id = str(row["plate_id"]).strip()
        well_id = str(row["well_id"]).strip().upper()
        try:
            value = float(row["value"])
        except (ValueError, TypeError):
            continue
        if math.isnan(value) or value < 0:
            continue
        if not _is_valid_well(well_id):
            continue
        is_wt = well_id in plate_meta_wt_wells.get(plate_id, [])
        records.append(ActivityRecord(
            plate_id=plate_id,
            well_id=well_id,
            value=value,
            replicate_idx=int(row["replicate_idx"]),
            is_wt=is_wt,
            source_file=path.name,
        ))

    plate_meta = PlateMeta(plates=[
        PlateConfig(plate_id=pid, wt_wells=wts)
        for pid, wts in plate_meta_wt_wells.items()
    ])
    return ActivityTable(records=records, plate_meta=plate_meta)
```

- [ ] **Step 4: 통과 확인** + **Step 5: 커밋** `v0.2.7.03: ingest_long_csv parser with validation`

### Task 1.2: Aggregate (replicate mean/sd, mutation-success 필터)

**파일**:
- 생성: `kuma_core/mame/activity/aggregate.py`
- 테스트: `tests/mame/activity/test_aggregate.py`

스펙 §3.4 step 4 [source: notes/specs/2026-05-04-mame-activity-integration.md:243-249]

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/mame/activity/test_aggregate.py
from kuma_core.mame.activity.aggregate import aggregate_replicates

def test_aggregate_three_replicates():
    values = [2.40, 2.50, 2.45]
    mean, sd, n = aggregate_replicates(values)
    assert abs(mean - 2.45) < 1e-6
    assert abs(sd - 0.05) < 0.001
    assert n == 3

def test_aggregate_single_value_no_sd():
    mean, sd, n = aggregate_replicates([1.5])
    assert mean == 1.5
    assert sd is None
    assert n == 1

def test_aggregate_empty():
    mean, sd, n = aggregate_replicates([])
    assert mean is None
    assert sd is None
    assert n == 0
```

- [ ] **Step 2-5**: 표준 사이클

```python
# kuma_core/mame/activity/aggregate.py
import statistics
from typing import Optional

def aggregate_replicates(values: list[float]) -> tuple[Optional[float], Optional[float], int]:
    n = len(values)
    if n == 0:
        return None, None, 0
    mean = sum(values) / n
    sd = statistics.stdev(values) if n > 1 else None
    return mean, sd, n
```

커밋 `v0.2.7.04: aggregate_replicates utility`

### Task 1.3: Normalize (fold-change, log2)

**파일**: 
- 생성: `kuma_core/mame/activity/normalize.py`
- 테스트: `tests/mame/activity/test_normalize.py`

스펙 §3.4 step 5–7 [source: notes/specs/2026-05-04-mame-activity-integration.md:251-258]

- [ ] **Step 1: 실패 테스트**

```python
# tests/mame/activity/test_normalize.py
from kuma_core.mame.activity.normalize import compute_fold_change, compute_log2_fc
import math

def test_fold_change_2x():
    assert abs(compute_fold_change(2.0, 1.0) - 2.0) < 1e-6

def test_fold_change_wt_zero_returns_none():
    assert compute_fold_change(2.0, 0.0) is None

def test_fold_change_none_input():
    assert compute_fold_change(None, 1.0) is None
    assert compute_fold_change(2.0, None) is None

def test_log2_fc():
    assert abs(compute_log2_fc(2.0) - 1.0) < 1e-6
    assert abs(compute_log2_fc(0.5) - (-1.0)) < 1e-6

def test_log2_fc_wt_returns_zero():
    # WT mutation 자체는 log2_fc = 0
    assert compute_log2_fc(1.0, is_wt=True) == 0.0

def test_log2_fc_negative_or_zero_returns_none():
    assert compute_log2_fc(0.0) is None
    assert compute_log2_fc(-1.0) is None
```

- [ ] **Step 3: 구현**

```python
# kuma_core/mame/activity/normalize.py
import math
from typing import Optional

def compute_fold_change(activity_mean: Optional[float], wt_mean: Optional[float]) -> Optional[float]:
    if activity_mean is None or wt_mean is None or wt_mean == 0:
        return None
    return activity_mean / wt_mean

def compute_log2_fc(fold_change: Optional[float], is_wt: bool = False) -> Optional[float]:
    if is_wt:
        return 0.0
    if fold_change is None or fold_change <= 0:
        return None
    return math.log2(fold_change)
```

- [ ] **Step 4-5**: 통과 + 커밋 `v0.2.7.05: normalize fold-change and log2`

### Task 1.4: Join (genotype × activity merge)

**파일**:
- 생성: `kuma_core/mame/activity/join.py`
- 테스트: `tests/mame/activity/test_join.py`

스펙 §2.4, §3.4 [source: notes/specs/2026-05-04-mame-activity-integration.md:151-167, 228-258]

- [ ] **Step 1: 실패 테스트** (가장 큰 테스트, mutation_source 3가지 + ngs_success 정의 + WT 처리)

```python
# tests/mame/activity/test_join.py
from kuma_core.mame.activity.join import merge_activity_with_genotype
from kuma_core.mame.activity.models import ActivityRecord, PlateMeta, PlateConfig

def _make_records(rows):
    return [ActivityRecord(plate_id=p, well_id=w, value=v, replicate_idx=r,
                           is_wt=False, source_file="t.csv")
            for (p, w, v, r) in rows]

def test_kuro_design_match_genotype():
    kuro_design = {("P01", "B03"): "F89W"}
    mame_genotype = {("P01", "B03"): "F89W"}
    activity = _make_records([("P01", "B03", 2.0, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                    replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, stats = merge_activity_with_genotype(kuro_design, mame_genotype, activity, plate_meta)
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.mutation_source == "kuro_design"
    assert rec.ngs_success == True
    assert rec.mutation == "F89W"
    assert abs(rec.fold_change - 2.0) < 1e-6
    assert abs(rec.log2_fc - 1.0) < 1e-6

def test_genotype_disagrees_with_design():
    kuro = {("P01", "B03"): "F89W"}
    mame = {("P01", "B03"): "WT"}
    activity = _make_records([("P01", "B03", 1.0, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                    replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.mutation_source == "mame_genotype"
    assert rec.ngs_success == False
    assert rec.expected_mutation == "F89W"
    assert rec.called_mutation == "WT"

def test_activity_only_well():
    kuro = {}
    mame = {}
    activity = _make_records([("P01", "C05", 1.5, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=[])])
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    rec = rows[0]
    assert rec.mutation_source == "activity_only"
    assert rec.mutation is None
    assert rec.ngs_success == False

def test_replicate_aggregation():
    kuro = {("P01", "B03"): "F89W"}
    mame = {("P01", "B03"): "F89W"}
    activity = _make_records([("P01", "B03", 2.0, 1), ("P01", "B03", 2.5, 2), ("P01", "B03", 2.4, 3)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                    replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.replicate_n == 3
    assert abs(rec.activity_raw_mean - 2.3) < 0.01
    assert rec.activity_raw_sd is not None

def test_stats_counts():
    kuro = {("P01", "A02"): "L70V", ("P01", "B03"): "F89W"}
    mame = {("P01", "A02"): "L70V", ("P01", "B03"): "WT"}  # B03 NGS 실패
    activity = _make_records([("P01", "A02", 1.5, 1), ("P01", "B03", 1.0, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                    replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    assert stats.n_total_wells == 3
    assert stats.n_ngs_success == 1
    assert stats.n_wt == 1
```

- [ ] **Step 3: 구현**

```python
# kuma_core/mame/activity/join.py
import statistics
from collections import defaultdict
from kuma_core.mame.activity.models import (
    ActivityRecord, PlateMeta, MergedRow, MergeStats
)
from kuma_core.mame.activity.aggregate import aggregate_replicates
from kuma_core.mame.activity.normalize import compute_fold_change, compute_log2_fc

def merge_activity_with_genotype(
    kuro_design: dict[tuple[str, str], str],
    mame_genotype: dict[tuple[str, str], str],
    activity_records: list[ActivityRecord],
    plate_meta: PlateMeta,
) -> tuple[list[MergedRow], MergeStats]:

    wt_lookup = {p.plate_id: set(p.wt_wells) for p in plate_meta.plates}

    # Group activity by (plate_id, well_id)
    by_well: dict[tuple[str, str], list[ActivityRecord]] = defaultdict(list)
    seen_keys: set[tuple[str, str, int]] = set()
    n_dup = 0
    for r in activity_records:
        key = (r.plate_id, r.well_id, r.replicate_idx)
        if key in seen_keys:
            n_dup += 1
            continue
        seen_keys.add(key)
        by_well[(r.plate_id, r.well_id)].append(r)

    # WT mean per plate
    wt_means: dict[str, float | None] = {}
    for plate_id, wt_wells in wt_lookup.items():
        wt_values = [r.value for (p, w), recs in by_well.items()
                     for r in recs if p == plate_id and w in wt_wells]
        if wt_values:
            wt_means[plate_id] = sum(wt_values) / len(wt_values)
        else:
            wt_means[plate_id] = None

    # All keys union
    all_keys = set(kuro_design.keys()) | set(mame_genotype.keys()) | set(by_well.keys())

    rows: list[MergedRow] = []
    n_with_activity = 0
    n_with_genotype = 0
    n_ngs_success = 0
    n_wt = 0
    n_excluded = 0

    for (plate_id, well_id) in sorted(all_keys):
        expected = kuro_design.get((plate_id, well_id))
        called = mame_genotype.get((plate_id, well_id))
        is_wt_well = well_id in wt_lookup.get(plate_id, set())

        if is_wt_well:
            mutation = "WT"
            mutation_source = "kuro_design" if expected else "activity_only"
            ngs_success = (called == "WT") if called else (expected == "WT")
        elif expected and (not called or called == expected):
            mutation = expected
            mutation_source = "kuro_design"
            ngs_success = (called == expected)
        elif called:
            mutation = called
            mutation_source = "mame_genotype"
            ngs_success = (expected is not None and called == expected)
        else:
            mutation = None
            mutation_source = "activity_only"
            ngs_success = False

        recs = by_well.get((plate_id, well_id), [])
        replicates = [r.value for r in recs]
        mean, sd, n_rep = aggregate_replicates(replicates)
        wt_m = wt_means.get(plate_id)
        fold_change = compute_fold_change(mean, wt_m)
        log2 = compute_log2_fc(fold_change, is_wt=(mutation == "WT"))

        if recs: n_with_activity += 1
        if called: n_with_genotype += 1
        if ngs_success: n_ngs_success += 1
        if mutation == "WT": n_wt += 1
        if not (ngs_success and mutation != "WT" and log2 is not None):
            n_excluded += 1

        rows.append(MergedRow(
            plate_id=plate_id, well_id=well_id,
            mutation=mutation, mutation_source=mutation_source,
            expected_mutation=expected, called_mutation=called,
            ngs_success=ngs_success,
            activity_raw_mean=mean, activity_raw_sd=sd,
            activity_replicates=replicates, replicate_n=n_rep,
            fold_change=fold_change, log2_fc=log2,
        ))

    stats = MergeStats(
        n_total_wells=len(rows), n_with_activity=n_with_activity,
        n_with_genotype=n_with_genotype, n_ngs_success=n_ngs_success,
        n_wt=n_wt, n_duplicate_warnings=n_dup,
        n_excluded_from_export=n_excluded,
    )
    return rows, stats
```

- [ ] **Step 4-5**: 통과 + 커밋 `v0.2.7.06: merge_activity_with_genotype with mutation_source rules`

### Task 1.5: EVOLVEpro CSV export

**파일**:
- 생성: `kuma_core/mame/activity/export_evolvepro.py`
- 테스트: `tests/mame/activity/test_export_evolvepro.py`

스펙 §3.5 [source: notes/specs/2026-05-04-mame-activity-integration.md:280-294]

- [ ] **Step 1: 실패 테스트**

```python
# tests/mame/activity/test_export_evolvepro.py
from pathlib import Path
import csv
from kuma_core.mame.activity.export_evolvepro import export_evolvepro_csv
from kuma_core.mame.activity.models import MergedRow

def _row(**kwargs):
    base = dict(plate_id="P01", well_id="A01", mutation="F89W",
                mutation_source="kuro_design", expected_mutation="F89W",
                called_mutation="F89W", ngs_success=True,
                activity_raw_mean=2.0, activity_raw_sd=0.1,
                activity_replicates=[2.0], replicate_n=1,
                fold_change=2.0, log2_fc=1.0)
    base.update(kwargs)
    return MergedRow(**base)

def test_export_includes_kept_rows(tmp_path):
    rows = [_row(), _row(well_id="B01", mutation="WT", mutation_source="kuro_design",
                expected_mutation="WT", called_mutation="WT", log2_fc=0.0)]
    out = tmp_path / "evolvepro.csv"
    n = export_evolvepro_csv(rows, out, round_n=1)
    assert n == 1  # WT 제외
    with open(out) as f:
        reader = csv.DictReader(f)
        records = list(reader)
    assert len(records) == 1
    assert records[0]["variant"] == "F89W"
    assert abs(float(records[0]["y_pred"]) - 1.0) < 1e-6

def test_export_excluded_csv(tmp_path):
    rows = [_row(), _row(well_id="C01", ngs_success=False, mutation="L70V")]
    out = tmp_path / "evo.csv"
    export_evolvepro_csv(rows, out, round_n=1)
    excluded = tmp_path / "evo.excluded.csv"
    assert excluded.exists()
    with open(excluded) as f:
        reader = csv.DictReader(f)
        excl = list(reader)
    assert len(excl) == 1
    assert "ngs_success" in excl[0]["reason"].lower() or "ngs" in excl[0]["reason"]
```

- [ ] **Step 3: 구현**

```python
# kuma_core/mame/activity/export_evolvepro.py
import csv
from pathlib import Path
from kuma_core.mame.activity.models import MergedRow

COLUMNS = ["variant", "y_pred", "round_n", "plate_id", "well_id",
           "activity_raw_mean", "activity_raw_sd"]

def export_evolvepro_csv(rows: list[MergedRow], path: Path, round_n: int) -> int:
    kept = []
    excluded = []
    for r in rows:
        if not r.ngs_success:
            excluded.append((r, "ngs_success=False"))
        elif r.mutation == "WT":
            excluded.append((r, "mutation=WT"))
        elif r.log2_fc is None:
            excluded.append((r, "log2_fc=None"))
        else:
            kept.append(r)

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in kept:
            w.writerow({
                "variant": r.mutation, "y_pred": r.log2_fc,
                "round_n": round_n, "plate_id": r.plate_id, "well_id": r.well_id,
                "activity_raw_mean": r.activity_raw_mean,
                "activity_raw_sd": r.activity_raw_sd,
            })

    excluded_path = path.with_suffix(".excluded.csv")
    with open(excluded_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS + ["reason"])
        w.writeheader()
        for r, reason in excluded:
            w.writerow({
                "variant": r.mutation or "", "y_pred": r.log2_fc or "",
                "round_n": round_n, "plate_id": r.plate_id, "well_id": r.well_id,
                "activity_raw_mean": r.activity_raw_mean or "",
                "activity_raw_sd": r.activity_raw_sd or "",
                "reason": reason,
            })

    return len(kept)
```

- [ ] **Step 4-5**: 통과 + 커밋 `v0.2.7.07: EVOLVEpro CSV export with excluded.csv audit`

---

## Phase 2 — Sidecar handlers (0.5일)

### Task 2.1: activity.* RPC 핸들러

**파일**:
- 생성: `python-core/sidecar_mame/handlers/activity.py`
- 수정: `python-core/sidecar_mame/dispatcher.py`
- 테스트: `tests/mame/activity/test_handler_activity.py`

스펙 §3.2 [source: notes/specs/2026-05-04-mame-activity-integration.md:191-215]

- [ ] **Step 1: 실패 테스트**

```python
# tests/mame/activity/test_handler_activity.py
import json
from pathlib import Path
from python_core.sidecar_mame.handlers.activity import (
    handle_activity_upload, handle_activity_set_plate_meta,
    handle_activity_merge, handle_activity_export_evolvepro_csv
)

def test_handle_upload(tmp_path):
    csv = tmp_path / "act.csv"
    csv.write_text("plate_id,well_id,value\nP01,A01,1.0\n")
    state = {"rounds": {"round_1": {"plate_meta": {"plates": [
        {"plate_id": "P01", "wt_wells": ["A01"], "control_wells": []}]}}}}
    res = handle_activity_upload(state, {"round_id": "round_1", "file_path": str(csv), "format": "long_csv"})
    assert "records" in res
    assert len(res["records"]) == 1
    assert res["warnings"] == []
```

- [ ] **Step 3: 구현**

```python
# python-core/sidecar_mame/handlers/activity.py
from pathlib import Path
from kuma_core.mame.activity.ingest_long_csv import ingest_long_csv
from kuma_core.mame.activity.join import merge_activity_with_genotype
from kuma_core.mame.activity.export_evolvepro import export_evolvepro_csv
from kuma_core.mame.activity.models import PlateMeta, ActivityRecord

def handle_activity_upload(state: dict, params: dict) -> dict:
    round_id = params["round_id"]
    file_path = Path(params["file_path"])
    pmeta = state["rounds"][round_id]["plate_meta"]
    wt_lookup = {p["plate_id"]: p["wt_wells"] for p in pmeta["plates"]}
    table = ingest_long_csv(file_path, wt_lookup)
    return {"records": [r.model_dump() for r in table.records], "warnings": []}

def handle_activity_set_plate_meta(state: dict, params: dict) -> dict:
    round_id = params["round_id"]
    state["rounds"][round_id]["plate_meta"] = params["plate_meta"]
    return {"ok": True}

def handle_activity_merge(state: dict, params: dict) -> dict:
    round_id = params["round_id"]
    rd = state["rounds"][round_id]
    kuro_design = _extract_kuro_design(rd.get("design", {}))
    mame_geno = _extract_mame_genotype(rd.get("genotype", {}))
    plate_meta = PlateMeta(**rd["plate_meta"])
    raw = [ActivityRecord(**r) for r in rd.get("activity", {}).get("raw_records", [])]
    rows, stats = merge_activity_with_genotype(kuro_design, mame_geno, raw, plate_meta)
    rd["merged_table"] = [r.model_dump() for r in rows]
    rd["status"] = "activity_linked"
    return {"merged": rd["merged_table"], "stats": stats.model_dump()}

def handle_activity_export_evolvepro_csv(state: dict, params: dict) -> dict:
    round_id = params["round_id"]
    out = Path(params["path"])
    rd = state["rounds"][round_id]
    from kuma_core.mame.activity.models import MergedRow
    rows = [MergedRow(**r) for r in rd["merged_table"]]
    n = export_evolvepro_csv(rows, out, round_n=rd["n"])
    return {"written_rows": n, "columns": ["variant", "y_pred", "round_n", "plate_id",
            "well_id", "activity_raw_mean", "activity_raw_sd"]}

def _extract_kuro_design(design: dict) -> dict[tuple[str, str], str]:
    # design dict의 mutation list와 plate map에서 (plate_id, well_id) → mutation 추출
    # 5/12 전제: design = inputSlice snapshot. plate map이 inputSlice의 echoMapping에 있음
    plate_map = design.get("plateMap", [])
    return {(item["plate_id"], item["well_id"]): item["mutation"] for item in plate_map}

def _extract_mame_genotype(genotype: dict) -> dict[tuple[str, str], str]:
    # genotype dict의 verdict 결과에서 (plate_id, well_id) → called mutation 추출
    verdict = genotype.get("verdict", [])
    return {(v["plate_id"], v["well_id"]): v["called_mutation"] for v in verdict}
```

- [ ] **Step 4: dispatcher 등록**

```python
# python-core/sidecar_mame/dispatcher.py 끝부분에 추가
from python_core.sidecar_mame.handlers.activity import (
    handle_activity_upload, handle_activity_set_plate_meta,
    handle_activity_merge, handle_activity_export_evolvepro_csv
)

DISPATCH_TABLE.update({
    "activity.upload": handle_activity_upload,
    "activity.set_plate_meta": handle_activity_set_plate_meta,
    "activity.merge": handle_activity_merge,
    "activity.export_evolvepro_csv": handle_activity_export_evolvepro_csv,
})
```

- [ ] **Step 5: 통과 확인 + 커밋** `v0.2.7.08: activity sidecar handlers and dispatcher routing`

---

## Phase 3 — Frontend store (1일)

### Task 3.1: roundSlice (Round 엔티티)

**파일**:
- 생성: `src/store/round/roundSlice.ts`
- 테스트: `src/store/round/roundSlice.test.ts` (Vitest)

[source: notes/specs/2026-05-04-mame-activity-integration.md:36-80]

- [ ] **Step 1: 실패 테스트**

```typescript
// src/store/round/roundSlice.test.ts
import { describe, it, expect } from "vitest"
import { createRoundSlice } from "./roundSlice"

describe("roundSlice", () => {
  it("addRound creates new round with status=design", () => {
    const slice = createRoundSlice()
    const id = slice.addRound({ plate_meta: { plates: [] } })
    expect(slice.rounds).toHaveLength(1)
    expect(slice.rounds[0].status).toBe("design")
    expect(slice.rounds[0].n).toBe(1)
  })

  it("transitionStatus updates round status", () => {
    const slice = createRoundSlice()
    slice.addRound({ plate_meta: { plates: [] } })
    slice.transitionStatus("round_1", "activity_linked")
    expect(slice.rounds[0].status).toBe("activity_linked")
  })

  it("addRound increments n", () => {
    const slice = createRoundSlice()
    slice.addRound({ plate_meta: { plates: [] } })
    slice.addRound({ plate_meta: { plates: [] } })
    expect(slice.rounds[1].n).toBe(2)
    expect(slice.rounds[1].id).toBe("round_2")
  })
})
```

- [ ] **Step 3: 구현**

```typescript
// src/store/round/roundSlice.ts
import type { Round, RoundStatus } from "@/types/round"
import type { PlateMeta } from "@/types/mame/activity"

interface RoundSliceState {
  rounds: Round[]
  active_round_id: string | null
}

export interface RoundSlice extends RoundSliceState {
  addRound: (init: { plate_meta: PlateMeta }) => string
  transitionStatus: (round_id: string, status: RoundStatus) => void
  setActiveRound: (round_id: string) => void
  updateRoundField: <K extends keyof Round>(round_id: string, field: K, value: Round[K]) => void
}

export function createRoundSlice(): RoundSlice {
  const state: RoundSliceState = { rounds: [], active_round_id: null }

  return {
    get rounds() { return state.rounds },
    get active_round_id() { return state.active_round_id },

    addRound(init) {
      const n = state.rounds.length + 1
      const id = `round_${n}`
      const round: Round = {
        id, n,
        created_at: new Date().toISOString(),
        status: "design",
        error_info: null,
        plate_meta: init.plate_meta,
        design: {}, genotype: {},
        activity: null,
        merged_table: [],
      }
      state.rounds.push(round)
      state.active_round_id = id
      return id
    },

    transitionStatus(round_id, status) {
      const r = state.rounds.find(x => x.id === round_id)
      if (r) r.status = status
    },

    setActiveRound(round_id) { state.active_round_id = round_id },

    updateRoundField(round_id, field, value) {
      const r = state.rounds.find(x => x.id === round_id)
      if (r) (r[field] as unknown) = value
    },
  }
}
```

(실제로는 Zustand `create<>()` 패턴으로 wrapping 필요. 위는 단위 테스트용 단순화)

- [ ] **Step 4-5**: 통과 확인 + 커밋 `v0.2.7.09: roundSlice with Round entity CRUD`

### Task 3.2: activitySlice

**파일**: `src/store/mame/activitySlice.ts` + 테스트

- [ ] **Step 1-5**: 표준 사이클. activity 업로드 파일·매핑·merged_table 상태 관리. activity.* RPC 호출 wrapper.

핵심 메서드:
- `uploadActivityFile(round_id, file_path, format)` → 백엔드 `activity.upload` 호출 → 결과를 round.activity.raw_records에 저장
- `setPlateMeta(round_id, plate_meta)` → `activity.set_plate_meta`
- `mergeActivity(round_id)` → `activity.merge` → round.merged_table 갱신, status="activity_linked"
- `exportEvolveproCsv(round_id, path)` → `activity.export_evolvepro_csv`

커밋 `v0.2.7.10: activitySlice with backend RPC wrappers`

### Task 3.3: exportSlice 수정 (workspace snapshot에 rounds 추가)

**파일**: 수정 `src/store/exportSlice.ts:380-457` (`getWorkspaceSnapshot`, `restoreWorkspace`)

[source: notes/specs/2026-05-04-mame-activity-integration.md:127-130 (cross-layer checklist)]

- [ ] **Step 1: 실패 테스트**

```typescript
// 기존 exportSlice.test.ts에 추가
it("snapshot includes rounds and schema_version 0.3", () => {
  const snap = getWorkspaceSnapshot()
  expect(snap.schema_version).toBe("0.3")
  expect(snap.rounds).toBeDefined()
  expect(Array.isArray(snap.rounds)).toBe(true)
})

it("restoreWorkspace rejects schema_version < 0.3", () => {
  const old = { schema_version: "0.2", /* ... */ }
  expect(() => restoreWorkspace(old)).toThrow(/v0.3 이전/)
})
```

- [ ] **Step 3: 수정**

```typescript
// src/store/exportSlice.ts (관련 부분만)
export function getWorkspaceSnapshot(): WorkspaceSnapshot {
  return {
    schema_version: "0.3",
    active_round_id: roundStore.active_round_id,
    rounds: roundStore.rounds.map(r => ({
      ...r,
      design: getKuroSnapshotForRound(r.id),
      genotype: getMameSnapshotForRound(r.id),
    })),
    // ... 기존 필드
  }
}

export function restoreWorkspace(snap: any) {
  if (!snap.schema_version || snap.schema_version < "0.3") {
    throw new Error(
      "v0.3 이전 워크스페이스는 지원하지 않습니다. 새 워크스페이스로 시작하세요."
    )
  }
  // ... rounds 복원, 각 round의 design/genotype을 KURO/MAME store에 hydrate
}
```

- [ ] **Step 5: 커밋** `v0.2.7.11: workspace schema 0.3 with rounds, hard break for older`

### Task 3.4: ipc.ts (RPC client)

**파일**: 수정 `src/lib/ipc.ts`

- [ ] **Step 1-5**: activity.* 4개 RPC client 함수 추가

```typescript
// src/lib/ipc.ts에 추가
export async function activityUpload(round_id: string, file_path: string, format: "long_csv" | "long_xlsx") {
  return invokeMame("activity.upload", { round_id, file_path, format })
}
export async function activitySetPlateMeta(round_id: string, plate_meta: PlateMeta) {
  return invokeMame("activity.set_plate_meta", { round_id, plate_meta })
}
export async function activityMerge(round_id: string): Promise<{ merged: MergedRow[]; stats: MergeStats }> {
  return invokeMame("activity.merge", { round_id })
}
export async function activityExportEvolveproCsv(round_id: string, path: string) {
  return invokeMame("activity.export_evolvepro_csv", { round_id, path })
}
```

커밋 `v0.2.7.12: activity RPC client functions`

---

## Phase 4 — Frontend UI (1.5일)

### Task 4.1: ActivityUploadPanel

**파일**: 생성 `src/components/mame/ActivityUploadPanel.tsx` + 테스트

스펙 §4.4 [source: notes/specs/2026-05-04-mame-activity-integration.md:380-394]

- [ ] **Step 1-5**: 드래그드롭 + format select + 행 미리보기. shadcn/ui 컴포넌트 사용.

```tsx
// 핵심 구조
export function ActivityUploadPanel({ round_id }: { round_id: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [format, setFormat] = useState<"long_csv" | "long_xlsx">("long_csv")
  const upload = useActivitySlice(s => s.uploadActivityFile)
  const records = useActivitySlice(s => s.rounds[round_id]?.activity?.records ?? [])

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">Activity Data</h3>
      <input type="file" onChange={e => setFile(e.target.files?.[0] ?? null)} accept=".csv,.xlsx" />
      <Select value={format} onValueChange={setFormat}>...</Select>
      <Button onClick={() => file && upload(round_id, file.path, format)}>Upload</Button>
      <p className="text-xs text-muted-foreground">{records.length} wells loaded</p>
    </div>
  )
}
```

커밋 `v0.2.7.13: ActivityUploadPanel with drag-drop and format select`

### Task 4.2: WtWellEditor

**파일**: 생성 `src/components/mame/WtWellEditor.tsx`

[source: notes/specs/2026-05-04-mame-activity-integration.md:373-378]

- [ ] **Step 1-5**: 96-well plate map 모달. WT well 클릭 토글. plate_meta 갱신.

커밋 `v0.2.7.14: WtWellEditor modal for WT well designation`

### Task 4.3: ParameterPanel 수정

**파일**: 수정 `src/components/mame/ParameterPanel.tsx`

[source: notes/specs/2026-05-04-mame-activity-integration.md:380-394]

- [ ] **Step 1-5**: Activity Data 섹션 추가 (`<ActivityUploadPanel />` + `<WtWellEditor />` + Merge/Export 버튼)

커밋 `v0.2.7.15: ParameterPanel adds Activity Data section`

### Task 4.4: VerdictTable 컬럼 확장

**파일**: 수정 `src/components/mame/VerdictTable.tsx`

[source: notes/specs/2026-05-04-mame-activity-integration.md:362-366]

- [ ] **Step 1-5**: 신규 컬럼 5개 (`activity_log2fc`, `fold_change`, `raw_mean ± sd`, `replicate_n`, `ngs_success`). 컬럼 토글. `min-w-0` flex overflow 가드.

커밋 `v0.2.7.16: VerdictTable adds activity columns with toggles`

### Task 4.5: RoundHandoffButton

**파일**: 생성 `src/components/round/RoundHandoffButton.tsx`

[source: notes/specs/2026-05-04-mame-activity-integration.md:368-378]

- [ ] **Step 1: 실패 테스트**

```tsx
// src/components/round/RoundHandoffButton.test.tsx
it("disabled when merged_table empty", () => {
  const { getByRole } = render(<RoundHandoffButton round_id="round_1" />)
  expect(getByRole("button")).toBeDisabled()
})

it("calls handoffNextRound on click", async () => {
  // setup with merged_table populated
  ...
  const handoff = vi.fn()
  // click → handoff called with prev round id
})
```

- [ ] **Step 3: 구현**

```tsx
// src/components/round/RoundHandoffButton.tsx
export function RoundHandoffButton({ round_id }: { round_id: string }) {
  const round = useRoundSlice(s => s.rounds.find(r => r.id === round_id))
  const handoff = useRoundSlice(s => s.handoffNextRound)
  const disabled = !round?.merged_table.length

  return (
    <Button onClick={() => handoff(round_id)} disabled={disabled}>
      Start Round {(round?.n ?? 0) + 1}
    </Button>
  )
}
```

커밋 `v0.2.7.17: RoundHandoffButton with disabled state`

---

## Phase 5 — KURO 핸드오프 (0.5일)

### Task 5.1: inputSlice.loadRoundActivity

**파일**: 수정 `src/store/slices/inputSlice.ts`

스펙 §4.5 [source: notes/specs/2026-05-04-mame-activity-integration.md:339-356]

- [ ] **Step 1: 실패 테스트**

```typescript
// src/store/slices/inputSlice.test.ts
describe("loadRoundActivity", () => {
  it("hydrates evolveproRows from prevRound merged_table", () => {
    const prev = makeRoundWithMergedTable([
      { mutation: "F89W", log2_fc: 0.99, ngs_success: true /* ... */ },
      { mutation: "WT", log2_fc: 0.0, ngs_success: true /* ... */ },
    ])
    const result = loadRoundActivity(prev)
    expect(result.ok).toBe(true)
    expect(inputSlice.evolveproRows).toHaveLength(1)  // WT 제외
    expect(inputSlice.evolveproRows[0].variant).toBe("F89W")
    expect(inputSlice.mutationInputMode).toBe("evolvepro")
    expect(inputSlice.mutationText).toBe("")
  })

  it("returns ok=false when no rows pass filter", () => {
    const prev = makeRoundWithMergedTable([])
    const result = loadRoundActivity(prev)
    expect(result.ok).toBe(false)
    expect(result.warnings).toContain("0 rows after filter")
  })
})
```

- [ ] **Step 3: 구현**

```typescript
// src/store/slices/inputSlice.ts에 추가
export function loadRoundActivity(prevRound: Round): { ok: boolean; warnings: string[] } {
  const filtered = prevRound.merged_table.filter(r =>
    r.ngs_success && r.mutation && r.mutation !== "WT" && r.log2_fc !== null
  )
  if (filtered.length === 0) {
    return { ok: false, warnings: ["0 rows after filter (ngs_success && non-WT && log2_fc)"] }
  }
  set({
    mutationInputMode: "evolvepro",
    evolveproRows: filtered.map(r => ({
      variant: r.mutation!, y_pred: r.log2_fc!,
      round_n: prevRound.n, plate_id: r.plate_id, well_id: r.well_id,
    })),
    mutationText: "",
  })
  // diversity 캐시 초기화
  diversitySlice.evolveproTotalCount = 0
  diversitySlice.evolveproStepStats = null
  return { ok: true, warnings: [] }
}
```

- [ ] **Step 5: 커밋** `v0.2.7.18: inputSlice.loadRoundActivity for round handoff`

### Task 5.2: roundSlice.handoffNextRound

**파일**: 수정 `src/store/round/roundSlice.ts`

[source: notes/specs/2026-05-04-mame-activity-integration.md:368-378]

- [ ] **Step 1-5**: prev round 종료(status=exported) → 새 round 생성 (n+1) → loadRoundActivity 호출 → KURO 탭 자동 전환

커밋 `v0.2.7.19: roundSlice handoffNextRound 1-click flow`

---

## Phase 6 — Strategy signals (1일, 5/12 부분 IN)

### Task 6.1: Strategy 신호 계산 (T1·T2·T3·T4·T_active·T_unused)

**파일**:
- 생성: `kuma_core/strategy/__init__.py`
- 생성: `kuma_core/strategy/signals.py`
- 생성: `kuma_core/strategy/models.py`
- 테스트: `tests/strategy/test_signals.py`

스펙 §12-A.1 [source: notes/specs/2026-05-04-mame-activity-integration.md:606-630]

- [ ] **Step 1: 실패 테스트**

```python
# tests/strategy/test_signals.py
from kuma_core.strategy.signals import (
    compute_K_throughput, compute_T1, compute_T2, compute_T3,
    compute_T4, compute_T_active, compute_T_unused, compute_sigma_assay
)

def test_K_throughput_96_well():
    assert compute_K_throughput(96) == 14  # C(14,2)=91 ≤ 96

def test_K_throughput_384_well():
    assert compute_K_throughput(384) == 28

def test_T1_threshold():
    assert compute_T1(cumulative_beneficial=15, K_throughput=14) == True
    assert compute_T1(cumulative_beneficial=10, K_throughput=14) == False

def test_T2_plateau():
    # delta < 1.96 * sigma * sqrt(2/r)
    delta_ema = 0.05
    sigma = 0.1
    r = 3
    threshold = 1.96 * sigma * (2/r)**0.5
    assert compute_T2(delta_ema, sigma, r) == (delta_ema < threshold)

def test_sigma_assay_from_wt_replicates():
    wt_values = [1.0, 1.05, 0.98, 1.02]
    assert compute_sigma_assay(wt_values) is not None
    assert compute_sigma_assay(wt_values[:3]) is None  # < 4 WT replicate

def test_T_active_concentration():
    # top-K 변이 위치 중 active site 6Å 이내 비율
    top_k_positions = [89, 70, 263, 477, 305]
    active_residues = [89, 263]
    assert compute_T_active(top_k_positions, active_residues, threshold=0.4) == False  # 2/5 = 0.4 borderline
    # adjust test logic per spec
```

- [ ] **Step 3: 구현**

```python
# kuma_core/strategy/signals.py
import math
import statistics
from typing import Optional

def compute_K_throughput(C_next: int) -> int:
    """floor((1 + sqrt(1 + 8*C_next)) / 2). C(K,2) <= C_next 만족 K"""
    return int((1 + math.sqrt(1 + 8 * C_next)) / 2)

def compute_T1(cumulative_beneficial: int, K_throughput: int) -> bool:
    return cumulative_beneficial >= K_throughput

def compute_T2(delta_best_ema: float, sigma_assay: float, r: int) -> bool:
    if r < 1: return False
    threshold = 1.96 * sigma_assay * math.sqrt(2.0 / r)
    return delta_best_ema < threshold

def compute_T3(hit_rates: list[float]) -> bool:
    """라운드별 hit rate 선형 회귀 기울기 ≤ 0"""
    if len(hit_rates) < 2: return False
    n = len(hit_rates)
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(hit_rates) / n
    num = sum((x[i] - x_mean) * (hit_rates[i] - y_mean) for i in range(n))
    den = sum((xi - x_mean) ** 2 for xi in x)
    if den == 0: return False
    slope = num / den
    return slope <= 0

def compute_T4(top_k_positions_n: set[int], top_k_positions_n1: set[int],
               jaccard_threshold: float = 0.5) -> bool:
    if not top_k_positions_n or not top_k_positions_n1:
        return False
    inter = len(top_k_positions_n & top_k_positions_n1)
    union = len(top_k_positions_n | top_k_positions_n1)
    if union == 0: return False
    return (inter / union) >= jaccard_threshold

def compute_T_active(top_k_positions: list[int], active_residues: list[int],
                     threshold: float = 0.4) -> bool:
    if not top_k_positions or not active_residues:
        return False
    active_set = set(active_residues)
    in_active = sum(1 for p in top_k_positions if p in active_set)
    return (in_active / len(top_k_positions)) >= threshold

def compute_T_unused(unused_beneficial_count: int, M_min: int = 5) -> bool:
    return unused_beneficial_count >= M_min

def compute_sigma_assay(wt_values: list[float], min_replicates: int = 4) -> Optional[float]:
    if len(wt_values) < min_replicates:
        return None
    return statistics.stdev(wt_values)
```

- [ ] **Step 5: 커밋** `v0.2.7.20: strategy signals T1-T_unused with reasoning anchors`

### Task 6.2: StrategyDecisionLog 모델

**파일**: `kuma_core/strategy/models.py` + 테스트

스펙 §12-A.4 [source: notes/specs/2026-05-04-mame-activity-integration.md:720-740]

- [ ] **Step 1-5**: Pydantic StrategyDecisionLog (위 spec 정의 그대로). decision Literal에 4개 라벨 (continue_walking/switch_combinatorial/stop/deferred).

커밋 `v0.2.7.21: StrategyDecisionLog Pydantic with 4 decision labels`

### Task 6.3: RoundSummaryPanel (5/12 IN — 표시만)

**파일**: 생성 `src/components/round/RoundSummaryPanel.tsx`

스펙 §12-A.6 (5/12 IN), §12-A.5 calibration mode [source: notes/specs/2026-05-04-mame-activity-integration.md:743-754]

- [ ] **Step 1-5**: 라운드별 메트릭 표 + 신호 boolean 표시. "calibration period" 라벨. 분류 결정은 안 함.

```tsx
export function RoundSummaryPanel({ round_id }: { round_id: string }) {
  const round = useRoundSlice(s => s.rounds.find(r => r.id === round_id))
  const signals = useStrategySignals(round_id)  // T1~T_unused 계산 결과
  return (
    <div className="space-y-2">
      <h3>Round {round?.n} — Strategy signals (calibration)</h3>
      <table>
        <tr><td>T1 (K_throughput)</td><td>{signals.T1 ? "✓" : "—"}</td><td>{signals.cumulative_beneficial}/{signals.K_throughput}</td></tr>
        <tr><td>T2 (Δ_best plateau)</td><td>{signals.T2 ? "✓" : "—"}</td><td>...</td></tr>
        ...
      </table>
      <p className="text-xs">Calibration period — 분류 결정 비활성</p>
    </div>
  )
}
```

커밋 `v0.2.7.22: RoundSummaryPanel displays signals in calibration mode`

---

## Phase 7 — Fixtures + integration test (0.5일)

### Task 7.1: 합성 fixture 생성기

**파일**:
- 생성: `fixtures/activity_demo/generate.py`
- 생성: `fixtures/activity_demo/round1_activity.csv` (생성 결과)
- 생성: `fixtures/activity_demo/plate_meta.json`

스펙 §5.2 [source: notes/specs/2026-05-04-mame-activity-integration.md:399-407]

- [ ] **Step 1: 작성**

```python
# fixtures/activity_demo/generate.py
import csv
import json
import random
from pathlib import Path

random.seed(20260504)

WT_WELLS = ["A01", "A12", "H01", "H12"]
WT_MEAN = 1.0

# 30 mutations × 3 replicate = 90 wells + 4 WT + 2 extra
MUTATIONS = [f"M{i:02d}{aa}" for i, aa in enumerate("FWVLAGIPS" * 4)][:30]

def generate():
    out = Path(__file__).parent / "round1_activity.csv"
    rows = []
    # WT wells
    for w in WT_WELLS:
        rows.append({"plate_id": "P01", "well_id": w,
                     "value": random.gauss(WT_MEAN, 0.05), "replicate_idx": 1})

    # Variants: round-robin assign mutations to 92 wells
    all_wells = [f"{r}{c:02d}" for r in "ABCDEFGH" for c in range(1, 13)]
    variant_wells = [w for w in all_wells if w not in WT_WELLS]

    log2_targets = {m: random.gauss(0, 0.7) for m in MUTATIONS}
    # Inject specific test seeds:
    log2_targets["F89W"] = 0.99  # asserted in test
    log2_targets["L70V"] = -0.50

    for i, well in enumerate(variant_wells):
        mut = MUTATIONS[i % len(MUTATIONS)]
        true_log2 = log2_targets[mut]
        value = WT_MEAN * (2 ** true_log2) * random.gauss(1.0, 0.03)
        rows.append({"plate_id": "P01", "well_id": well,
                     "value": value, "replicate_idx": 1})

    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["plate_id", "well_id", "value", "replicate_idx"])
        w.writeheader()
        w.writerows(rows)

    plate_meta = {"plates": [{"plate_id": "P01", "wt_wells": WT_WELLS, "control_wells": []}]}
    with open(Path(__file__).parent / "plate_meta.json", "w") as f:
        json.dump(plate_meta, f, indent=2)

if __name__ == "__main__":
    generate()
```

- [ ] **Step 2: 실행**: `python fixtures/activity_demo/generate.py` → 두 파일 생성
- [ ] **Step 3: 커밋** `v0.2.7.23: synthetic activity fixture with seeded test rows`

### Task 7.2: Round-trip 통합 테스트

**파일**: 생성 `tests/integration/test_kuma_round_trip.py`

스펙 §9.2 [source: notes/specs/2026-05-04-mame-activity-integration.md:501-513]

- [ ] **Step 1-5**: 9단계 통합 테스트 (스펙 §9.2 표 그대로 assertion)

```python
# tests/integration/test_kuma_round_trip.py
import pytest
from pathlib import Path
from kuma_core.mame.activity.ingest_long_csv import ingest_long_csv
from kuma_core.mame.activity.join import merge_activity_with_genotype
from kuma_core.mame.activity.export_evolvepro import export_evolvepro_csv
from kuma_core.mame.activity.models import PlateMeta

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "activity_demo"

def test_round_trip(tmp_path):
    # 합성 fixture 로드
    table = ingest_long_csv(FIXTURE / "round1_activity.csv",
                            {"P01": ["A01", "A12", "H01", "H12"]})
    assert len(table.records) == 96

    # Synthetic kuro_design + mame_genotype
    kuro_design = {("P01", w): m for w, m in [("B03", "F89W"), ("G05", "L70V")]}
    mame_geno = dict(kuro_design)  # 90 success 가정 (test 단순화 위해 모두 일치)

    rows, stats = merge_activity_with_genotype(kuro_design, mame_geno, table.records, table.plate_meta)
    assert stats.n_total_wells >= 96
    assert stats.n_wt == 4

    f89w = next(r for r in rows if r.well_id == "B03")
    assert abs(f89w.log2_fc - 0.99) < 0.01

    l70v = next(r for r in rows if r.well_id == "G05")
    assert abs(l70v.log2_fc - (-0.50)) < 0.01

    # Export → 재파싱 round-trip
    out = tmp_path / "evo.csv"
    n = export_evolvepro_csv(rows, out, round_n=1)
    assert n >= 1

    from kuma_core.kuro.evolvepro import _load_evolvepro_rows
    reloaded = _load_evolvepro_rows(out)
    assert len(reloaded) == n
```

- [ ] **Step 5: 커밋** `v0.2.7.24: round-trip integration test (synthetic fixture → merge → export → reparse)`

---

## Phase 8 — Docs + cleanup (0.5일)

### Task 8.1: UPDATE-NOTES + README + CLAUDE.md

- [ ] UPDATE-NOTES.ko.md에 `v0.2.7` 섹션 추가 (활성 통합·Round 엔티티·Strategy 신호)
- [ ] README.ko.md에 Activity Data Integration 섹션 추가
- [ ] CLAUDE.md "Cross-layer Change Checklist"에 6행 추가 (스펙 §12.3)
- [ ] 워크스페이스 hard break 안내: 첫 로드 시 다이얼로그 메시지 (이미 Task 3.3에 throw 처리됨)

커밋 `v0.2.7.25: docs update for activity integration release`

### Task 8.2: 사이드카 빌드 검증

```bash
pnpm run sidecar:build
```

PyInstaller가 새 모듈(`kuma_core.mame.activity`, `kuma_core.strategy`)을 포함하는지 확인. `python-core/sidecar_*.py`의 `--hidden-import` 갱신 필요 시.

- [ ] 빌드 후 `--version` 호출로 사이드카 정상 기동 확인
- [ ] 커밋 (필요 시) `v0.2.7.26: sidecar build hidden imports for activity/strategy`

### Task 8.3: 사전 검증 게이트

```bash
npx tsc --noEmit
cd src-tauri && cargo check
python -m pytest tests/ -v
```

세 가지 모두 통과 시 5/12 데모 준비 완료.

---

## 의존 그래프

```
Phase 0 (모델)
   └─ Phase 1 (백엔드 ingest/merge/export) ─┐
                                              ├─ Phase 2 (sidecar handler)
                                              ├─ Phase 6 (signals — 백엔드 부분)
   └─ Phase 3 (frontend store)
        ├─ Phase 4 (UI)
        ├─ Phase 5 (KURO handoff)
        └─ Phase 6 (RoundSummaryPanel)
                                              └─ Phase 7 (integration test)
                                                  └─ Phase 8 (docs + 빌드)
```

병렬 가능:
- Phase 1 백엔드 + Phase 3 frontend store (인터페이스만 합의)
- Phase 4 UI 컴포넌트들 (독립)

---

## 5/12 데모 시나리오 (검증 게이트)

스펙 §10 [source: notes/specs/2026-05-04-mame-activity-integration.md:519-535]

1. 새 워크스페이스 생성 → schema_version="0.3"
2. KURO 라운드 1 디자인 (합성 EVOLVEpro CSV 또는 안건 1 first-round)
3. (시뮬레이션 nanopore + 합성 활성 fixture) MAME ingest
4. ActivityUploadPanel → `fixtures/activity_demo/round1_activity.csv` 업로드
5. WtWellEditor → A01/A12/H01/H12 WT 지정
6. "Merge with genotype" 클릭 → VerdictTable에 신규 5컬럼
7. RoundSummaryPanel에 T1~T_unused 신호값 + "calibration period" 라벨
8. "Export EVOLVEpro CSV" → `round1_evolvepro.csv` + `.excluded.csv`
9. "Start Round N+1" → KURO 탭 자동 전환, evolvepro 모드 hydrate

성공 기준: 1–9 사용자 5분 내 완료, B03 log2_fc ≈ 0.99 ± 0.01, G05 ≈ -0.50 ± 0.01

---

## 안건 1 spec(`fill-on-failure-mode-split-and-workspace-input-reload.md`)과의 병행

- 안건 1은 v0.2.5.x로 이미 부분 구현됨 (`v0.2.5.03~10`).
- 본 spec과의 결합점 (스펙 §12.4):
  - `loadRoundActivity`는 안건 1 분리 후의 EVOLVEpro CSV 경로 사용 — 호환 검증 (Task 5.1 테스트로 일부 커버)
  - fillOnFailure 모드와 라운드 핸드오프 독립 — 충돌 없음
- PR 분리: 본 spec 구현은 별도 PR. 안건 1 추가 작업이 들어가면 별 PR

---

## 누적 커밋 계획 (총 ~26 커밋)

`v0.2.7.00` ~ `v0.2.7.26` (BB 신규 기능 = 0.2.7). 마지막에 `v0.2.7` 태그로 release.

---

## 위험과 대비

| 위험 | 대비 |
|---|---|
| 혜민 연구원 실데이터 형식 미확정 | 합성 fixture로 5/12 데모 가능. 실데이터는 사후 검증 |
| C_next, active_residues 미입력 | T2/T_active 자동 비활성, 다른 신호로 평가 (calibration mode) |
| roundSlice가 기존 5 슬라이스에 침투 시 회귀 | 단방향 의존만 추가 (rounds → slice snapshot wrap), 기존 슬라이스 무변경 |
| EVOLVEpro CSV round-trip 실패 | Task 7.2 통합 테스트로 검증 |
| sidecar PyInstaller가 새 모듈 누락 | Task 8.2에서 `--hidden-import` 또는 spec 파일 갱신 |

---

## Confidence Check

| 축 | 점수 | 근거 |
|---|---|---|
| Completeness | 5/5 | 스펙 §1–§12-A 5/12 IN 항목 모두 task로 매핑 (Phase 0–8) |
| Clarity | 4/5 | 각 Task에 정확한 파일 경로·코드·커밋 메시지. 일부 UI Task(4.2, 4.4)는 shadcn/ui 사용 가정으로 세부 구현 압축 |
| Feasibility | 5/5 | 신규 의존성 0건. 기존 pandas/openpyxl/Pydantic/Zustand로 모두 구현 가능. PyInstaller 빌드 검증 항목 포함 |

총점 14/15. PASS.

---

## 다음 단계

1. 본 계획 @verifier 검증
2. 사용자 최종 리뷰
3. `execute-plan` 스킬로 구현 시작
4. 병행: PI/혜민 연구원에 `260504_KUMA_5_12데모_사전확인_항목.md` 7개 항목 확인 요청
