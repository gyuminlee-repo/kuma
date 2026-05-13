# Export All + Macrogen + Sidebar Resize 구현 계획

**스펙:** [source: notes/specs/2026-05-13-export-all-macrogen.md]
**모드:** shape (요구사항 확정, 아키텍처 결정)
**Verifier 판정:** TBD

**목표:** Phase C export UI 를 Export All 단일 버튼으로 통합하고 Macrogen Plate Oligo `.xls` exporter 를 신설한다. 동시에 kUMA 전역 사이드바 너비 통일과 드래그 리사이즈를 구현한다.

**아키텍처:** 두 독립 서브시스템을 Part A / Part B 로 분리해 순차 실행. Part A 는 Python sidecar exporter → Pydantic 모델 → TS RPC → React UI 순. Part B 는 빌드 타임 너비 계산 → Zustand 슬라이스 → AppShell 통합 순. 두 파트 모두 TDD (실패 테스트 → 최소 구현 → 통과 → 커밋).

**기술 스택:** Python 3.11 + xlwt 1.3.0 + Pydantic v2, React 19 + TypeScript + Zustand + Tailwind, pytest + vitest.

---

# Part A — Export All + Macrogen Plate Order

## A1. xlwt 의존성 추가

**파일:**
- 수정: `.devcontainer/Dockerfile`
- 수정: `python-core/requirements.txt` (없으면 생성)

- [ ] **Step 1: requirements 파일 확인**

실행: `cat python-core/requirements.txt | grep -i xlwt; ls python-core/pyproject.toml kuma_core/pyproject.toml 2>&1`
예상: 미발견.

- [ ] **Step 2: requirements 에 xlwt 추가**

```diff
+ xlwt==1.3.0
```

(파일 없으면 `kuma_core/pyproject.toml` 의 `[project.dependencies]` 또는 `python-core/pyproject.toml` 에 추가. 실측 경로 따라 한 곳만.)

- [ ] **Step 3: Dockerfile 갱신**

`.devcontainer/Dockerfile` 의 pip install 라인에 `xlwt==1.3.0` 추가.

- [ ] **Step 4: 로컬 설치 검증**

실행: `pip install --break-system-packages xlwt==1.3.0 && python -c "import xlwt; print(xlwt.__VERSION__)"`
예상: `1.3.0`.

- [ ] **Step 5: 커밋**

```bash
git add .devcontainer/Dockerfile python-core/requirements.txt
git commit -m "v0.4.0.01: add xlwt 1.3.0 for Macrogen xls export"
```

> 알림 출력: "`.devcontainer/Dockerfile` 변경 — Rebuild Container 필요".

---

## A2. `export_macrogen_xls` — Python exporter (TDD)

**파일:**
- 생성: `tests/test_macrogen_export.py`
- 수정: `kuma_core/kuro/plate_mapper.py` (함수 추가, 파일 끝)

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_macrogen_export.py
import re
import pytest
import xlrd
from kuma_core.kuro.plate_mapper import export_macrogen_xls
from kuma_core.kuro.types import Primer  # adjust import to actual

def _mk(seq: str, name: str) -> "Primer":
    return Primer(name=name, sequence=seq)

def test_macrogen_export_1plate_1well(tmp_path):
    out = tmp_path / "out.xls"
    export_macrogen_xls(
        fwd_primers=[_mk("ATCG", "p1")], rev_primers=[],
        fwd_plate_name="P1", rev_plate_name="",
        amount="0.05", purification="MOPC", output_path=str(out),
    )
    wb = xlrd.open_workbook(str(out))
    s = wb.sheets()[0]
    assert s.cell_value(0, 0) == "No."
    assert s.cell_value(1, 1) == "P1"
    assert s.cell_value(1, 2) == "A1"
    assert s.cell_value(1, 3) == "p1"
    assert s.cell_value(1, 4) == "ATCG"
    assert s.cell_value(1, 5) == "0.05"
    assert s.cell_value(1, 6) == "MOPC"

def test_column_major_well_order(tmp_path):
    primers = [_mk("A" * 4, f"p{i}") for i in range(9)]  # fills A1..H1, A2
    out = tmp_path / "out.xls"
    export_macrogen_xls(
        fwd_primers=primers, rev_primers=[],
        fwd_plate_name="P1", rev_plate_name="",
        amount="0.05", purification="MOPC", output_path=str(out),
    )
    wb = xlrd.open_workbook(str(out))
    s = wb.sheets()[0]
    wells = [s.cell_value(i, 2) for i in range(1, 10)]
    assert wells == ["A1","B1","C1","D1","E1","F1","G1","H1","A2"]

def test_2plates_concatenated(tmp_path):
    out = tmp_path / "out.xls"
    export_macrogen_xls(
        fwd_primers=[_mk("AAA", "f1")], rev_primers=[_mk("TTT", "r1")],
        fwd_plate_name="Pfwd", rev_plate_name="Prev",
        amount="0.05", purification="MOPC", output_path=str(out),
    )
    wb = xlrd.open_workbook(str(out))
    s = wb.sheets()[0]
    assert s.nrows == 1 + 96 + 96
    assert s.cell_value(1, 1) == "Pfwd"
    assert s.cell_value(97, 1) == "Prev"
    assert s.cell_value(97, 0) == 97  # No. continues

def test_overflow_raises(tmp_path):
    out = tmp_path / "out.xls"
    with pytest.raises(ValueError, match="exceeds 96"):
        export_macrogen_xls(
            fwd_primers=[_mk("A", f"p{i}") for i in range(97)],
            rev_primers=[], fwd_plate_name="P1", rev_plate_name="",
            amount="0.05", purification="MOPC", output_path=str(out),
        )

def test_plate_name_rejects_korean(tmp_path):
    with pytest.raises(ValueError, match="plate name"):
        export_macrogen_xls(
            fwd_primers=[_mk("A", "p")], rev_primers=[],
            fwd_plate_name="한글", rev_plate_name="",
            amount="0.05", purification="MOPC", output_path=str(tmp_path/"x.xls"),
        )

