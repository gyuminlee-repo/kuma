#!/usr/bin/env python3
"""Frozen MAME sidecar smoke test.

Verifies that the frozen (PyInstaller) MAME sidecar binary correctly handles:
  - ProcessPoolExecutor(mp_context=spawn) + multiprocessing.freeze_support()
  - per-NB parallel combinatorial demux over JSON-RPC 2.0

Usage:
    python frozen_mame_smoke.py <path-to-frozen-mame-sidecar>

Exit codes:
    0 = PASS
    1 = FAIL (with diagnostic output)
"""

from __future__ import annotations

import gzip
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Synthetic constants (mirrored from tests/mame/test_combinatorial_demux.py)
# Self-contained: do NOT import the pytest test module.
# ---------------------------------------------------------------------------

_REF_SEQ = "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGAGACCCGT"

_F_BARCODES = [
    "AATCCCACTAC",  # F1 (11 bp)
    "TGAACTGAGCG",  # F2 (11 bp)
    "TATCTGACCTT",  # F3 (11 bp)
    "ATATGAGACG",   # F4 (10 bp)
    "CGCTCATTAG",   # F5 (10 bp)
    "TAATCTCGTC",   # F6 (10 bp)
    "GCGCGATTTT",   # F7 (10 bp)
    "AGAGCACTAG",   # F8 (10 bp)
    "TGCCTTGATC",   # F9 (10 bp)
    "CTACTCAGTC",   # F10 (10 bp)
    "TCGTCTGACT",   # F11 (10 bp)
    "GAACATACGG",   # F12 (10 bp)
]

_R_BARCODES = [
    "CCCTATGACA",  # R1 (10 bp)
    "TAATGGCAAG",  # R2 (10 bp)
    "AACAAGGCGT",  # R3 (10 bp)
    "GTATGTAGAA",  # R4 (10 bp)
    "TTCTATGGGG",  # R5 (10 bp)
    "CCTCGCAACC",  # R6 (10 bp)
    "TGGATGCTTA",  # R7 (10 bp)
    "AGAGTGCGGC",  # R8 (10 bp)
]

_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"


def _reverse_complement(seq: str) -> str:
    complement = str.maketrans("ACGTacgt", "TGCAtgca")
    return seq.translate(complement)[::-1]


def _build_read(r_idx: int, f_idx: int, amplicon: str) -> str:
    """Build a synthetic read matching the real library layout (1-indexed).

    Real library structure (sense strand):
      5'-[F_barcode + F_anneal]-[insert]-[RC(R_anneal) + RC(R_barcode)]-3'
    """
    return (
        _F_BARCODES[f_idx - 1] + _F_TAIL
        + amplicon
        + _reverse_complement(_R_TAIL.upper()) + _reverse_complement(_R_BARCODES[r_idx - 1])
    )


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _build_reference_fasta(workdir: Path) -> Path:
    ref = workdir / "reference.fasta"
    ref.write_text(f">sispS_test\n{_REF_SEQ}\n", encoding="utf-8")
    return ref


def _build_barcodes_xlsx(workdir: Path) -> Path:
    try:
        import openpyxl
    except ImportError as exc:
        print(f"FAIL: openpyxl not available — install it with: pip install openpyxl")
        print(f"  ImportError: {exc}")
        sys.exit(1)

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None

    for i, bc in enumerate(_F_BARCODES, start=1):
        ws.append([f"isps_f_{i}", bc.lower() + _F_TAIL])
    for i, bc in enumerate(_R_BARCODES, start=1):
        ws.append([f"isps_r_{i}", bc.lower() + _R_TAIL])

    path = workdir / "barcodes.xlsx"
    wb.save(path)
    return path


def _build_fastq_gz(barcode_dir: Path, n_reads: int = 18) -> None:
    """Write ~18 gzipped synthetic reads into barcode_dir/reads.fastq.gz."""
    barcode_dir.mkdir(parents=True, exist_ok=True)
    fastq_path = barcode_dir / "reads.fastq.gz"
    amplicon = _REF_SEQ  # full 60 bp; proven to align in unit tests

    reads: list[tuple[str, str]] = []
    for i in range(n_reads):
        # Rotate through r_idx in {1..3} and f_idx in {1..4} for variety
        r_idx = (i % 3) + 1
        f_idx = (i % 4) + 1
        seq = _build_read(r_idx, f_idx, amplicon)
        reads.append((f"read_{i}", seq))

    with gzip.open(fastq_path, "wt", encoding="utf-8") as fh:
        for read_id, seq in reads:
            qual = "I" * len(seq)
            fh.write(f"@{read_id}\n{seq}\n+\n{qual}\n")


