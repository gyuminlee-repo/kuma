"""Tests for kuma_core.shared.run_manifest.

Covers:
- compute_input_sha256: deterministic, known-bytes fixture
- build_run_manifest: required field presence
- write_run_manifest / load_run_manifest: round-trip JSON fidelity
- Determinism: same input/params produce identical non-timestamp fields
- Missing input file: key silently omitted (no exception)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kuma_core.shared.run_manifest import (
    SCHEMA_VERSION,
    build_run_manifest,
    compute_input_sha256,
    load_run_manifest,
    write_run_manifest,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Deterministic 12-byte payload; SHA-256 precomputed offline.
_KNOWN_BYTES = b"hello kuma!\n"
_KNOWN_SHA256 = hashlib.sha256(_KNOWN_BYTES).hexdigest()


@pytest.fixture
def known_input_file(tmp_path: Path) -> Path:
    """Write a fixture file with known bytes."""
    p = tmp_path / "fixture.txt"
    p.write_bytes(_KNOWN_BYTES)
    return p


def _ts(offset: int = 0) -> datetime:
    """Return a fixed UTC datetime. offset adjusts seconds."""
    return datetime(2026, 5, 7, 10, 0, offset, tzinfo=timezone.utc)


def _base_manifest(inputs=None, extra=None) -> dict:
    return build_run_manifest(
        method="test_method",
        inputs=inputs or {},
        params={"key": "value", "count": 3},
        started_at=_ts(0),
        finished_at=_ts(5),
        seed=42,
        extra=extra,
    )


# ---------------------------------------------------------------------------
# compute_input_sha256
# ---------------------------------------------------------------------------


def test_sha256_known_bytes(known_input_file: Path) -> None:
    """SHA-256 of known bytes matches pre-computed digest."""
    digest = compute_input_sha256(known_input_file)
    assert digest == _KNOWN_SHA256


def test_sha256_deterministic(known_input_file: Path) -> None:
    """Calling compute_input_sha256 twice returns the same value."""
    assert compute_input_sha256(known_input_file) == compute_input_sha256(known_input_file)


def test_sha256_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_input_sha256(tmp_path / "nonexistent.txt")


# ---------------------------------------------------------------------------
# build_run_manifest — required field presence
# ---------------------------------------------------------------------------


def test_build_manifest_required_fields() -> None:
    m = _base_manifest()
    for field in (
        "schema_version",
        "method",
        "kuma_version",
        "kuro_module_version",
        "python_version",
        "platform",
        "started_at",
        "finished_at",
        "duration_seconds",
        "inputs",
        "params",
        "seed",
    ):
        assert field in m, f"Missing required field: {field!r}"


def test_build_manifest_schema_version() -> None:
    m = _base_manifest()
    assert m["schema_version"] == SCHEMA_VERSION


def test_build_manifest_method() -> None:
    m = _base_manifest()
    assert m["method"] == "test_method"


def test_build_manifest_seed() -> None:
    m = _base_manifest()
    assert m["seed"] == 42


def test_build_manifest_seed_none() -> None:
    m = build_run_manifest(
        method="m",
        inputs={},
        params={},
        started_at=_ts(),
        finished_at=_ts(1),
    )
    assert m["seed"] is None


def test_build_manifest_duration() -> None:
    m = _base_manifest()
    assert m["duration_seconds"] == pytest.approx(5.0)


def test_build_manifest_timestamps_iso8601() -> None:
    m = _base_manifest()
    # Must parse as ISO 8601 with UTC offset
    dt = datetime.fromisoformat(m["started_at"])
    assert dt.tzinfo is not None


def test_build_manifest_naive_timestamp_raises() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_run_manifest(
            method="m",
            inputs={},
            params={},
            started_at=datetime(2026, 5, 7, 10, 0, 0),  # naive
            finished_at=_ts(),
        )


def test_build_manifest_input_recorded(known_input_file: Path) -> None:
    m = build_run_manifest(
        method="m",
        inputs={"my_file": known_input_file},
        params={},
        started_at=_ts(),
        finished_at=_ts(1),
    )
    assert "my_file" in m["inputs"]
    entry = m["inputs"]["my_file"]
    assert entry["sha256"] == _KNOWN_SHA256
    assert entry["size_bytes"] == len(_KNOWN_BYTES)
    assert "path" in entry


def test_build_manifest_missing_input_omitted(tmp_path: Path) -> None:
    """Non-existent input path must be silently omitted — no exception."""
    m = build_run_manifest(
        method="m",
        inputs={"absent": tmp_path / "does_not_exist.csv"},
        params={},
        started_at=_ts(),
        finished_at=_ts(1),
    )
    assert "absent" not in m["inputs"]


def test_build_manifest_extra_included() -> None:
    m = _base_manifest(extra={"note": "test run"})
    assert m.get("extra") == {"note": "test run"}


def test_build_manifest_no_extra_key_absent() -> None:
    m = _base_manifest()
    assert "extra" not in m


def test_build_manifest_params_serialised() -> None:
    """Path objects in params must be converted to strings."""
    from pathlib import Path as P
    m = build_run_manifest(
        method="m",
        inputs={},
        params={"p": P("/tmp/test.csv")},
        started_at=_ts(),
        finished_at=_ts(1),
    )
    # After JSON serialisation the value must be a plain string.
    assert isinstance(m["params"]["p"], str)


# ---------------------------------------------------------------------------
# write_run_manifest / load_run_manifest round-trip
# ---------------------------------------------------------------------------


def test_write_and_load_roundtrip(tmp_path: Path) -> None:
    m = _base_manifest()
    out = tmp_path / "test.run.json"
    returned = write_run_manifest(out, m)
    assert returned == out

    loaded = load_run_manifest(out)
    assert loaded == m


def test_write_creates_valid_json(tmp_path: Path) -> None:
    m = _base_manifest()
    out = tmp_path / "check.run.json"
    write_run_manifest(out, m)
    raw = out.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["method"] == "test_method"


def test_write_wrong_extension_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=".json"):
        write_run_manifest(tmp_path / "manifest.txt", {})


def test_write_missing_parent_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        write_run_manifest(tmp_path / "nonexistent_dir" / "m.json", {})


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_run_manifest(tmp_path / "missing.json")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_run_manifest(bad)


# ---------------------------------------------------------------------------
# Determinism (seed fixed; timestamps excluded from comparison)
# ---------------------------------------------------------------------------


def test_determinism_excluding_timestamps(known_input_file: Path) -> None:
    """With identical inputs and params, non-timestamp fields are identical."""
    kwargs = dict(
        method="design_sdm_primers",
        inputs={"ref": known_input_file},
        params={"polymerase": "Q5", "organism": "ecoli"},
        started_at=_ts(0),
        finished_at=_ts(10),
        seed=0,
    )
    m1 = build_run_manifest(**kwargs)
    m2 = build_run_manifest(**kwargs)

    # Strip timestamps before comparing
    for m in (m1, m2):
        m.pop("started_at")
        m.pop("finished_at")

    assert m1 == m2
