"""What the flow cell had, and whether this run folder is its second outing.

Three numbers decide whether a run could have worked before anything is scored,
and none of them were being read. A campaign was sequenced on a cell that
started with forty pores and produced four reads per well, and the app drew a
ninety-six-well verdict table over it. Nothing in that table was wrong in a way
the operator could see, because every cell in it was equally meaningless.

The pore counts live in ``report_*.json``, which MAME ignored: MinKNOW records
one mux scan per period and each carries ``counts.single_pore``. Measured
against a real run (FBF10847, FLO-MIN114, nine scans over 45047 s) the first
scan is the number an operator reads as "starting pores" and the last is
"ending pores". The first scan is NOT a flow cell check: it happens after the
library is loaded (t = 211 s in that run), so it dates the run rather than
preventing it. Prevention is the pre-run check on the instrument; this is for
saying afterwards that the run never had a chance.

Reuse is the other half. A washed cell keeps its id, so the same
``flow_cell_id`` appearing in two run folders is the one signal that says "this
is the second campaign on this cell", and Oxford Nanopore excludes post-wash
checks from the pore warranty, which is why the count is worth reporting next
to it. The ledger is written by the sidecar at the project root rather than by
the frontend: a dot-prefixed path would need its own ``fs:scope`` entry
(``src-tauri/capabilities/default.json``), and this file has no reason to be
hidden.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Minimum active pores Oxford Nanopore warrants for a MinION/GridION flow cell
#: at the pre-run check (PromethION is 5000, Flongle 50). Not a success
#: threshold and not ours to set: it is the number below which an unused cell is
#: replaced, so a run that started under it started outside the guarantee.
#: https://nanoporetech.com/support/customer-support/warranty-and-storage/flow-cell-warranty-and-storage
MINION_WARRANTY_PORES = 800

#: Where the ledger lives, relative to the project root.
FLOW_CELL_LEDGER_NAME = "mame_flowcells.json"


@dataclass
class PoreScan:
    """One mux scan: seconds into the acquisition, and pores it found."""

    at_seconds: int
    single_pore: int


@dataclass
class FlowCellHistory:
    """What this run folder says about the cell it was sequenced on."""

    flow_cell_id: str | None = None
    product_code: str | None = None
    channel_count: int | None = None
    #: Mux scans in acquisition order. Empty when no report json was readable,
    #: which is the ordinary case for a folder that never carried one.
    scans: list[PoreScan] = field(default_factory=list)

    @property
    def pore_start(self) -> int | None:
        """Pores at the first mux scan, the "starting pores" an operator reads."""
        return self.scans[0].single_pore if self.scans else None

    @property
    def pore_end(self) -> int | None:
        """Pores at the last mux scan."""
        return self.scans[-1].single_pore if self.scans else None


def read_flow_cell_history(run_dir: Path) -> FlowCellHistory:
    """Read pore counts and cell identity from a MinKNOW ``report_*.json``.

    Best-effort in the same sense as the rest of ``health.py``: a folder with no
    report, a truncated one, or a schema that moved comes back empty rather than
    raising, because none of this is worth failing a run over. The caller
    distinguishes "no data" from "bad data" by asking whether ``scans`` is
    empty, so a silent zero can never be read as a measurement.
    """
    history = FlowCellHistory()
    try:
        reports = sorted(run_dir.glob("report_*.json"))
        if not reports:
            return history
        data = json.loads(reports[0].read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return history

    flow_cell = ((data.get("protocol_run_info") or {}).get("flow_cell")) or {}
    if isinstance(flow_cell, dict):
        history.flow_cell_id = flow_cell.get("flow_cell_id") or None
        history.product_code = flow_cell.get("product_code") or None
        count = flow_cell.get("channel_count")
        history.channel_count = int(count) if isinstance(count, int) else None

    # Scans hang off whichever acquisition actually sequenced; the earlier ones
    # in a run folder are calibration and carry none, so every acquisition is
    # read and the results concatenated in order rather than picking one by
    # index.
    for acquisition in data.get("acquisitions") or []:
        if not isinstance(acquisition, dict):
            continue
        bream = (
            (acquisition.get("acquisition_run_info") or {}).get("bream_info")
        ) or {}
        for scan in (bream.get("mux_scan_results") or []):
            if not isinstance(scan, dict):
                continue
            pores = (scan.get("counts") or {}).get("single_pore")
            if not isinstance(pores, int):
                continue
            stamp = scan.get("mux_scan_timestamp")
            history.scans.append(
                PoreScan(
                    at_seconds=int(stamp) if isinstance(stamp, (int, float)) else 0,
                    single_pore=pores,
                )
            )
    return history


def read_ledger(project_root: Path) -> list[dict]:
    """Every run this project has recorded, oldest first. Missing file is empty."""
    path = project_root / FLOW_CELL_LEDGER_NAME
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def find_previous_use(
    ledger: list[dict], flow_cell_id: str | None, run_dir: str
) -> dict | None:
    """The most recent earlier entry for this cell, or ``None``.

    Matching excludes the run being analysed by its own directory, so
    re-analysing one folder twice never reports itself as a reuse. That is the
    whole difference between "this cell carried an earlier campaign" and "this
    campaign was scored twice", and conflating them would make the warning fire
    on every repeat analysis until nobody read it.
    """
    if not flow_cell_id:
        return None
    for entry in reversed(ledger):
        if entry.get("flow_cell_id") != flow_cell_id:
            continue
        if str(entry.get("run_dir") or "") == str(run_dir):
            continue
        return entry
    return None


def record_use(
    project_root: Path,
    history: FlowCellHistory,
    run_dir: str,
    started: str | None,
) -> None:
    """Append this run to the ledger, replacing any entry for the same folder.

    Re-analysing a folder updates its entry instead of adding one, so the ledger
    counts campaigns rather than analyse clicks. Failure to write is swallowed:
    a read-only project directory is a reason to lose the warning, not the run.
    """
    if not history.flow_cell_id:
        return
    entries = [
        e for e in read_ledger(project_root) if str(e.get("run_dir") or "") != str(run_dir)
    ]
    entries.append(
        {
            "flow_cell_id": history.flow_cell_id,
            "product_code": history.product_code,
            "run_dir": str(run_dir),
            "started": started,
            "pore_start": history.pore_start,
            "pore_end": history.pore_end,
        }
    )
    try:
        (project_root / FLOW_CELL_LEDGER_NAME).write_text(
            json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        return


def serialise_history(history: FlowCellHistory) -> dict:
    """The history as the analyze response carries it."""
    return {
        "flow_cell_id": history.flow_cell_id,
        "product_code": history.product_code,
        "channel_count": history.channel_count,
        "pore_start": history.pore_start,
        "pore_end": history.pore_end,
        "scans": [asdict(scan) for scan in history.scans],
    }


__all__ = [
    "FLOW_CELL_LEDGER_NAME",
    "MINION_WARRANTY_PORES",
    "FlowCellHistory",
    "PoreScan",
    "find_previous_use",
    "read_flow_cell_history",
    "read_ledger",
    "record_use",
    "serialise_history",
]