def _build_run_dir(workdir: Path) -> Path:
    """Create MinKNOW run dir with barcode06 and barcode20 fastq_pass dirs."""
    run_dir = workdir / "RUN"
    for barcode in ("barcode06", "barcode20"):
        _build_fastq_gz(run_dir / "fastq_pass" / barcode)
    return run_dir


# ---------------------------------------------------------------------------
# JSON-RPC request builder — json.dumps() ensures backslash paths are safe
# ---------------------------------------------------------------------------

def _rpc(id_: int, method: str, params: dict[str, Any]) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params})


# ---------------------------------------------------------------------------
# Cross-platform sidecar I/O: daemon reader thread + queue
#
# Uses queue.Queue to avoid select() (broken on Windows named-pipe handles)
# and signal.alarm() (Unix-only). The reader thread blocks on proc.stdout and
# pushes each decoded JSON object into self._q; EOF pushes sentinel None.
# ---------------------------------------------------------------------------

class SidecarIO:

    def __init__(self, binary: Path, stderr_path: Path) -> None:
        self._stderr_fh = open(stderr_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_fh,
            text=True,
            bufsize=1,
        )
        self._q: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self.proc.stdout is not None
        try:
            for raw_line in self.proc.stdout:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    print(f"[reader] JSONDecodeError on line {raw_line!r}: {exc}",
                          file=sys.stderr)
                    continue
                self._q.put(obj)
        finally:
            self._q.put(None)  # sentinel: reader done (EOF or exception)

    def send(self, payload: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(payload + "\n")
        self.proc.stdin.flush()

    def recv(self, req_id: int, timeout: float) -> dict[str, Any]:
        """Block until a response with matching id arrives, skipping notifications.

        Raises TimeoutError on timeout; raises RuntimeError on process EOF.
        """
        t0 = time.monotonic()
        while True:
            elapsed = time.monotonic() - t0
            remaining = timeout - elapsed
            if remaining <= 0:
                raise TimeoutError(f"No response for id={req_id} within {timeout}s")
            try:
                obj = self._q.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                # Check again next iteration
                continue
            if obj is None:
                raise RuntimeError(
                    f"Sidecar stdout closed before response id={req_id}"
                )
            # Skip JSON-RPC notifications (ready, progress, etc.)
            if "method" in obj:
                continue
            if obj.get("id") == req_id:
                return obj
            # Response for an unexpected id — skip and continue
            print(f"[recv] skipping unexpected id={obj.get('id')!r} while waiting for {req_id}",
                  file=sys.stderr)

    def close(self, timeout: float = 10.0) -> int:
        """Close stdin, wait for process exit; kill if stuck. Returns exit code."""
        if self.proc.stdin:
            try:
                self.proc.stdin.close()
            except OSError as exc:
                print(f"[close] stdin close error (ignored): {exc}", file=sys.stderr)
        try:
            rc = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            rc = self.proc.wait()
        self._stderr_fh.flush()
        self._stderr_fh.close()
        return rc


# ---------------------------------------------------------------------------
# Main smoke test
# ---------------------------------------------------------------------------

def run_smoke(binary: Path) -> None:
    workdir = Path(tempfile.mkdtemp(prefix="mame_smoke_"))
    stderr_path = workdir / "sidecar_stderr.txt"
    sio: SidecarIO | None = None
    failures: list[str] = []

    try:
        # Build fixtures
        ref_fasta = _build_reference_fasta(workdir)
        xlsx = _build_barcodes_xlsx(workdir)
        run_dir = _build_run_dir(workdir)
        out_dir = workdir / "output"
        out_dir.mkdir()

        sio = SidecarIO(binary, stderr_path)

        # --- ping ---
        print("[1/4] ping ...")
        sio.send(_rpc(1, "ping", {}))
        try:
            ping_resp = sio.recv(1, timeout=30.0)
            if ping_resp.get("result", {}).get("ok") is not True:
                failures.append(f"ping: ok is not True — got {ping_resp!r}")
            else:
                print("      ping OK")
        except (TimeoutError, RuntimeError) as exc:
            failures.append(f"ping timed out or process died: {exc}")

        # --- detect ---
        print("[2/4] mame.detect_native_barcodes ...")
        sio.send(_rpc(2, "mame.detect_native_barcodes", {
            "minknow_run_dir": str(run_dir),
        }))
        try:
            detect_resp = sio.recv(2, timeout=60.0)
            if "error" in detect_resp:
                failures.append(f"detect RPC error: {detect_resp['error']}")
            else:
                detect_result = detect_resp.get("result", {})
                total = detect_result.get("total_count", 0)
                if total < 1:
                    failures.append(f"detect: total_count={total}, expected >= 1")
                else:
                    print(f"      detect OK — total_count={total}, "
                          f"native_barcodes={detect_result.get('native_barcodes')}")
        except (TimeoutError, RuntimeError) as exc:
            failures.append(f"detect timed out or process died: {exc}")

        # --- per-NB parallel demux ---
        print("[3/4] mame.run_combinatorial_demux (per-NB parallel) ...")
        sio.send(_rpc(3, "mame.run_combinatorial_demux", {
            "minknow_run_dir": str(run_dir),
            "custom_barcodes_xlsx": str(xlsx),
            "reference_fasta": str(ref_fasta),
            "output_dir": str(out_dir),
            "native_barcodes": ["barcode06", "barcode20"],
        }))
        try:
            demux_resp = sio.recv(3, timeout=240.0)
            if "error" in demux_resp:
                failures.append(f"demux RPC error: {demux_resp['error']}")
            else:
                demux_result = demux_resp.get("result", {})
                per_nb = demux_result.get("native_barcodes")
                if not isinstance(per_nb, list):
                    failures.append(
                        f"demux: native_barcodes is not a list — got {type(per_nb).__name__!r}"
                    )
                elif len(per_nb) != 2:
                    failures.append(
                        f"demux: native_barcodes length={len(per_nb)}, expected 2"
                    )
                else:
                    print(f"      demux OK — native_barcodes list length={len(per_nb)}")
        except (TimeoutError, RuntimeError) as exc:
            failures.append(f"demux timed out or process died: {exc}")

        # --- shutdown ---
        print("[4/4] shutdown ...")
        sio.send(_rpc(4, "shutdown", {}))
        try:
            sio.recv(4, timeout=15.0)
            print("      shutdown ack received")
        except (TimeoutError, RuntimeError) as exc:
            # Shutdown ack may not arrive before EOF; process exit is the criterion
            print(f"      shutdown ack not received ({exc}); waiting for process exit")

        rc = sio.close(timeout=15.0)
        print(f"      sidecar exit code: {rc}")
        sio = None

    except OSError as exc:
        failures.append(f"OS error launching sidecar: {exc}")
    finally:
        if sio is not None:
            sio.close(timeout=5.0)
            sio = None

    # --- stderr analysis (after process is dead so buffer is fully flushed) ---
    print("\n[stderr analysis]")
    stderr_lines: list[str] = []
    if stderr_path.exists():
        stderr_lines = stderr_path.read_text(encoding="utf-8", errors="replace").splitlines()

    started_count = sum(
        1 for line in stderr_lines if "MAME sidecar started" in line
    )
    print(f"      'MAME sidecar started' occurrences in stderr: {started_count}")

    if started_count == 0:
        failures.append(
            "freeze_support check: 'MAME sidecar started' not found in stderr — "
            "sidecar may not have launched correctly"
        )
    elif started_count > 1:
        failures.append(
            f"freeze_support BROKEN: 'MAME sidecar started' appeared {started_count}x "
            f"(expected exactly 1) — spawned children are re-running the server loop"
        )
    else:
        print("      freeze_support OK: exactly 1 'MAME sidecar started' line")

    # --- Final report ---
    print()
    if failures:
        print("=" * 60)
        print("FROZEN MAME SMOKE: FAIL")
        print("=" * 60)
        for i, msg in enumerate(failures, 1):
            print(f"  [{i}] {msg}")
        print()
        print("--- last 20 stderr lines ---")
        for line in stderr_lines[-20:]:
            print(f"  {line}")
        shutil.rmtree(workdir, ignore_errors=True)
        sys.exit(1)
    else:
        print("=" * 60)
        print("FROZEN MAME SMOKE: PASS")
        print("=" * 60)
        shutil.rmtree(workdir, ignore_errors=True)
        sys.exit(0)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-frozen-mame-sidecar>")
        sys.exit(1)

    binary = Path(sys.argv[1])
    if not binary.exists():
        print(f"FAIL: sidecar binary not found: {binary}")
        sys.exit(1)
    if not os.access(binary, os.X_OK):
        print(f"FAIL: sidecar binary is not executable: {binary}")
        sys.exit(1)

    print(f"Frozen MAME sidecar smoke test")
    print(f"Binary: {binary}")
    print(f"Platform: {sys.platform}")
    print()

    run_smoke(binary)


if __name__ == "__main__":
    main()