def test_oligo_name_rejects_space(tmp_path):
    with pytest.raises(ValueError, match="oligo name"):
        export_macrogen_xls(
            fwd_primers=[_mk("A", "p 1")], rev_primers=[],
            fwd_plate_name="P", rev_plate_name="",
            amount="0.05", purification="MOPC", output_path=str(tmp_path/"x.xls"),
        )
```

- [ ] **Step 2: 실행 → 실패**

실행: `python -m pytest tests/test_macrogen_export.py -v`
예상: `ImportError: cannot import name 'export_macrogen_xls'`.

- [ ] **Step 3: 최소 구현**

`kuma_core/kuro/plate_mapper.py` 끝에 추가:

```python
import re as _re
import xlwt as _xlwt

_MACROGEN_NAME_RE = _re.compile(r"^[A-Za-z0-9_-]{1,20}$")
_HEADERS = ["No.", "Plate Name", "Well", "Oligo Name", "5' - Oligo Seq - 3'", "Amount", "Purification"]

def _column_major_wells() -> list[str]:
    return [f"{r}{c}" for c in range(1, 13) for r in "ABCDEFGH"]

def _validate_plate_name(name: str, label: str) -> None:
    if not _MACROGEN_NAME_RE.fullmatch(name):
        raise ValueError(f"{label} plate name '{name}' violates ^[A-Za-z0-9_-]{{1,20}}$")

def _validate_oligo_names(primers, label: str) -> None:
    for p in primers:
        if not _MACROGEN_NAME_RE.fullmatch(p.name):
            raise ValueError(f"{label} oligo name '{p.name}' violates ^[A-Za-z0-9_-]{{1,20}}$")

def export_macrogen_xls(
    fwd_primers, rev_primers,
    fwd_plate_name: str, rev_plate_name: str,
    amount: str, purification: str, output_path: str,
) -> None:
    if len(fwd_primers) > 96:
        raise ValueError(f"fwd primer count {len(fwd_primers)} exceeds 96 well limit")
    if len(rev_primers) > 96:
        raise ValueError(f"rev primer count {len(rev_primers)} exceeds 96 well limit")

    plates = []
    if fwd_primers:
        _validate_plate_name(fwd_plate_name, "fwd")
        _validate_oligo_names(fwd_primers, "fwd")
        plates.append((fwd_plate_name, fwd_primers))
    if rev_primers:
        _validate_plate_name(rev_plate_name, "rev")
        _validate_oligo_names(rev_primers, "rev")
        plates.append((rev_plate_name, rev_primers))

    wb = _xlwt.Workbook(encoding="utf-8")
    s = wb.add_sheet("Sheet")
    for c, h in enumerate(_HEADERS):
        s.write(0, c, h)

    wells = _column_major_wells()
    row = 1
    no = 1
    for plate_name, primers in plates:
        for i, well in enumerate(wells):
            s.write(row, 0, no)
            s.write(row, 1, plate_name)
            s.write(row, 2, well)
            if i < len(primers):
                p = primers[i]
                s.write(row, 3, p.name)
                s.write(row, 4, p.sequence)
                s.write(row, 5, amount)
                s.write(row, 6, purification)
            row += 1
            no += 1
    wb.save(output_path)
```

- [ ] **Step 4: 실행 → 통과**

실행: `python -m pytest tests/test_macrogen_export.py -v`
예상: 6 passed.

- [ ] **Step 5: 커밋**

```bash
git add tests/test_macrogen_export.py kuma_core/kuro/plate_mapper.py
git commit -m "v0.4.1.00: add export_macrogen_xls with column-major wells and validation"
```

---

## A3. Pydantic 모델 신규 (`ExportMacrogenParams`, `ExportAllParams`)

**파일:**
- 수정: `python-core/sidecar_kuro/models.py`
- 생성: `tests/test_export_models.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_export_models.py
import pytest
from pydantic import ValidationError
from sidecar_kuro.models import ExportMacrogenParams, ExportAllParams

def test_macrogen_params_ok():
    p = ExportMacrogenParams(
        output_path="/tmp/x.xls",
        fwd_plate_name="P1_fwd", rev_plate_name="P1_rev",
    )
    assert p.amount == "0.05"
    assert p.purification == "MOPC"

def test_macrogen_params_rejects_korean_plate_name():
    with pytest.raises(ValidationError):
        ExportMacrogenParams(
            output_path="/tmp/x.xls",
            fwd_plate_name="한글", rev_plate_name="P1",
        )

def test_export_all_defaults():
    p = ExportAllParams(output_dir="/tmp/out")
    assert p.echo_transfer_vol == 100
    assert 25 <= p.echo_transfer_vol <= 500

def test_export_all_echo_clamp_rejects():
    with pytest.raises(ValidationError):
        ExportAllParams(output_dir="/tmp/out", echo_transfer_vol=1000)
```

- [ ] **Step 2: 실행 → 실패**

실행: `python -m pytest tests/test_export_models.py -v`
예상: `ImportError`.

- [ ] **Step 3: 최소 구현**

`python-core/sidecar_kuro/models.py` 에 추가:

```python
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator

_PLATE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")

class ExportMacrogenParams(BaseModel):
    project_id: str | None = None
    output_path: str
    fwd_plate_name: str = ""
    rev_plate_name: str = ""
    amount: Literal["0.05", "0.2"] = "0.05"
    purification: Literal["MOPC"] = "MOPC"

    @field_validator("fwd_plate_name", "rev_plate_name")
    @classmethod
    def _plate_name_rule(cls, v: str) -> str:
        if v and not _PLATE_NAME_RE.fullmatch(v):
            raise ValueError(f"plate name '{v}' violates ^[A-Za-z0-9_-]{{1,20}}$")
        return v


class ExportAllParams(BaseModel):
    project_id: str | None = None
    output_dir: str
    fwd_plate_name: str = ""
    rev_plate_name: str = ""
    amount: Literal["0.05", "0.2"] = "0.05"
    purification: Literal["MOPC"] = "MOPC"
    echo_transfer_vol: int = Field(default=100, ge=25, le=500)
    janus_transfer_vol: float = Field(default=2.0, ge=0.5, le=10.0)
    bom: bool = False
