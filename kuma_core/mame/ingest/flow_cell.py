"""What the flow cell had, and whether this run folder is its second outing.

Pore counts live in report_*.json. Each mux scan carries counts.single_pore;
the first and last scans supply the start and end values reported here.
These are run measurements, not a replacement for the instrument pre-run
flow-cell check. Per-well depth is assessed separately.

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
import math
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


def find_report_json(run_dir: Path) -> Path | None:
    """The MinKNOW ``report_*.json`` for this input, or ``None``.

    The run folder, then one level up. A raw MinKNOW run is analysed with the
    run folder itself as the input, so the report sits right there. A
    consensus-directory run is analysed with `consensus/` as the input, and that
    directory lives inside the run folder MinKNOW wrote, so the report is one
    level above it. Two candidates rather than a recursive walk: the file has a
    fixed home in a MinKNOW folder, and searching further would start picking up
    reports from unrelated runs stored nearby.

    ``Path.glob`` on a directory that does not exist yields nothing, which is
    the same answer as a directory that holds no report and needs no separate
    handling. Shared with :mod:`kuma_core.mame.ingest.read_length`, which reads
    other parts of the same file: one search rather than two, so the two readers
    can never disagree about which report a run has.
    """
    for candidate in (run_dir, run_dir.parent):
        reports = sorted(candidate.glob("report_*.json"))
        if reports:
            return reports[0]
    return None


def _scan_seconds(stamp: object) -> int | None:
    """Seconds into the acquisition for one mux scan, or ``None`` if unreadable.

    MinKNOW writes ``mux_scan_timestamp`` as a string of digits (``"120"``), so
    a numeric string is the ordinary case and not a malformed one. An absent
    stamp is an older report and reads as zero. Anything that is not a finite,
    non-negative number is refused, and the caller drops that scan.
    """
    if stamp is None:
        return 0
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float, str)):
        return None
    try:
        seconds = float(stamp)
    except ValueError:
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return int(seconds)


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
        report = find_report_json(run_dir)
        if report is None:
            return history
        data = json.loads(report.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return history

    if not isinstance(data, dict):
        return history

    protocol = data.get("protocol_run_info")
    flow_cell = protocol.get("flow_cell") if isinstance(protocol, dict) else None
    if isinstance(flow_cell, dict):
        cell_id = flow_cell.get("flow_cell_id")
        product = flow_cell.get("product_code")
        history.flow_cell_id = cell_id if isinstance(cell_id, str) and cell_id else None
        history.product_code = product if isinstance(product, str) and product else None
        count = flow_cell.get("channel_count")
        history.channel_count = count if type(count) is int and count >= 0 else None

    # Optional report JSON is not a schema guarantee. Validate each container
    # before traversing it and retain only well-formed measurements.
    acquisitions = data.get("acquisitions")
    for acquisition in acquisitions if isinstance(acquisitions, list) else []:
        if not isinstance(acquisition, dict):
            continue
        info = acquisition.get("acquisition_run_info")
        if not isinstance(info, dict):
            continue
        bream = info.get("bream_info")
        if not isinstance(bream, dict):
            continue
        scans = bream.get("mux_scan_results")
        for scan in scans if isinstance(scans, list) else []:
            if not isinstance(scan, dict):
                continue
            counts = scan.get("counts")
            if not isinstance(counts, dict):
                continue
            pores = counts.get("single_pore")
            if type(pores) is not int or pores < 0:
                continue
            seconds = _scan_seconds(scan.get("mux_scan_timestamp"))
            if seconds is None:
                continue
            history.scans.append(PoreScan(at_seconds=seconds, single_pore=pores))
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
    ledger: list[dict],
    flow_cell_id: str | None,
    run_dir: str,
    *,
    former_run_dir: str | None = None,
) -> dict | None:
    """The most recent earlier entry for this cell, or ``None``.

    Matching excludes the run being analysed by its own directory, so
    re-analysing one folder twice never reports itself as a reuse. That is the
    whole difference between "this cell carried an earlier campaign" and "this
    campaign was scored twice", and conflating them would make the warning fire
    on every repeat analysis until nobody read it.

    ``former_run_dir`` is a second name the same run may already be recorded
    under. A raw run was once recorded by its demux output directory and is now
    recorded by the run folder, so a ledger written before that change holds
    this very run under the older name.
    """
    if not flow_cell_id:
        return None
    own = {str(run_dir)} | ({str(former_run_dir)} if former_run_dir else set())
    for entry in reversed(ledger):
        if entry.get("flow_cell_id") != flow_cell_id:
            continue
        if str(entry.get("run_dir") or "") in own:
            continue
        return entry
    return None


def record_use(
    project_root: Path,
    history: FlowCellHistory,
    run_dir: str,
    started: str | None,
    *,
    former_run_dir: str | None = None,
) -> None:
    """Append this run to the ledger, replacing any entry for the same folder.

    Re-analysing a folder updates its entry instead of adding one, so the ledger
    counts campaigns rather than analyse clicks. Failure to write is swallowed:
    a read-only project directory is a reason to lose the warning, not the run.
    An entry under ``former_run_dir`` is this run under its older name (see
    :func:`find_previous_use`) and is replaced the same way.
    """
    if not history.flow_cell_id:
        return
    own = {str(run_dir)} | ({str(former_run_dir)} if former_run_dir else set())
    entries = [e for e in read_ledger(project_root) if str(e.get("run_dir") or "") not in own]
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
    "find_report_json",
    "read_flow_cell_history",
    "read_ledger",
    "record_use",
    "serialise_history",
]
