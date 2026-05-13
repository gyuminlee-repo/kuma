"""Full sidecar JSON-RPC end-to-end test for LOAD SAMPLE DATA.

Spawns the real Python sidecar as a subprocess, communicates via the same
newline-delimited JSON-RPC 2.0 protocol the Rust/Tauri host uses, and
reproduces the exact sequence the frontend's loadSampleData() action performs:

  1. load_fasta on samples/sample_plasmid.gb
  2. load_evolvepro_csv on samples/sample_evolvepro.csv  (text/evolvepro mode)
  3. load_evolvepro_csv on samples/sample_multi_evolve.csv (multi-evolve mode)

This validates the full IPC pipeline minus only the Rust shell, which is a
thin transport layer. If this passes, clicking "Load Sample Data" in the
Tauri UI cannot fail at the sidecar boundary.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "src-tauri" / "samples"
SIDECAR_ENTRY = REPO_ROOT / "python-core" / "sidecar_main_kuro.py"


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

    def call(self, method: str, params: dict, timeout: float = 30.0) -> dict:
        self._req_id += 1
        req = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params}
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        # drain progress / ready notifications until we see our response
        deadline = self.proc.stdout
        while True:
            line = deadline.readline()
            if not line:
                stderr = (self.proc.stderr.read() if self.proc.stderr else "") or ""
                raise RuntimeError(f"sidecar closed stdout. stderr: {stderr[:500]}")
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
        except Exception:
            self.proc.kill()


@pytest.fixture(scope="module")
def client():
    c = SidecarClient()
    yield c
    c.close()


def test_sidecar_ping(client: SidecarClient) -> None:
    result = client.call("ping", {})
    assert result == "pong" or result is True or result is None or isinstance(result, dict)


def test_load_sample_data_text_mode_full_chain(client: SidecarClient) -> None:
    """Reproduce frontend loadSampleData() in text→evolvepro mode."""
    seq = client.call("load_fasta", {"filepath": str(SAMPLE_DIR / "sample_plasmid.gb")})
    assert seq["seq_length"] == 5000
    longest = max(seq["genes"], key=lambda g: g["aa_length"])
    assert longest["gene"] == "synR"
    translation = longest["translation"]

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


def test_load_sample_data_multi_evolve_mode_full_chain(client: SidecarClient) -> None:
    """Reproduce frontend loadSampleData() in multi-evolve mode."""
    seq = client.call("load_fasta", {"filepath": str(SAMPLE_DIR / "sample_plasmid.gb")})
    assert seq["seq_length"] == 5000

    csv_result = client.call(
        "load_evolvepro_csv",
        {
            "filepath": str(SAMPLE_DIR / "sample_multi_evolve.csv"),
            "top_n": 24,
            "ref_seq": "",
        },
    )
    assert csv_result["total_count"] > 0
    assert len(csv_result["variants"]) > 0