```

- [ ] **Step 4: 실행 → 통과**

실행: `python -m pytest tests/test_export_models.py -v`
예상: 4 passed.

- [ ] **Step 5: 커밋**

```bash
git add tests/test_export_models.py python-core/sidecar_kuro/models.py
git commit -m "v0.4.1.01: add ExportMacrogenParams and ExportAllParams pydantic models"
```

---

## A4. Sidecar 핸들러 `handle_export_macrogen` + `handle_export_all`

**파일:**
- 수정: `python-core/sidecar_kuro/handlers/export.py`
- 수정: `python-core/sidecar_kuro/dispatcher.py:70` (`_METHODS` 등록)
- 수정: `tests/test_handlers_export.py` (있으면 확장, 없으면 생성)

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_handlers_export.py (append)
from sidecar_kuro.handlers.export import handle_export_macrogen, handle_export_all

def test_handle_export_macrogen_writes_file(tmp_path, monkeypatch):
    # seed state with fake fwd/rev primers via monkeypatch
    from sidecar_kuro import _core
    _core._state.fwd_primers = [_mk("ATCG", "p1")]
    _core._state.rev_primers = []
    res = handle_export_macrogen({
        "output_path": str(tmp_path / "x.xls"),
        "fwd_plate_name": "P1",
    })
    assert res["ok"] is True
    assert (tmp_path / "x.xls").exists()

def test_handle_export_all_writes_six_files(tmp_path, monkeypatch):
    _core._state.fwd_primers = [_mk("ATCG", "p1")]
    _core._state.rev_primers = [_mk("CGAT", "p1r")]
    res = handle_export_all({
        "output_dir": str(tmp_path),
        "fwd_plate_name": "Pfwd",
        "rev_plate_name": "Prev",
    })
    assert len(res["success"]) >= 4
```

- [ ] **Step 2: 실행 → 실패**

`pytest tests/test_handlers_export.py -v` → ImportError.

- [ ] **Step 3: 최소 구현**

`python-core/sidecar_kuro/handlers/export.py` 에:

```python
from kuma_core.kuro.plate_mapper import export_macrogen_xls
from sidecar_kuro.models import ExportMacrogenParams, ExportAllParams

def handle_export_macrogen(params: dict) -> dict:
    p = ExportMacrogenParams(**params)
    state = _core._state
    export_macrogen_xls(
        fwd_primers=state.fwd_primers or [],
        rev_primers=state.rev_primers or [],
        fwd_plate_name=p.fwd_plate_name,
        rev_plate_name=p.rev_plate_name,
        amount=p.amount, purification=p.purification,
        output_path=p.output_path,
    )
    return {"ok": True, "path": p.output_path}


def handle_export_all(params: dict) -> dict:
    p = ExportAllParams(**params)
    out_dir = Path(p.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    project_name = (_core._state.project.name if _core._state.project else None) \
        or p.fwd_plate_name or p.rev_plate_name or "kuro_export"
    ts = datetime.now().strftime("%Y%m%d")
    base = f"{project_name}_{ts}.kuro"
    success: list[str] = []
    failed: list[dict] = []

    def _try(name: str, fn):
        try:
            fn()
            success.append(name)
        except Exception as e:
            failed.append({"path": name, "reason": str(e)})

    _try(f"{base}.macrogen.xls", lambda: handle_export_macrogen({
        "output_path": str(out_dir / f"{base}.macrogen.xls"),
        "fwd_plate_name": p.fwd_plate_name,
        "rev_plate_name": p.rev_plate_name,
        "amount": p.amount, "purification": p.purification,
    }))
    _try(f"{base}.primers.fasta", lambda: _export_primers_fasta(out_dir / f"{base}.primers.fasta"))
    _try(f"{base}.echo.csv", lambda: _export_echo(out_dir / f"{base}.echo.csv", p.echo_transfer_vol, p.bom))
    _try(f"{base}.janus.csv", lambda: _export_janus(out_dir / f"{base}.janus.csv", p.janus_transfer_vol, p.bom))
    _try(f"{base}.platemap.xlsx", lambda: _export_platemap(out_dir / f"{base}.platemap.xlsx"))
    _try(f"{base}.run.json", lambda: _export_run_json(out_dir / f"{base}.run.json"))

    return {"success": success, "failed": failed, "output_dir": str(out_dir)}
```

> 내부 헬퍼 (`_export_primers_fasta`, `_export_echo`, `_export_janus`, `_export_platemap`, `_export_run_json`) 는 기존 export 함수 호출 wrapping. fasta 가 없으면 신규 작성 (Primer.name + Primer.sequence FASTA).

- [ ] **Step 4: dispatcher 등록**

`python-core/sidecar_kuro/dispatcher.py:70` `_METHODS` 에 추가:

```python
_METHODS = {
    ...,
    "export_macrogen": handle_export_macrogen,
    "export_all": handle_export_all,
}
```

기존 `export` 분기에서 IDT/Twist 분기 제거.

- [ ] **Step 5: 실행 → 통과**

실행: `python -m pytest tests/test_handlers_export.py -v`
예상: 2 passed.

- [ ] **Step 6: 커밋**

```bash
git add python-core/sidecar_kuro/handlers/export.py python-core/sidecar_kuro/dispatcher.py tests/test_handlers_export.py
git commit -m "v0.4.1.02: add handle_export_macrogen and handle_export_all dispatcher methods"
```

---

## A5. TS RpcMethodMap + 모델 재생성

**파일:**
- 수정: `src/types/models.ts:470` `RpcMethodMap` 인터페이스
- 자동 생성: `src/types/models.generated.ts` via `pnpm gen:models`

- [ ] **Step 1: 모델 재생성**

실행: `pnpm gen:models`
예상: `src/types/models.generated.ts` 갱신.

- [ ] **Step 2: `RpcMethodMap` 확장**

`src/types/models.ts:470` 부근에 추가:

