"""Full sidecar JSON-RPC end-to-end test for LOAD SAMPLE DATA.

Spawns the real Python sidecar as a subprocess, communicates via the same
newline-delimited JSON-RPC 2.0 protocol the Rust/Tauri host uses, and
reproduces the exact sequence the frontend's loadSampleData() action performs:

  1. load_fasta on samples/sample_plasmid.gb
  2. load_evolvepro_csv on samples/sample_evolvepro.csv  (text/evolvepro mode)

This validates source Python sidecar behavior over subprocess JSON-RPC.
It does not exercise the Rust/Tauri transport, packaged native sidecar,
frontend state, or UI, so passing does not guarantee the native action works.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "src-tauri" / "samples"
SIDECAR_ENTRY = REPO_ROOT / "python-core" / "sidecar_main_kuro.py"


def test_client_timeout_when_sidecar_is_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    silent = tmp_path / "silent.py"
    silent.write_text("import time\ntime.sleep(60)\n")
    monkeypatch.setattr(sys.modules[__name__], "SIDECAR_ENTRY", silent)
    client = SidecarClient()
    failures: list[TimeoutError] = []

    def request() -> None:
        try:
            client.call("health_info", {}, _timeout=0.05)
        except TimeoutError as error:
            failures.append(error)

    worker = threading.Thread(target=request, daemon=True)
    try:
        worker.start()
        worker.join(timeout=2)
        assert not worker.is_alive(), "RPC timeout was ignored"
        assert len(failures) == 1
    finally:
        client.proc.kill()
        client.proc.wait(timeout=5)
        worker.join(timeout=5)


class SidecarClient:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, str(SIDECAR_ENTRY)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(REPO_ROOT),
            text=True,
            bufsize=1,
        )
        self._req_id = 0
        self._lines: queue.Queue[str] = queue.Queue()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put("")

    def call(self, method: str, params: dict, _timeout: float = 30.0) -> dict:
        self._req_id += 1
        req = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params}
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        # drain progress / ready notifications until we see our response
        deadline = time.monotonic() + _timeout
        while True:
            try:
                line = self._lines.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                raise TimeoutError(f"sidecar RPC {method} exceeded {_timeout}s") from None
            if not line:
                raise RuntimeError("sidecar closed stdout")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg and msg["id"] == self._req_id:
                if "error" in msg:
                    raise RuntimeError(f"RPC error: {msg['error']}")
                return msg["result"]
            # else: notification (ready / progress) — keep reading

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        finally:
            self._reader.join(timeout=5)


@pytest.fixture(scope="module")
def client():
    c = SidecarClient()
    yield c
    c.close()


def test_sidecar_ping(client: SidecarClient) -> None:
    result = client.call("ping", {})
    assert result == {"ok": True}
    assert result["ok"] is True


def test_load_sample_data_text_mode_full_chain(client: SidecarClient) -> None:
    """Reproduce frontend loadSampleData() in text→evolvepro mode."""
    seq = client.call("load_fasta", {"filepath": str(SAMPLE_DIR / "sample_plasmid.gb")})
    assert seq["seq_length"] == 2700
    longest = max(seq["genes"], key=lambda g: g["aa_length"])
    assert longest["gene"].lower() == "egfp"
    # aa_length is CDS_len/3 (includes stop codon position); translation excludes stop
    assert longest["aa_length"] == 240
    translation = longest["translation"]
    assert len(translation) == 239
    assert translation.startswith("MVSKGEELFTGVVPIL")
    assert translation.endswith("MDELYK")

    csv_result = client.call(
        "load_evolvepro_csv",
        {
            "filepath": str(SAMPLE_DIR / "sample_evolvepro.csv"),
            "top_n": 24,
            "ref_seq": translation,
        },
    )
    assert csv_result["total_count"] >= 24
    assert csv_result["selected_count"] > 0
    assert len(csv_result["variants"]) > 0
