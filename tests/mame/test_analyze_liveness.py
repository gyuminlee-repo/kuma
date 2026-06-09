"""Liveness instrumentation for the MAME analyze phase (PR#2a).

Three behaviours are verified:

1. ``run_analyze`` invokes the optional ``progress_callback`` monotonically,
   once per record, with the final call carrying ``index == total``.
2. ``handle_analyze`` now emits intermediate progress values strictly between
   60 and 85 (the formerly silent classify-verdicts black box), so the
   frontend ETA advances instead of freezing at 60 %.
3. The keep-alive heartbeat thread starts, emits during an otherwise-silent
   long run, and is cleanly joined afterwards (no thread leak).

Fixtures are self-contained barcode-mode consensus FASTA (no minimap2 needed):
analyze operates on already-consensus records, so ``route_ingest`` reads the
FASTA directly.
"""

from __future__ import annotations

import time
from pathlib import Path

import openpyxl
import pytest

# Reference: ATG GGG TTT -> M G F (9 bp, table 11).
_REFERENCE_NT = "ATGGGGTTT"
# Per-well single-substitution consensus sequences (kept byte-identical to the
# scoping-test fixtures so the ingest contract is shared, not re-invented).
_G2A_NT = "ATGGCGTTT"  # well A02, custom_barcode "1_2"
_F3W_NT = "ATGGGGTGG"  # well B01, custom_barcode "2_1"
# Padding to clear the default 50 KB file-size threshold.
_PAD = "\n" * (52 * 1024)


def _write_fasta(path: Path, header: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f">{header}\n{body}\n{_PAD}", encoding="utf-8")


def _make_kuro_xlsx(dest: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Fwd List"
    ws.append(["Well", "Primer Name", "Sequence", "Length", "Tm", "Tm_Overlap",
               "WT_Codon", "MT_Codon", "Mutation"])
    ws.append(["A1", "G2A_F", "ATGNNNNNNNN", 11, 60.0, 40.0, "GGG", "GCG", "G2A"])
    ws.append(["B1", "F3W_F", "ATGNNNNNNNN", 11, 60.0, 40.0, "TTT", "TGG", "F3W"])
    ws2 = wb.create_sheet("expected_mutations")
    ws2.append(["mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
                "group_id", "primer_set_ref", "notation_type", "status"])
    ws2.append(["G2A", 2, "G", "A", "GGG", "GCG", "", "G2A", "substitution", "DESIGNED"])
    ws2.append(["F3W", 3, "F", "W", "TTT", "TGG", "", "F3W", "substitution", "DESIGNED"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)


def _make_input_dir(tmp_path: Path, n_extra_copies: int = 0) -> Path:
    """Barcode-mode ingest dir with two base wells (+ optional extra copies).

    Extra copies live under additional native-barcode dirs so they parse as
    distinct records, padding the per-record loop for richer sub-progress.
    """
    ingest_dir = tmp_path / "consensus"
    _write_fasta(ingest_dir / "NB01" / "1_2.fasta", header="1_2", body=_G2A_NT)
    _write_fasta(ingest_dir / "NB01" / "2_1.fasta", header="2_1", body=_F3W_NT)
    for k in range(n_extra_copies):
        nb = f"NB{k + 2:02d}"
        _write_fasta(ingest_dir / nb / "1_2.fasta", header="1_2", body=_G2A_NT)
        _write_fasta(ingest_dir / nb / "2_1.fasta", header="2_1", body=_F3W_NT)
    return ingest_dir


def _make_reference_fasta(tmp_path: Path) -> Path:
    ref = tmp_path / "reference.fasta"
    ref.write_text(f">ref\n{_REFERENCE_NT}\n", encoding="utf-8")
    return ref


# ---------------------------------------------------------------------------
# 1. run_analyze invokes progress_callback monotonically per record
# ---------------------------------------------------------------------------

def test_run_analyze_invokes_progress_callback_per_record(tmp_path: Path) -> None:
    from kuma_core.mame.ingest import IngestMode
    from kuma_core.mame.pipeline import run_analyze

    ingest_dir = _make_input_dir(tmp_path, n_extra_copies=2)  # 6 records total
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    output = tmp_path / "out.xlsx"

    calls: list[tuple[int, int]] = []

    verdicts, _ = run_analyze(
        input_dir=ingest_dir,
        reference_path=reference,
        expected_path=kuro_xlsx,
        output_path=output,
        cds_start=0,
        cds_end=9,
        min_file_size_kb=0.0,
        ingest_mode=IngestMode.BARCODE,
        progress_callback=lambda i, total: calls.append((i, total)),
    )

    n = len(verdicts)
    assert n == 6, f"fixture should yield 6 records, got {n}"
    assert len(calls) == n, "callback must fire once per record"
    # Indices are 1-based, strictly monotonic, ending at total.
    assert [c[0] for c in calls] == list(range(1, n + 1))
    assert all(c[1] == n for c in calls), "total must equal record count on every call"
    assert calls[-1] == (n, n), "final call must be (total, total)"


def test_run_analyze_callback_optional_backward_compatible(tmp_path: Path) -> None:
    """Omitting progress_callback (the default) must not raise."""
    from kuma_core.mame.ingest import IngestMode
    from kuma_core.mame.pipeline import run_analyze

    ingest_dir = _make_input_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    output = tmp_path / "out.xlsx"

    verdicts, _ = run_analyze(
        input_dir=ingest_dir,
        reference_path=reference,
        expected_path=kuro_xlsx,
        output_path=output,
        cds_start=0,
        cds_end=9,
        min_file_size_kb=0.0,
        ingest_mode=IngestMode.BARCODE,
    )
    assert len(verdicts) == 2


# ---------------------------------------------------------------------------
# 2. handle_analyze emits intermediate values strictly between 60 and 85
# ---------------------------------------------------------------------------

def test_handle_analyze_emits_intermediate_band_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = _make_input_dir(tmp_path, n_extra_copies=4)  # 10 records
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    output = tmp_path / "out.xlsx"

    sent: list[dict] = []
    # Capture the band emitter (_send, module-level import in the handler).
    monkeypatch.setattr(analyze_mod, "_send", lambda obj: sent.append(obj))

    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(output),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    })
    assert result["output_path"] == str(output)

    band_values = [
        m["params"]["value"]
        for m in sent
        if m.get("method") == "progress" and "value" in m.get("params", {})
    ]
    intermediate = [v for v in band_values if 60 < v < 85]
    assert intermediate, (
        "handle_analyze must emit values strictly between 60 and 85 "
        f"(the formerly silent 60->85 jump); captured band values={band_values}"
    )
    # current/total must be carried so the dormant "X / Y" UI activates.
    with_counts = [
        m["params"]
        for m in sent
        if m.get("method") == "progress" and "current" in m.get("params", {})
    ]
    assert with_counts, "band emissions must include current/total"
    assert all(p["total"] == 10 for p in with_counts)
    assert max(p["current"] for p in with_counts) == 10