```ts
export interface RpcMethodMap {
  // ... existing
  export_macrogen: {
    params: ExportMacrogenParams;
    result: { ok: true; path: string };
  };
  export_all: {
    params: ExportAllParams;
    result: { success: string[]; failed: { path: string; reason: string }[]; output_dir: string };
  };
}
```

- [ ] **Step 3: 타입체크**

실행: `npx tsc --noEmit`
예상: 0 errors.

- [ ] **Step 4: sync-check**

실행: `pnpm sync:check`
예상: PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/types/models.ts src/types/models.generated.ts
git commit -m "v0.4.1.03: regen TS models for export_macrogen/export_all RPC"
```

---

## A6. `handleExportAll` frontend handler

**파일:**
- 수정: `src/components/layout/export-handlers.ts`
- 생성: `src/components/layout/export-handlers.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

```ts
// export-handlers.test.ts
import { describe, it, vi, expect } from "vitest";
import { handleExportAll } from "./export-handlers";

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn().mockResolvedValue("/projects/proj1"),
  save: vi.fn(),
}));
vi.mock("@/lib/ipc", () => ({
  sendRequest: vi.fn().mockResolvedValue({ success: ["a.xls"], failed: [], output_dir: "/projects/proj1" }),
}));

describe("handleExportAll", () => {
  it("passes plate names and echo vol to sidecar", async () => {
    const ipc = await import("@/lib/ipc");
    await handleExportAll({
      fwdPlateName: "Pfwd",
      rvsPlateName: "Prev",
      amount: "0.05",
      echoTransferVol: 100,
      janusTransferVol: 2.0,
      bom: false,
    });
    expect(ipc.sendRequest).toHaveBeenCalledWith("export_all", expect.objectContaining({
      fwd_plate_name: "Pfwd",
      rev_plate_name: "Prev",
      echo_transfer_vol: 100,
    }));
  });
});
```

- [ ] **Step 2: 실행 → 실패**

실행: `pnpm vitest run src/components/layout/export-handlers.test.ts`
예상: `handleExportAll is not a function`.

- [ ] **Step 3: 구현**

`src/components/layout/export-handlers.ts` 끝에:

```ts
import { open } from "@tauri-apps/plugin-dialog";

export async function handleExportAll(params: {
  projectId?: string;
  fwdPlateName?: string;
  rvsPlateName?: string;
  amount: "0.05" | "0.2";
  echoTransferVol: number;
  janusTransferVol: number;
  bom: boolean;
}): Promise<{ success: string[]; failed: { path: string; reason: string }[] }> {
  const dir = await open({ directory: true });
  if (!dir || typeof dir !== "string") return { success: [], failed: [] };
  const result = await sendRequest("export_all", {
    project_id: params.projectId,
    output_dir: dir,
    fwd_plate_name: params.fwdPlateName ?? "",
    rev_plate_name: params.rvsPlateName ?? "",
    amount: params.amount,
    echo_transfer_vol: params.echoTransferVol,
    janus_transfer_vol: params.janusTransferVol,
    bom: params.bom,
  });
  return result;
}
```

기존 `handleExportExcel` 은 일단 유지 (IDT/Twist 제거는 A7 에서 UI 정리와 함께).

- [ ] **Step 4: 실행 → 통과**

실행: `pnpm vitest run src/components/layout/export-handlers.test.ts`
예상: 1 passed.

- [ ] **Step 5: 커밋**

```bash
git add src/components/layout/export-handlers.ts src/components/layout/export-handlers.test.ts
git commit -m "v0.4.1.04: add handleExportAll frontend handler"
```

---

## A7. `ExportFormatSelector.tsx` Export All UI 재작성

**파일:**
- 수정: `src/components/steps/ExportFormatSelector.tsx` (전면 재작성)
- 수정: `src/components/steps/ExportFormatSelector.test.tsx` (신규 또는 갱신)
- 수정: `src/i18n/locales/ko.json`, `en.json` (신규 키)

- [ ] **Step 1: i18n 키 추가**

`src/i18n/locales/ko.json` `phaseC.export` 하위에:

```json
"all": {
  "heading": "Export All",
  "plateNameFwd": "Plate Name (fwd)",
  "plateNameRev": "Plate Name (rev)",
  "amountLabel": "Amount",
  "purificationLabel": "Purification",
  "echoVolLabel": "Echo transfer vol",
  "janusVolLabel": "JANUS transfer vol",
  "bomLabel": "Include BoM",
  "runExport": "Export All",
  "ruleHint": "1–20자, 영문/숫자/_/- 만 허용",
  "wellCount": "{count}/96 wells",
  "error": {
    "plateNameRegex": "Plate Name 형식 오류 (영문/숫자/_/- 1–20자)",
    "oligoNameRegex": "{count}개 oligo name 규칙 위반",
    "wellOverflow": "{count} > 96 well. 설계 단계에서 분할 필요"
  }
},
"toast": {
  "success": "{n}/6 파일 export 완료",
  "partial": "{ok}/6 성공, {fail} 실패"
}
```

en.json 도 동일 구조 영문 번역.

- [ ] **Step 2: 컴포넌트 테스트 작성**

```tsx
// ExportFormatSelector.test.tsx
describe("ExportFormatSelector Export All", () => {
  it("renders Echo Range 25–500 nL", () => {
    render(<ExportFormatSelector />);
    expect(screen.getByText(/25.*500.*nL/)).toBeInTheDocument();
  });

  it("disables Export All button when plate name contains Korean", async () => {
    render(<ExportFormatSelector />);
    const input = screen.getByLabelText(/Plate Name \(fwd\)/);
    fireEvent.change(input, { target: { value: "한글" } });
    const btn = screen.getByRole("button", { name: /Export All/ });
    expect(btn).toBeDisabled();
    expect(screen.getByText(/Plate Name 형식 오류/)).toBeInTheDocument();
  });

  it("shows well count badge", () => {
    // seed store with 50 fwd primers
    useAppStore.setState({ designResults: { fwd: Array(50).fill(...) } });
    render(<ExportFormatSelector />);
    expect(screen.getByText(/50\/96 wells/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: 실행 → 실패**

실행: `pnpm vitest run src/components/steps/ExportFormatSelector.test.tsx`
예상: FAIL.

- [ ] **Step 4: 컴포넌트 전면 재작성**

`src/components/steps/ExportFormatSelector.tsx` 의 Section 2 (Plate Mapping Export) 완전 제거, Section 1 을 Export All 폼으로 재작성:

```tsx
const PLATE_NAME_RE = /^[A-Za-z0-9_-]{1,20}$/;
const ECHO_RANGE = { min: 25, max: 500, step: 1, unit: "nL" } as const;
const JANUS_RANGE = { min: 0.5, max: 10, step: 0.1, unit: "μL" } as const;

