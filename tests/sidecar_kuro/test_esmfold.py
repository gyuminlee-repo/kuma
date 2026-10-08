# ruff: noqa: S101
"""Tests for predict_structure_esmfold — core prediction, size guard, cache,
handler, dispatcher, and the dispersion reference-frame branch.

All network is mocked; no real ESMFold calls are made.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SIDECAR_DIR = _PROJECT_ROOT / "python-core"
if str(_SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(_SIDECAR_DIR))

# A valid 60-aa protein sequence.
_SEQ = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVK"


def _seq_hash(seq: str) -> str:
    return hashlib.sha256(seq.encode()).hexdigest()


def _make_pdb(residues: int = 3, plddt: float = 90.0) -> str:
    """Minimal PDB text with CA atoms carrying pLDDT in the B-factor column."""
    lines = []
    for i in range(1, residues + 1):
        # columns must line up with fixed-width PDB parsing (12:16 name, 22:26 resSeq,
        # 30:38/38:46/46:54 xyz, 60:66 bfactor)
        lines.append(
            f"ATOM  {i:>5} CA  ALA A{i:>4}    "
            f"{float(i):>8.3f}{0.0:>8.3f}{0.0:>8.3f}"
            f"{1.0:>6.2f}{plddt:>6.2f}           C"
        )
    return "\n".join(lines) + "\n"


def _mock_resp(payload: bytes) -> MagicMock:
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    m.read.return_value = payload
    return m


class TestSizeGuard:
    def test_too_long_rejected_before_network(self) -> None:
        from kuma_core.kuro.esmfold import predict_structure
        import urllib.request as _req

        long_seq = "A" * 401
        with patch.object(_req, "urlopen", side_effect=AssertionError("no network")):
            with pytest.raises(ValueError, match="too long"):
                predict_structure(long_seq)

    def test_too_short_rejected(self) -> None:
        from kuma_core.kuro.esmfold import predict_structure

        with pytest.raises(ValueError, match="too short"):
            predict_structure("MAG")

    def test_exactly_400_allowed(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import esmfold as _es

        monkeypatch.setattr(_es, "_cache_path", lambda h: tmp_path / f"{h}.pdb")
        pdb = _make_pdb(residues=400)
        with patch("urllib.request.urlopen", return_value=_mock_resp(pdb.encode())):
            pdb_text, plddt, count, cache_hit, _h = predict_structure_via(_es, "A" * 400)
        assert pdb_text is not None
        assert cache_hit is False
        assert count == 400


def predict_structure_via(module, seq):
    return module.predict_structure(seq)


class TestPredictAndCache:
    def test_successful_prediction_parses_plddt(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import esmfold as _es

        monkeypatch.setattr(_es, "_cache_path", lambda h: tmp_path / f"{h}.pdb")
        pdb = _make_pdb(residues=3, plddt=88.0)
        with patch("urllib.request.urlopen", return_value=_mock_resp(pdb.encode())):
            pdb_text, plddt, count, cache_hit, seq_hash = _es.predict_structure(_SEQ)

        assert pdb_text is not None
        assert plddt == 88.0
        assert count == 3
        assert cache_hit is False
        assert seq_hash == _seq_hash(_SEQ.upper().rstrip("*"))
        assert (tmp_path / f"{seq_hash}.pdb").exists()

    def test_cache_hit_skips_network(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import esmfold as _es

        monkeypatch.setattr(_es, "_cache_path", lambda h: tmp_path / f"{h}.pdb")
        seq_clean = _SEQ.upper()
        seq_hash = _seq_hash(seq_clean)
        (tmp_path / f"{seq_hash}.pdb").write_text(_make_pdb(residues=5, plddt=70.0))

        with patch("urllib.request.urlopen", side_effect=AssertionError("no network on cache hit")):
            pdb_text, plddt, count, cache_hit, computed = _es.predict_structure(seq_clean)

        assert cache_hit is True
        assert count == 5
        assert plddt == 70.0
        assert computed == seq_hash

    def test_network_failure_raises_valueerror(self) -> None:
        from kuma_core.kuro.esmfold import predict_structure

        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            with pytest.raises(ValueError, match="ESMFold prediction failed"):
                predict_structure(_SEQ)

    def test_empty_structure_raises(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import esmfold as _es

        monkeypatch.setattr(_es, "_cache_path", lambda h: tmp_path / f"{h}.pdb")
        with patch("urllib.request.urlopen", return_value=_mock_resp(b"   ")):
            with pytest.raises(ValueError, match="empty or invalid"):
                _es.predict_structure(_SEQ)

    def test_failed_prediction_not_cached(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import esmfold as _es

        monkeypatch.setattr(_es, "_cache_path", lambda h: tmp_path / f"{h}.pdb")
        with patch("urllib.request.urlopen", side_effect=OSError("boom")):
            with pytest.raises(ValueError):
                _es.predict_structure(_SEQ)
        assert not (tmp_path / f"{_seq_hash(_SEQ.upper())}.pdb").exists()


class TestHandler:
    def test_success_result_shape(self, tmp_path, monkeypatch) -> None:
        with patch(
            "kuma_core.kuro.esmfold.predict_structure",
            return_value=(_make_pdb(3), 91.0, 3, False, "abc123"),
        ):
            from sidecar_kuro.handlers.external import handle_predict_structure_esmfold

            result = handle_predict_structure_esmfold({"sequence": _SEQ})

        assert result["success"] is True
        assert result["source"] == "esmfold"
        assert result["coordinate_frame"] == "reference"
        assert result["plddt_mean"] == 91.0
        assert result["residue_count"] == 3
        assert result["seq_hash"] == "abc123"
        assert "error_msg" not in result

    def test_cache_hit_source(self) -> None:
        with patch(
            "kuma_core.kuro.esmfold.predict_structure",
            return_value=(_make_pdb(3), 91.0, 3, True, "abc123"),
        ):
            from sidecar_kuro.handlers.external import handle_predict_structure_esmfold

            result = handle_predict_structure_esmfold({"sequence": _SEQ})
        assert result["source"] == "esmfold_cache"

    def test_empty_sequence_raises(self) -> None:
        from sidecar_kuro.handlers.external import handle_predict_structure_esmfold

        with pytest.raises(ValueError, match="sequence is required"):
            handle_predict_structure_esmfold({"sequence": ""})

    def test_too_long_returns_error_msg(self) -> None:
        from sidecar_kuro.handlers.external import handle_predict_structure_esmfold

        result = handle_predict_structure_esmfold({"sequence": "A" * 401})
        assert result["success"] is False
        assert result["source"] == "error"
        assert result["pdb_text"] is None
        assert "too long" in (result.get("error_msg") or "")

    def test_network_error_no_traceback(self) -> None:
        with patch(
            "kuma_core.kuro.esmfold.predict_structure",
            side_effect=ValueError("ESMFold prediction failed: connection refused"),
        ):
            from sidecar_kuro.handlers.external import handle_predict_structure_esmfold

            result = handle_predict_structure_esmfold({"sequence": _SEQ})
        assert result["success"] is False
        assert "connection refused" in (result.get("error_msg") or "")
        assert "Traceback" not in (result.get("error_msg") or "")


class TestDispatcherRegistration:
    def test_registered_in_methods(self) -> None:
        from sidecar_kuro.dispatcher import _METHODS

        assert "predict_structure_esmfold" in _METHODS

    def test_registered_in_async_methods(self) -> None:
        from sidecar_kuro.dispatcher import _ASYNC_METHODS

        assert "predict_structure_esmfold" in _ASYNC_METHODS


class TestDispersionReferenceFrame:
    def test_reference_frame_skips_accession_mapping(self) -> None:
        """coordinate_frame='reference' uses supplied PDB and does NOT fetch by accession."""
        from kuma_core.kuro import dispersion as _disp

        # A 20-residue linear structure; positions 2 and 18 are far apart.
        pdb = _make_pdb(residues=20)
        with patch.object(_disp, "fetch_ca_coords", side_effect=AssertionError("no fetch")), \
             patch.object(_disp, "fetch_ca_seq", side_effect=AssertionError("no fetch")):
            result = _disp.compute_round_dispersion(
                accession="",
                ref_seq=_SEQ,
                positions=[2, 18],
                n_trials=50,
                seed=0,
                pdb_text=pdb,
                coordinate_frame="reference",
            )
        assert result["dropped"] == []
        assert result["n_positions"] == 2
        assert result["klass"] in ("clustered", "random", "spread")

    def test_reference_frame_requires_pdb_text(self) -> None:
        from kuma_core.kuro.dispersion import compute_round_dispersion

        with pytest.raises(ValueError, match="requires pdb_text"):
            compute_round_dispersion(
                accession="",
                ref_seq=_SEQ,
                positions=[1, 2],
                coordinate_frame="reference",
            )

    def test_accession_frame_default_unchanged(self) -> None:
        """Default path still fetches by accession (backward compatible)."""
        from kuma_core.kuro import dispersion as _disp

        with patch.object(_disp, "fetch_ca_coords", return_value=None) as m:
            result = _disp.compute_round_dispersion(
                accession="P12345",
                ref_seq=_SEQ,
                positions=[1, 2],
                n_trials=10,
                seed=0,
            )
        m.assert_called_once()
        assert result["klass"] == "na"