# ---------------------------------------------------------------------------
# 3. Heartbeat thread starts, emits during a silent run, and stops cleanly
# ---------------------------------------------------------------------------

def test_handle_analyze_heartbeat_starts_emits_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = _make_input_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    output = tmp_path / "out.xlsx"

    # Shrink the interval so the test does not wait 30 s.
    monkeypatch.setattr(analyze_mod, "_HEARTBEAT_INTERVAL_S", 0.05)

    sent: list[dict] = []
    monkeypatch.setattr(analyze_mod, "_send", lambda obj: sent.append(obj))

    # Stub run_analyze (function-local import -> patch the source binding) with
    # a long, otherwise-silent run that emits NO progress of its own.
    def _slow_run_analyze(*_args, **_kwargs):
        time.sleep(0.3)  # >> heartbeat interval -> several beats
        return ([], [])

    monkeypatch.setattr(
        "kuma_core.mame.pipeline.run_analyze", _slow_run_analyze
    )

    threads_before = {t.name for t in threading.enumerate()}

    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(output),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    })
    assert result["output_path"] == str(output)

    # Heartbeat re-emitted the holder state during the silent stretch.
    progress_msgs = [m for m in sent if m.get("method") == "progress"]
    assert len(progress_msgs) >= 1, (
        "heartbeat must emit at least one progress event during the silent run"
    )

    # No thread leak: the named heartbeat thread is gone after the handler
    # returns (joined in the finally block).
    threads_after = {t.name for t in threading.enumerate()}
    assert "analyze-heartbeat" not in (threads_after - threads_before)
    assert not any(
        t.name == "analyze-heartbeat" and t.is_alive()
        for t in threading.enumerate()
    )


# ---------------------------------------------------------------------------
# 4. Progress never steps backward when the heartbeat fires during a slow
#    pre-loop ingest (regression guard: holder must track the current phase,
#    not sit ahead of it).
# ---------------------------------------------------------------------------

def test_handle_analyze_progress_monotonic_with_slow_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sidecar_mame.handlers import analyze as analyze_mod

    ingest_dir = _make_input_dir(tmp_path)
    reference = _make_reference_fasta(tmp_path)
    kuro_xlsx = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro_xlsx)
    output = tmp_path / "out.xlsx"

    monkeypatch.setattr(analyze_mod, "_HEARTBEAT_INTERVAL_S", 0.02)

    # Single ordered sink merging milestone (_progress) + band/heartbeat
    # (_send) emissions, so the backward-step glitch (heartbeat emitting a
    # value ahead of the next milestone) becomes observable.
    values: list[int] = []
    monkeypatch.setattr(
        analyze_mod, "_progress", lambda value, message="": values.append(value)
    )
    monkeypatch.setattr(
        analyze_mod,
        "_send",
        lambda obj: values.append(obj["params"]["value"])
        if obj.get("method") == "progress"
        else None,
    )

    # Make the FIRST ingest (dist_stats, before any milestone past 10) slow so
    # the heartbeat fires while the holder should still read the ingest phase.
    # route_ingest is a function-local import in handle_analyze, so patch the
    # source binding (not a module attribute on the handler).
    import kuma_core.mame.ingest as ingest_mod

    real_route_ingest = ingest_mod.route_ingest

    def _slow_route_ingest(*args, **kwargs):
        time.sleep(0.12)  # several heartbeat beats during the ingest phase
        return real_route_ingest(*args, **kwargs)

    monkeypatch.setattr(ingest_mod, "route_ingest", _slow_route_ingest)

    result = analyze_mod.handle_analyze({
        "input_dir": str(ingest_dir),
        "reference": str(reference),
        "expected": str(kuro_xlsx),
        "output": str(output),
        "cds_start": 0,
        "cds_end": 9,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    })
    assert result["output_path"] == str(output)

    # The merged emitted value sequence must be non-decreasing: a heartbeat
    # during the slow ingest must not surface a value ahead of the next
    # milestone (which would make the bar jump 10 -> 60 -> 30).
    assert values, "expected progress emissions"
    assert values == sorted(values), (
        f"progress values must be non-decreasing; got {values}"
    )