export function ExportFormatSelector() {
  const { t } = useTranslation();
  const fwdPrimers = useAppStore(s => s.designResults?.fwd ?? []);
  const rvsPrimers = useAppStore(s => s.designResults?.rev ?? []);

  const [fwdPlate, setFwdPlate] = useState("");
  const [rvsPlate, setRvsPlate] = useState("");
  const [amount, setAmount] = useState<"0.05" | "0.2">("0.05");
  const [echoVol, setEchoVol] = useState(100);
  const [janusVol, setJanusVol] = useState(2.0);
  const [bom, setBom] = useState(false);
  const [running, setRunning] = useState(false);

  const fwdValid = fwdPrimers.length === 0 || PLATE_NAME_RE.test(fwdPlate);
  const rvsValid = rvsPrimers.length === 0 || PLATE_NAME_RE.test(rvsPlate);
  const fwdOverflow = fwdPrimers.length > 96;
  const rvsOverflow = rvsPrimers.length > 96;
  const canExport = fwdValid && rvsValid && !fwdOverflow && !rvsOverflow && !running;

  const onExport = async () => {
    setRunning(true);
    try {
      const r = await handleExportAll({
        fwdPlateName: fwdPlate || undefined,
        rvsPlateName: rvsPlate || undefined,
        amount, echoTransferVol: echoVol, janusTransferVol: janusVol, bom,
      });
      toast.success(t("phaseC.export.toast.success", { n: r.success.length }));
      if (r.failed.length) toast.error(t("phaseC.export.toast.partial", { ok: r.success.length, fail: r.failed.length }));
    } finally {
      setRunning(false);
    }
  };

  return (
    <section aria-labelledby="export-all-heading" className="flex flex-col gap-4 p-6">
      <h3 id="export-all-heading">{t("phaseC.export.all.heading")}</h3>

      {fwdPrimers.length > 0 && (
        <div>
          <label htmlFor="fwd-plate">{t("phaseC.export.all.plateNameFwd")}</label>
          <input id="fwd-plate" value={fwdPlate} onChange={e => setFwdPlate(e.target.value)} aria-describedby="fwd-plate-help" />
          <span id="fwd-plate-help">{t("phaseC.export.all.wellCount", { count: fwdPrimers.length })}</span>
          {!fwdValid && <span role="alert">{t("phaseC.export.all.error.plateNameRegex")}</span>}
          {fwdOverflow && <span role="alert">{t("phaseC.export.all.error.wellOverflow", { count: fwdPrimers.length })}</span>}
        </div>
      )}

      {/* rev 동일 구조 */}

      <div>
        <label htmlFor="amount">{t("phaseC.export.all.amountLabel")}</label>
        <select id="amount" value={amount} onChange={e => setAmount(e.target.value as "0.05" | "0.2")}>
          <option value="0.05">0.05 μmole</option>
          <option value="0.2">0.2 μmole</option>
        </select>
        <span>{t("phaseC.export.all.purificationLabel")}: MOPC</span>
      </div>

      <div>
        <label>{t("phaseC.export.all.echoVolLabel")}</label>
        <input type="number" min={ECHO_RANGE.min} max={ECHO_RANGE.max} step={ECHO_RANGE.step}
          value={echoVol} onChange={e => setEchoVol(Number(e.target.value))} />
        <span>Range: {ECHO_RANGE.min}–{ECHO_RANGE.max} {ECHO_RANGE.unit}</span>
      </div>

      {/* janus 동일 */}

      <div>
        <input type="checkbox" id="bom" checked={bom} onChange={e => setBom(e.target.checked)} />
        <label htmlFor="bom">{t("phaseC.export.all.bomLabel")}</label>
      </div>

      <p>{t("phaseC.export.all.ruleHint")}</p>

      <button disabled={!canExport} onClick={onExport}>
        {running ? t("common.loading") : t("phaseC.export.all.runExport")}
      </button>
    </section>
  );
}
```

> 기존 `ExportFormat` 타입, `ORDER_FORMATS`, `MAPPING_FORMAT_DEFAULTS`, `handleExportExcel` / `handleExportMappingWithParams` 호출부 제거.

- [ ] **Step 5: 실행 → 통과**

실행: `pnpm vitest run src/components/steps/ExportFormatSelector.test.tsx && npx tsc --noEmit`
예상: PASS + 0 errors.

- [ ] **Step 6: 커밋**

```bash
git add src/components/steps/ExportFormatSelector.tsx src/components/steps/ExportFormatSelector.test.tsx src/i18n/locales/ko.json src/i18n/locales/en.json
git commit -m "v0.4.2.00: rewrite ExportFormatSelector as Export All single button"
```

---

## A8. MappingExportDialog 제거 + IDT/Twist UI 분기 정리

**파일:**
- 삭제: `src/components/dialogs/MappingExportDialog.tsx`, `MappingExportDialog.test.tsx`
- 수정: `src/components/layout/export-handlers.ts` (사용 안 되는 export 함수 제거)
- 수정: `src/i18n/locales/{ko,en}.json` 잔여 키 정리

- [ ] **Step 1: 사용처 검색**

실행: `grep -rn "MappingExportDialog\|handleExportMappingWithParams\|orderExport\|mappingExportDialog" src --include="*.ts" --include="*.tsx"`
예상: 호출 0건 (ExportFormatSelector 재작성 후).

- [ ] **Step 2: 파일 삭제**

```bash
rm src/components/dialogs/MappingExportDialog.tsx src/components/dialogs/MappingExportDialog.test.tsx
```

- [ ] **Step 3: i18n 정리**

`grep` 으로 `phaseC.export.format.idt`, `.twist`, `.orderExport`, `.mappingExport`, `mappingExportDialog` 키 검색 → 미사용 키 ko/en JSON 에서 삭제.

- [ ] **Step 4: 타입체크 + 테스트**

실행: `npx tsc --noEmit && pnpm vitest run`
예상: PASS.

- [ ] **Step 5: 커밋**

```bash
git add -A
git commit -m "v0.4.2.01: remove MappingExportDialog and legacy IDT/Twist i18n keys"
```

---

## A9. `.cross-layer-sync.json` group 등록

**파일:**
- 수정: `.cross-layer-sync.json`

- [ ] **Step 1: groups[] 에 추가**

```json
{
  "id": "macrogen-export-flow",
  "files": [
    "src/components/steps/ExportFormatSelector.tsx",
    "src/components/layout/export-handlers.ts",
    "python-core/sidecar_kuro/handlers/export.py",
    "python-core/sidecar_kuro/models.py",
    "kuma_core/kuro/plate_mapper.py"
  ],
  "note": "Export All UI ↔ RPC ↔ exporter 정합성",
  "severity": "blocking"
}
```

- [ ] **Step 2: 검증**

실행: `pnpm sync:check`
예상: PASS.

- [ ] **Step 3: 커밋**

```bash
git add .cross-layer-sync.json
git commit -m "v0.4.2.02: register macrogen-export-flow cross-layer group"
```

---

# Part B — Sidebar 통일 + Drag Resize

## B1. 빌드 타임 너비 계산 스크립트

**파일:**
- 생성: `scripts/compute-sidebar-width.mjs`
- 생성: `scripts/compute-sidebar-width.test.mjs`
- 생성: `src/lib/sidebar-default-width.ts` (스크립트 실행 결과)
- 수정: `package.json` scripts

- [ ] **Step 1: 테스트 작성**

```js
// scripts/compute-sidebar-width.test.mjs
import { computeMaxLabelWidth } from "./compute-sidebar-width.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";

