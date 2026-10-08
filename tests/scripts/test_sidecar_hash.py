"""
tests/scripts/test_sidecar_hash.py

Verifies that scripts/sidecar-hash.mjs produces correct SHA-256 hashes by:
1. Creating temporary fake binaries in a temp directory.
2. Running sidecar-hash.mjs against that directory via Node.js.
3. Comparing the JSON output against Python hashlib.sha256().

The test does NOT depend on real sidecar binaries existing in src-tauri/binaries/.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sidecar-hash.mjs"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_hash_script(binaries_dir: Path) -> dict:
    """Run sidecar-hash.mjs with BINARIES_DIR overridden via env var."""
    env = {**os.environ, "SIDECAR_HASH_BINARIES_DIR": str(binaries_dir)}
    result = subprocess.run(
        ["node", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sidecar-hash.mjs failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    # Parse the written JSON from the output path reported by the script
    for line in result.stdout.splitlines():
        if line.startswith("[sidecar-hash] Written:"):
            json_path = Path(line.split("Written:", 1)[1].strip())
            return json.loads(json_path.read_text())
    raise RuntimeError(f"No 'Written:' line in script output:\n{result.stdout}")


@pytest.fixture()
def fake_binaries(tmp_path):
    """Create fake sidecar binaries and return (binaries_dir, {name: content})."""
    contents = {
        "kuro-sidecar-x86_64-unknown-linux-gnu": b"fake kuro linux binary content",
        "mame-sidecar-x86_64-unknown-linux-gnu": b"fake mame linux binary content",
        "kuro-sidecar-x86_64-pc-windows-msvc.exe": b"fake kuro windows binary content",
        "mame-sidecar-x86_64-pc-windows-msvc.exe": b"fake mame windows binary content",
    }
    for name, data in contents.items():
        (tmp_path / name).write_bytes(data)
    return tmp_path, contents


def node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


@pytest.mark.skipif(not node_available(), reason="Node.js not available")
def test_hash_matches_python_hashlib(fake_binaries, tmp_path):
    """SHA-256 values in sidecar-hashes.json must match Python hashlib output."""
    binaries_dir, contents = fake_binaries

    # Patch the script to use our temp binaries_dir and write output to tmp_path.
    # We pass overrides via environment variables read inside the script.
    output_path = tmp_path / "sidecar-hashes.json"

    env = {
        **os.environ,
        "SIDECAR_HASH_BINARIES_DIR": str(binaries_dir),
        "SIDECAR_HASH_OUTPUT_PATH": str(output_path),
    }
    result = subprocess.run(
        ["node", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"sidecar-hash.mjs failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert output_path.exists(), "sidecar-hashes.json was not written"

    hashes = json.loads(output_path.read_text())

    for filename, data in contents.items():
        expected = sha256_bytes(data)
        assert filename in hashes, f"Missing key '{filename}' in hashes"
        assert hashes[filename] == expected, (
            f"Hash mismatch for '{filename}':\n"
            f"  expected (Python): {expected}\n"
            f"  actual (Node):     {hashes[filename]}"
        )


@pytest.mark.skipif(not node_available(), reason="Node.js not available")
def test_only_triple_suffixed_keys_written(fake_binaries, tmp_path):
    """
    Manifest must contain ONLY triple-suffixed full-filename keys.
    Bare base-name keys ("kuro-sidecar", "mame-sidecar") are platform-ambiguous
    and were dropped to prevent cross-build last-wins corruption.
    """
    binaries_dir, _ = fake_binaries
    output_path = tmp_path / "sidecar-hashes.json"

    env = {
        **os.environ,
        "SIDECAR_HASH_BINARIES_DIR": str(binaries_dir),
        "SIDECAR_HASH_OUTPUT_PATH": str(output_path),
    }
    subprocess.run(
        ["node", str(SCRIPT_PATH)],
        capture_output=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=True,
    )
    hashes = json.loads(output_path.read_text())
    assert "kuro-sidecar" not in hashes, "Bare base-name key must not be written"
    assert "mame-sidecar" not in hashes, "Bare base-name key must not be written"
    # All keys must start with kuro-sidecar- or mame-sidecar- (triple-suffixed).
    for key in hashes:
        assert key.startswith(("kuro-sidecar-", "mame-sidecar-")), (
            f"Unexpected non-triple-suffixed key: {key!r}"
        )


@pytest.mark.skipif(not node_available(), reason="Node.js not available")
def test_merge_preserves_other_platform_entries(fake_binaries, tmp_path):
    """
    When the manifest already contains hashes for platforms NOT present in
    this build, those entries must SURVIVE the rewrite (cross-platform safety).
    """
    binaries_dir, _ = fake_binaries
    # Remove the Windows fake binaries so only Linux entries are computed.
    for f in list(binaries_dir.iterdir()):
        if "windows" in f.name:
            f.unlink()

    output_path = tmp_path / "sidecar-hashes.json"
    preexisting = {
        "kuro-sidecar-aarch64-apple-darwin": "a" * 64,
        "mame-sidecar-aarch64-apple-darwin": "b" * 64,
        # Legacy base-name keys must be dropped on rewrite.
        "kuro-sidecar": "c" * 64,
    }
    output_path.write_text(json.dumps(preexisting))

    env = {
        **os.environ,
        "SIDECAR_HASH_BINARIES_DIR": str(binaries_dir),
        "SIDECAR_HASH_OUTPUT_PATH": str(output_path),
    }
    subprocess.run(
        ["node", str(SCRIPT_PATH)],
        capture_output=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=True,
    )
    hashes = json.loads(output_path.read_text())
    assert hashes["kuro-sidecar-aarch64-apple-darwin"] == "a" * 64
    assert hashes["mame-sidecar-aarch64-apple-darwin"] == "b" * 64
    assert "kuro-sidecar-x86_64-unknown-linux-gnu" in hashes
    assert "mame-sidecar-x86_64-unknown-linux-gnu" in hashes
    assert "kuro-sidecar" not in hashes


@pytest.mark.skipif(not node_available(), reason="Node.js not available")
def test_empty_binaries_dir_exits_nonzero(tmp_path):
    """sidecar-hash.mjs must exit non-zero when no sidecar binaries exist."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    output_path = tmp_path / "out.json"

    env = {
        **os.environ,
        "SIDECAR_HASH_BINARIES_DIR": str(empty_dir),
        "SIDECAR_HASH_OUTPUT_PATH": str(output_path),
    }
    result = subprocess.run(
        ["node", str(SCRIPT_PATH)],
        capture_output=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode != 0, (
        "Expected non-zero exit when no sidecar binaries are present"
    )