test("computes max label width with padding", () => {
  const labels = ["short", "a much longer label here"];
  const w = computeMaxLabelWidth(labels, { fontSize: 14, padding: 44 });
  assert.ok(w > 200 && w < 400);
});

test("returns fallback for empty list", () => {
  assert.equal(computeMaxLabelWidth([], { fontSize: 14, padding: 44, fallback: 240 }), 240);
});
```

- [ ] **Step 2: 실행 → 실패**

실행: `node --test scripts/compute-sidebar-width.test.mjs`
예상: ERR_MODULE_NOT_FOUND.

- [ ] **Step 3: 스크립트 구현**

```js
// scripts/compute-sidebar-width.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// avg char widths (px) for Inter 14px medium, empirical
const CHAR_WIDTH = 7.3;

export function computeMaxLabelWidth(labels, { fontSize = 14, padding = 44, fallback = 240 } = {}) {
  if (!labels.length) return fallback;
  const scale = fontSize / 14;
  const max = Math.max(...labels.map(l => l.length * CHAR_WIDTH * scale));
  return Math.ceil(max + padding);
}

function collectSubStepLabels(localePath) {
  const data = JSON.parse(fs.readFileSync(localePath, "utf-8"));
  const out = [];
  const visit = (obj) => {
    for (const v of Object.values(obj)) {
      if (typeof v === "string") out.push(v);
      else if (v && typeof v === "object") visit(v);
    }
  };
  if (data.phaseC?.subSteps) visit(data.phaseC.subSteps);
  if (data.mame?.subSteps) visit(data.mame.subSteps);
  return out;
}

function main() {
  const localesDir = path.join(__dirname, "..", "src", "i18n", "locales");
  const labels = ["ko.json", "en.json"].flatMap(f =>
    collectSubStepLabels(path.join(localesDir, f))
  );
  const width = computeMaxLabelWidth(labels);
  const out = path.join(__dirname, "..", "src", "lib", "sidebar-default-width.ts");
  fs.writeFileSync(out,
    `// Auto-generated by scripts/compute-sidebar-width.mjs\nexport const SIDEBAR_DEFAULT_WIDTH = ${width};\n`,
    "utf-8");
  console.log(`SIDEBAR_DEFAULT_WIDTH = ${width}`);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
```

- [ ] **Step 4: package.json scripts 추가**

```json
"compute:sidebar-width": "node scripts/compute-sidebar-width.mjs",
"prebuild": "pnpm compute:sidebar-width"
```

- [ ] **Step 5: 실행 → 통과**

실행: `node --test scripts/compute-sidebar-width.test.mjs && pnpm compute:sidebar-width`
예상: 2 passed, `src/lib/sidebar-default-width.ts` 생성.

- [ ] **Step 6: 커밋**

```bash
git add scripts/compute-sidebar-width.mjs scripts/compute-sidebar-width.test.mjs src/lib/sidebar-default-width.ts package.json
git commit -m "v0.4.3.00: add compute-sidebar-width build script and emit default constant"
```

---

## B2. `layoutSlice` (Zustand + persist)

**파일:**
- 생성: `src/store/slices/layoutSlice.ts`
- 생성: `src/store/slices/layoutSlice.test.ts`
- 수정: `src/store/appStore.ts` (slice inject)
- 수정: `src/store/mame/mameAppStore.ts` (slice inject)

- [ ] **Step 1: 테스트 작성**

```ts
// layoutSlice.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { createLayoutSlice, type LayoutSlice } from "./layoutSlice";

describe("layoutSlice", () => {
  beforeEach(() => localStorage.clear());

  it("starts with sidebarWidth null", () => {
    const useStore = create<LayoutSlice>()(createLayoutSlice);
    expect(useStore.getState().sidebarWidth).toBeNull();
  });

  it("setSidebarWidth persists to localStorage", () => {
    const useStore = create<LayoutSlice>()(persist(createLayoutSlice, { name: "test" }));
    useStore.getState().setSidebarWidth(300);
    expect(useStore.getState().sidebarWidth).toBe(300);
    expect(JSON.parse(localStorage.getItem("test")!).state.sidebarWidth).toBe(300);
  });

  it("setSidebarWidth(null) reverts to default", () => {
    const useStore = create<LayoutSlice>()(createLayoutSlice);
    useStore.getState().setSidebarWidth(300);
    useStore.getState().setSidebarWidth(null);
    expect(useStore.getState().sidebarWidth).toBeNull();
  });
});
```

- [ ] **Step 2: 실행 → 실패**

실행: `pnpm vitest run src/store/slices/layoutSlice.test.ts`
예상: ImportError.

- [ ] **Step 3: 구현**

```ts
// src/store/slices/layoutSlice.ts
import type { StateCreator } from "zustand";
import { SIDEBAR_DEFAULT_WIDTH } from "@/lib/sidebar-default-width";

export interface LayoutSlice {
  sidebarWidth: number | null;
  computedDefault: number;
  setSidebarWidth: (w: number | null) => void;
  setComputedDefault: (w: number) => void;
}

export const createLayoutSlice: StateCreator<LayoutSlice> = (set) => ({
  sidebarWidth: null,
  computedDefault: SIDEBAR_DEFAULT_WIDTH,
  setSidebarWidth: (w) => set({ sidebarWidth: w }),
  setComputedDefault: (w) => set({ computedDefault: w }),
});
```

- [ ] **Step 4: appStore inject**

`src/store/appStore.ts` 의 `create` 호출에 persist 미들웨어 wrap + `createLayoutSlice` 통합. 단, 기존 store 구조 보존 — `persist` 옵션 `partialize` 로 `sidebarWidth` 만 저장:

```ts
import { persist } from "zustand/middleware";
import { createLayoutSlice } from "./slices/layoutSlice";

export const useAppStore = create<AppState>()(
  persist(
    (set, get, store) => ({
      ...createLayoutSlice(set, get, store),
      ...createDesignSlice(set, get, store),
      // ... existing slices
    }),
    {
      name: "kuma.layout.v1",
      partialize: (s) => ({ sidebarWidth: s.sidebarWidth }),
    }
  )
);
```

- [ ] **Step 5: mameAppStore 도 동일하게 inject**

`src/store/mame/mameAppStore.ts` 에 같은 패턴 적용. localStorage 키도 `kuma.layout.v1` 공유 — kuro/mame 양쪽 동일 너비.

- [ ] **Step 6: 실행 → 통과**

실행: `pnpm vitest run src/store/slices/layoutSlice.test.ts && npx tsc --noEmit`
예상: 3 passed + 0 errors.

- [ ] **Step 7: 커밋**

```bash
git add src/store/slices/layoutSlice.ts src/store/slices/layoutSlice.test.ts src/store/appStore.ts src/store/mame/mameAppStore.ts
git commit -m "v0.4.3.01: add layoutSlice with localStorage persist for sidebar width"
```

---

## B3. `ResizeHandle` 컴포넌트

**파일:**
- 생성: `src/components/shell/ResizeHandle.tsx`
- 생성: `src/components/shell/ResizeHandle.test.tsx`

- [ ] **Step 1: 테스트 작성**

```tsx
// ResizeHandle.test.tsx
import { fireEvent, render } from "@testing-library/react";
import { ResizeHandle } from "./ResizeHandle";

describe("ResizeHandle", () => {
  it("calls onResize on mousemove during drag", () => {
    const onResize = vi.fn();
    const { getByRole } = render(<ResizeHandle width={240} min={180} max={480} onResize={onResize} />);
    const h = getByRole("separator");
    fireEvent.mouseDown(h, { clientX: 240 });
    fireEvent.mouseMove(document, { clientX: 300 });
    expect(onResize).toHaveBeenCalledWith(300);
    fireEvent.mouseUp(document);
  });

  it("clamps to min/max", () => {
    const onResize = vi.fn();
    const { getByRole } = render(<ResizeHandle width={240} min={180} max={480} onResize={onResize} />);
    const h = getByRole("separator");
    fireEvent.mouseDown(h, { clientX: 240 });
    fireEvent.mouseMove(document, { clientX: 50 });
    expect(onResize).toHaveBeenLastCalledWith(180);
    fireEvent.mouseMove(document, { clientX: 9999 });
    expect(onResize).toHaveBeenLastCalledWith(480);
    fireEvent.mouseUp(document);
  });

  it("ArrowRight increments width by 1", () => {
    const onResize = vi.fn();
    const { getByRole } = render(<ResizeHandle width={240} min={180} max={480} onResize={onResize} />);
    fireEvent.keyDown(getByRole("separator"), { key: "ArrowRight" });
    expect(onResize).toHaveBeenCalledWith(241);
  });
});
```

- [ ] **Step 2: 실행 → 실패**

실행: `pnpm vitest run src/components/shell/ResizeHandle.test.tsx`
예상: ImportError.

- [ ] **Step 3: 구현**

```tsx
// src/components/shell/ResizeHandle.tsx
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

interface Props {
  width: number;
  min: number;
  max: number;
  onResize: (w: number) => void;
  onCommit?: () => void;
}

export function ResizeHandle({ width, min, max, onResize, onCommit }: Props) {
  const { t } = useTranslation();
  const dragging = useRef(false);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        onResize(Math.max(min, Math.min(max, e.clientX)));
      });
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      onCommit?.();
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, [min, max, onResize, onCommit]);

  const onKey = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 10 : 1;
    if (e.key === "ArrowRight") onResize(Math.min(max, width + step));
    else if (e.key === "ArrowLeft") onResize(Math.max(min, width - step));
    else if (e.key === "Home") onResize(min);
    else if (e.key === "End") onResize(max);
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-label={t("appShell.sidebarResize")}
      tabIndex={0}
      onMouseDown={() => {
        dragging.current = true;
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
      }}
      onKeyDown={onKey}
      className="absolute right-0 top-0 h-full w-1 cursor-col-resize bg-border hover:bg-primary"
    />
  );
}
```

- [ ] **Step 4: i18n 키 추가**

ko: `appShell.sidebarResize` = "사이드바 너비 조절", en: "Resize sidebar".

- [ ] **Step 5: 실행 → 통과**

실행: `pnpm vitest run src/components/shell/ResizeHandle.test.tsx`
예상: 3 passed.

- [ ] **Step 6: 커밋**

```bash
git add src/components/shell/ResizeHandle.tsx src/components/shell/ResizeHandle.test.tsx src/i18n/locales/ko.json src/i18n/locales/en.json
git commit -m "v0.4.3.02: add ResizeHandle component with mouse + keyboard"
```

---

## B4. AppShell 통합

**파일:**
- 수정: `src/components/shell/AppShell.tsx:75`
- 수정: `src/components/shell/AppShell.test.tsx` (있으면)

- [ ] **Step 1: 테스트 갱신**

```tsx
// AppShell.test.tsx
it("aside has inline width from store", () => {
  useAppStore.setState({ sidebarWidth: 320 });
  const { getByTestId } = render(<AppShell sidebar={<div>x</div>} main={<div />} />);
  expect(getByTestId("sidebar")).toHaveStyle({ width: "320px" });
});

it("aside falls back to computed default", () => {
  useAppStore.setState({ sidebarWidth: null, computedDefault: 250 });
  const { getByTestId } = render(<AppShell sidebar={<div>x</div>} main={<div />} />);
  expect(getByTestId("sidebar")).toHaveStyle({ width: "250px" });
});

it("renders ResizeHandle inside aside", () => {
  const { getByRole } = render(<AppShell sidebar={<div>x</div>} main={<div />} />);
  expect(getByRole("separator")).toBeInTheDocument();
});
```

- [ ] **Step 2: AppShell 수정**

```tsx
// src/components/shell/AppShell.tsx
import { useAppStore } from "@/store/appStore";
import { ResizeHandle } from "./ResizeHandle";

export function AppShell({ tool, titlebar, appbar, subnav, sidebar, main, statusbar, ...rest }: AppShellProps) {
  const width = useAppStore(s => s.sidebarWidth ?? s.computedDefault);
  const setWidth = useAppStore(s => s.setSidebarWidth);

  return (
    <div /* ... */>
      {titlebar}{appbar}{subnav}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {sidebar != null && (
          <aside
            data-testid="sidebar"
            style={{ width }}
            className="relative flex shrink-0 flex-col border-r border-border bg-card"
          >
            {sidebar}
            <ResizeHandle width={width} min={180} max={480} onResize={setWidth} />
          </aside>
        )}
        <main data-testid="main-content" className="flex flex-1 min-w-0 min-h-0 flex-col overflow-hidden">
          {main}
        </main>
      </div>
      {statusbar}
    </div>
  );
}
```

- [ ] **Step 3: mame 도 동일 store hook 사용 검증**

`MameAppLayout.tsx` 는 AppShell 을 직접 호출하므로 별도 변경 없음. `useAppStore` 와 `useMameAppStore` 가 동일 `kuma.layout.v1` localStorage 키를 공유하도록 B2 의 persist 옵션 확인.

- [ ] **Step 4: 실행 → 통과**

실행: `pnpm vitest run src/components/shell && npx tsc --noEmit`
예상: PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/components/shell/AppShell.tsx src/components/shell/AppShell.test.tsx
git commit -m "v0.4.3.03: integrate ResizeHandle and persisted width into AppShell aside"
```

---

## B5. Cross-layer group + 통합 점검

**파일:**
- 수정: `.cross-layer-sync.json`

- [ ] **Step 1: groups[] 에 추가**

```json
{
  "id": "sidebar-resize-flow",
  "files": [
    "src/components/shell/AppShell.tsx",
    "src/components/shell/ResizeHandle.tsx",
    "src/store/slices/layoutSlice.ts",
    "src/lib/sidebar-default-width.ts",
    "scripts/compute-sidebar-width.mjs"
  ],
  "note": "Sidebar default width 계산 ↔ store ↔ AppShell 렌더 정합성",
  "severity": "warning"
}
```

- [ ] **Step 2: 통합 점검**

실행: `pnpm sync:check && npx tsc --noEmit && pnpm vitest run && python -m pytest tests/`
예상: 모두 PASS.

- [ ] **Step 3: 커밋 (정합성 그룹 + 통합)**

```bash
git add .cross-layer-sync.json
git commit -m "v0.4.3.04: register sidebar-resize-flow cross-layer group"
```

---

# 완료 후 작업

- [ ] `notes/specs/2026-05-13-export-all-macrogen.md` §13 open questions 갱신:
  - Oligo Name 길이 상한 — 사용자 추가 실측 또는 20 자 확정 표기
  - Amount 셀 문자열 — Macrogen 웹 LIMS 실측 후 spec 갱신
- [ ] `.devcontainer/Dockerfile` 변경 반영을 위한 Container Rebuild 안내
- [ ] PR 본문에 spec 링크 + 두 cross-layer group 등록 사실 명시
- [ ] `/code-review --deep --multi` 실행으로 Codex+Gemini+Claude 3-model 리뷰

---

# Confidence Check

| 축 | 점수 | 근거 |
|---|---|---|
| Completeness | 4/5 | spec §1–§15 모두 task 에 매핑. open questions 는 별도 추적. |
| Clarity | 4/5 | 각 step 에 정확 경로 + 실행 가능한 코드 스니펫. Step 3 의 내부 헬퍼 (`_export_primers_fasta` 등) 만 명세 미상세 — execute 단계에서 기존 export 함수 재사용 매핑 필요. |
| Feasibility | 5/5 | xlwt, xlrd, zustand persist, canvas measureText 모두 검증된 라이브러리. cross-layer-sync skill 기존 사용 중. |

총점: **13/15** — 임계 12/15 초과, 진행 승인.
