# ruff: noqa: S101
"""Tests for annotate_domains_by_sequence — core parsing, caching, handler, dispatcher.

All tests are fully mocked; no real network calls are made.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup (mirrors test_dispatcher_shutdown.py)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SIDECAR_DIR = _PROJECT_ROOT / "python-core"
if str(_SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(_SIDECAR_DIR))


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

# A valid 60-aa protein sequence used throughout.
_SEQ = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVK"


def _seq_hash(seq: str) -> str:
    return hashlib.sha256(seq.encode()).hexdigest()


def _make_iprscan_json(matches: list[dict]) -> dict:
    """Minimal InterProScan result JSON payload."""
    return {
        "results": [
            {
                "sequence": {"length": len(_SEQ)},
                "matches": matches,
            }
        ]
    }


def _domain_match(
    ipr_acc: str,
    ipr_name: str,
    start: int,
    end: int,
    library: str = "PFAM",
) -> dict:
    """A valid DOMAIN-type integrated InterPro match."""
    return {
        "signature": {
            "accession": f"sig-{ipr_acc}",
            "name": f"sig-{ipr_acc}",
            "signatureLibraryRelease": {"library": library},
            "entry": {
                "accession": ipr_acc,
                "name": ipr_name,
                "type": "DOMAIN",
            },
        },
        "locations": [{"start": start, "end": end}],
    }


def _family_match(ipr_acc: str, start: int, end: int) -> dict:
    """A FAMILY-type integrated match — must be excluded from results."""
    return {
        "signature": {
            "accession": f"sig-{ipr_acc}",
            "name": f"sig-{ipr_acc}",
            "signatureLibraryRelease": {"library": "PFAM"},
            "entry": {
                "accession": ipr_acc,
                "name": "family-name",
                "type": "FAMILY",
            },
        },
        "locations": [{"start": start, "end": end}],
    }


def _no_entry_match(sig_acc: str, start: int, end: int) -> dict:
    """Unintegrated signature (entry=None) — must be excluded from results."""
    return {
        "signature": {
            "accession": sig_acc,
            "name": "unintegrated",
            "signatureLibraryRelease": {"library": "SUPERFAMILY"},
            "entry": None,
        },
        "locations": [{"start": start, "end": end}],
    }


def _make_mock_resp(read_value: bytes) -> MagicMock:
    """Context-manager-compatible mock for urllib.request.urlopen."""
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    m.read.return_value = read_value
    return m


# ---------------------------------------------------------------------------
# 1. Parsing: domain-only JSON
# ---------------------------------------------------------------------------


class TestParseIprscanJson:
    def test_domain_entries_extracted(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        data = _make_iprscan_json([
            _domain_match("IPR000276", "GPCR family", 5, 50),
            _domain_match("IPR001810", "Cyclin N-term", 60, 120),
        ])
        result = _parse_iprscan_json(data)

        assert len(result) == 2
        assert result[0]["id"] == "IPR000276"
        assert result[0]["start"] == 5
        assert result[0]["end"] == 50
        assert result[0]["name"] == "GPCR family"
        assert result[0]["db"] == "PFAM"
        assert result[1]["id"] == "IPR001810"
        assert result[1]["start"] == 60

    def test_family_type_excluded(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        data = _make_iprscan_json([
            _domain_match("IPR000276", "A domain", 5, 50),
            _family_match("IPR999999", 1, 60),
        ])
        result = _parse_iprscan_json(data)
        ids = [d["id"] for d in result]
        assert "IPR999999" not in ids
        assert "IPR000276" in ids

    def test_no_entry_match_excluded(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        data = _make_iprscan_json([
            _domain_match("IPR000276", "A domain", 5, 50),
            _no_entry_match("SSF12345", 10, 40),
        ])
        result = _parse_iprscan_json(data)
        assert len(result) == 1
        assert result[0]["id"] == "IPR000276"

    def test_sorted_by_start(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        data = _make_iprscan_json([
            _domain_match("IPR001810", "later", 60, 120),
            _domain_match("IPR000276", "earlier", 5, 50),
        ])
        result = _parse_iprscan_json(data)
        starts = [d["start"] for d in result]
        assert starts == sorted(starts)

    def test_empty_results(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        assert _parse_iprscan_json({"results": []}) == []

    def test_db_field_preserved_from_library(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        data = _make_iprscan_json([
            _domain_match("IPR000001", "TM domain", 1, 30, "GENE3D"),
        ])
        result = _parse_iprscan_json(data)
        assert result[0]["db"] == "GENE3D"

    def test_missing_library_uses_interpro_fallback(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        match = {
            "signature": {
                "accession": "sig-X",
                "name": "sig-X",
                # no signatureLibraryRelease key
                "entry": {
                    "accession": "IPR999001",
                    "name": "some domain",
                    "type": "DOMAIN",
                },
            },
            "locations": [{"start": 1, "end": 40}],
        }
        result = _parse_iprscan_json(_make_iprscan_json([match]))
        assert len(result) == 1
        assert result[0]["db"] == "InterPro"


# ---------------------------------------------------------------------------
# 2. Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_same_accession_start_end_collapsed(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        m1 = _domain_match("IPR000276", "A domain", 5, 50, "PFAM")
        m2 = _domain_match("IPR000276", "A domain", 5, 50, "GENE3D")
        result = _parse_iprscan_json(_make_iprscan_json([m1, m2]))

        exact = [d for d in result if d["id"] == "IPR000276" and d["start"] == 5 and d["end"] == 50]
        assert len(exact) == 1

    def test_same_accession_different_locations_kept(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        m1 = _domain_match("IPR000276", "A domain", 5, 50)
        m2 = _domain_match("IPR000276", "A domain", 60, 110)
        result = _parse_iprscan_json(_make_iprscan_json([m1, m2]))

        all_matches = [d for d in result if d["id"] == "IPR000276"]
        assert len(all_matches) == 2

    def test_different_accessions_same_coords_kept(self) -> None:
        from kuma_core.kuro.domains import _parse_iprscan_json

        m1 = _domain_match("IPR000001", "Dom A", 5, 50)
        m2 = _domain_match("IPR000002", "Dom B", 5, 50)
        result = _parse_iprscan_json(_make_iprscan_json([m1, m2]))
        assert len(result) == 2


# ---------------------------------------------------------------------------
# 3. Sequence validation
# ---------------------------------------------------------------------------


class TestValidateSequence:
    def test_empty_raises(self) -> None:
        from kuma_core.kuro.domains import _validate_sequence

        with pytest.raises(ValueError, match="empty"):
            _validate_sequence("")

    def test_too_short_raises(self) -> None:
        from kuma_core.kuro.domains import _validate_sequence

        with pytest.raises(ValueError, match="too short"):
            _validate_sequence("MAG")

    def test_invalid_chars_raises(self) -> None:
        from kuma_core.kuro.domains import _validate_sequence

        with pytest.raises(ValueError, match="Invalid amino acid"):
            _validate_sequence("MKTAYIAKQR1234!")

    def test_fasta_header_stripped(self) -> None:
        from kuma_core.kuro.domains import _validate_sequence

        seq = ">sp|Q9AR86|ISPS\nMKTAYIAKQRQISFVKSHFS\n"
        result = _validate_sequence(seq)
        assert result == "MKTAYIAKQRQISFVKSHFS"

    def test_stop_codon_stripped(self) -> None:
        from kuma_core.kuro.domains import _validate_sequence

        result = _validate_sequence("MKTAYIAKQRQISFVK*")
        assert result.endswith("K")
        assert "*" not in result

    def test_lowercase_accepted_and_uppercased(self) -> None:
        from kuma_core.kuro.domains import _validate_sequence

        result = _validate_sequence("mktayiakqrqisfvkshfs")
        assert result == "MKTAYIAKQRQISFVKSHFS"


# ---------------------------------------------------------------------------
# 4. Cache hit
# ---------------------------------------------------------------------------


class TestCacheHit:
    def test_cache_hit_skips_network(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import domains as _dom

        monkeypatch.setattr(_dom, "_cache_path", lambda h: tmp_path / f"{h}.json")

        cached = [{"id": "IPR000276", "name": "GPCR", "start": 5, "end": 50, "db": "PFAM"}]
        seq_clean = _SEQ.upper()
        ref_hash = _seq_hash(seq_clean)
        (tmp_path / f"{ref_hash}.json").write_text(json.dumps(cached))

        call_log: list[str] = []

        def fail_urlopen(*a, **kw):
            call_log.append("called")
            raise AssertionError("urlopen must not be called on cache hit")

        import urllib.request as _req
        with patch.object(_req, "urlopen", side_effect=fail_urlopen):
            domains, cache_hit, computed_hash = _dom.run_interproscan(
                seq_clean, "test@example.com"
            )

        assert cache_hit is True
        assert computed_hash == ref_hash
        assert domains == cached
        assert call_log == []

    def test_result_written_to_cache_on_miss(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import domains as _dom

        monkeypatch.setattr(_dom, "_cache_path", lambda h: tmp_path / f"{h}.json")

        seq_clean = _SEQ.upper()
        ref_hash = _seq_hash(seq_clean)
        result_json = _make_iprscan_json([_domain_match("IPR000276", "GPCR", 5, 50)])

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_mock_resp(b"iprscan5-R-CACHE")
            if call_count[0] == 2:
                return _make_mock_resp(b"FINISHED")
            return _make_mock_resp(json.dumps(result_json).encode())

        import urllib.request as _req
        with patch.object(_req, "urlopen", side_effect=mock_urlopen):
            domains, cache_hit, computed_hash = _dom.run_interproscan(
                seq_clean, "t@example.com", poll_interval=0
            )

        assert cache_hit is False
        assert computed_hash == ref_hash
        assert len(domains) == 1
        assert (tmp_path / f"{ref_hash}.json").exists()
        saved = json.loads((tmp_path / f"{ref_hash}.json").read_text())
        assert saved == domains

    def test_empty_result_is_not_cached(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import domains as _dom

        monkeypatch.setattr(_dom, "_cache_path", lambda h: tmp_path / f"{h}.json")
        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_mock_resp(b"iprscan5-R-EMPTY")
            if call_count[0] == 2:
                return _make_mock_resp(b"FINISHED")
            return _make_mock_resp(json.dumps(_make_iprscan_json([])).encode())

        import urllib.request as _req
        with patch.object(_req, "urlopen", side_effect=mock_urlopen):
            domains, cache_hit, ref_hash = _dom.run_interproscan(
                _SEQ, "t@example.com", poll_interval=0
            )

        assert domains == []
        assert cache_hit is False
        assert not (tmp_path / f"{ref_hash}.json").exists()


# ---------------------------------------------------------------------------
# 5. Timeout / error paths
# ---------------------------------------------------------------------------


class TestTimeoutAndErrors:
    def test_submission_failure_raises_valueerror(self) -> None:
        from kuma_core.kuro.domains import run_interproscan
        import urllib.request as _req

        with patch.object(_req, "urlopen", side_effect=OSError("connection refused")):
            with pytest.raises(ValueError, match="InterProScan submission failed"):
                run_interproscan(_SEQ.upper(), "t@example.com", poll_interval=0)

    def test_job_failure_status_raises_valueerror(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import domains as _dom

        monkeypatch.setattr(_dom, "_cache_path", lambda h: tmp_path / f"{h}.json")

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_mock_resp(b"iprscan5-R-FAIL")
            return _make_mock_resp(b"FAILURE")

        import urllib.request as _req
        with patch.object(_req, "urlopen", side_effect=mock_urlopen):
            with pytest.raises(ValueError, match="failed: FAILURE"):
                _dom.run_interproscan(_SEQ.upper(), "t@example.com", poll_interval=0)

    def test_error_status_raises_valueerror(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import domains as _dom

        monkeypatch.setattr(_dom, "_cache_path", lambda h: tmp_path / f"{h}.json")

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_mock_resp(b"iprscan5-R-ERR")
            return _make_mock_resp(b"ERROR")

        import urllib.request as _req
        with patch.object(_req, "urlopen", side_effect=mock_urlopen):
            with pytest.raises(ValueError, match="failed: ERROR"):
                _dom.run_interproscan(_SEQ.upper(), "t@example.com", poll_interval=0)

    def test_timeout_raises_valueerror(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import domains as _dom

        monkeypatch.setattr(_dom, "_cache_path", lambda h: tmp_path / f"{h}.json")

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_mock_resp(b"iprscan5-R-TOUT")
            return _make_mock_resp(b"RUNNING")

        import urllib.request as _req
        with patch.object(_req, "urlopen", side_effect=mock_urlopen):
            with pytest.raises(ValueError, match="timed out"):
                _dom.run_interproscan(
                    _SEQ.upper(),
                    "t@example.com",
                    poll_interval=0,
                    max_poll_seconds=0,
                )

    def test_result_fetch_failure_raises_valueerror(self, tmp_path, monkeypatch) -> None:
        from kuma_core.kuro import domains as _dom

        monkeypatch.setattr(_dom, "_cache_path", lambda h: tmp_path / f"{h}.json")

        call_count = [0]

        def mock_urlopen(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_mock_resp(b"iprscan5-R-RESFAIL")
            if call_count[0] == 2:
                return _make_mock_resp(b"FINISHED")
            raise OSError("result network error")

        import urllib.request as _req
        with patch.object(_req, "urlopen", side_effect=mock_urlopen):
            with pytest.raises(ValueError, match="result fetch failed"):
                _dom.run_interproscan(_SEQ.upper(), "t@example.com", poll_interval=0)


# ---------------------------------------------------------------------------
# 6. Handler result
# ---------------------------------------------------------------------------


class TestHandlerResult:
    def test_returns_reference_frame_fields(self) -> None:
        fake_domains = [
            {"id": "IPR000276", "name": "GPCR", "start": 5, "end": 50, "db": "PFAM"}
        ]

        with patch(
            "kuma_core.kuro.domains.run_interproscan",
            return_value=(fake_domains, False, "abc123def456"),
        ):
            from sidecar_kuro.handlers.external import handle_annotate_domains_by_sequence

            result = handle_annotate_domains_by_sequence({"sequence": _SEQ})

        assert result["source"] == "interproscan"
        assert result["coordinate_frame"] == "reference"
        assert result["ref_hash"] == "abc123def456"
        assert result["cache_hit"] is False
        assert result["protein_length"] == len(_SEQ)
        assert len(result["domains"]) == 1
        assert result["domains"][0]["id"] == "IPR000276"
        assert "error_msg" not in result

    def test_empty_sequence_raises_valueerror(self) -> None:
        from sidecar_kuro.handlers.external import handle_annotate_domains_by_sequence

        with pytest.raises(ValueError, match="sequence is required"):
            handle_annotate_domains_by_sequence({"sequence": ""})

    def test_no_domains_returns_error_msg(self) -> None:
        with patch(
            "kuma_core.kuro.domains.run_interproscan",
            return_value=([], False, "deadbeef"),
        ):
            from sidecar_kuro.handlers.external import handle_annotate_domains_by_sequence

            result = handle_annotate_domains_by_sequence({"sequence": _SEQ})

        assert result["domains"] == []
        assert result.get("error_msg")

    def test_network_error_returns_error_msg_no_traceback(self) -> None:
        with patch(
            "kuma_core.kuro.domains.run_interproscan",
            side_effect=ValueError("InterProScan submission failed: connection refused"),
        ):
            from sidecar_kuro.handlers.external import handle_annotate_domains_by_sequence

            result = handle_annotate_domains_by_sequence({"sequence": _SEQ})

        assert result["domains"] == []
        assert result["source"] == "error"
        assert "connection refused" in (result.get("error_msg") or "")
        assert "Traceback" not in (result.get("error_msg") or "")

    def test_invalid_sequence_returns_error_msg(self) -> None:
        from sidecar_kuro.handlers.external import handle_annotate_domains_by_sequence

        result = handle_annotate_domains_by_sequence({"sequence": "MAG"})
        assert result["domains"] == []
        assert result["source"] == "error"
        assert result.get("error_msg")

    def test_caller_supplied_ref_hash_preserved_on_error(self) -> None:
        """ref_hash provided by caller is echoed back when network fails."""
        with patch(
            "kuma_core.kuro.domains.run_interproscan",
            side_effect=ValueError("timed out"),
        ):
            from sidecar_kuro.handlers.external import handle_annotate_domains_by_sequence

            result = handle_annotate_domains_by_sequence({
                "sequence": _SEQ,
                "ref_hash": "custom-hash-from-caller",
            })

        assert result["ref_hash"] == "custom-hash-from-caller"

    def test_cache_hit_propagated(self) -> None:
        fake_domains = [
            {"id": "IPR000276", "name": "GPCR", "start": 5, "end": 50, "db": "PFAM"}
        ]

        with patch(
            "kuma_core.kuro.domains.run_interproscan",
            return_value=(fake_domains, True, "hash-from-cache"),
        ):
            from sidecar_kuro.handlers.external import handle_annotate_domains_by_sequence

            result = handle_annotate_domains_by_sequence({"sequence": _SEQ})

        assert result["cache_hit"] is True
        assert result["ref_hash"] == "hash-from-cache"


# ---------------------------------------------------------------------------
# 7. Dispatcher registries
# ---------------------------------------------------------------------------


class TestDispatcherRegistration:
    _METHOD = "annotate_domains_by_sequence"

    def test_in_methods_dict(self) -> None:
        from sidecar_kuro.dispatcher import _METHODS

        assert self._METHOD in _METHODS, f"'{self._METHOD}' not in _METHODS"

    def test_handler_callable(self) -> None:
        from sidecar_kuro.dispatcher import _METHODS

        assert callable(_METHODS[self._METHOD])

    def test_in_async_methods(self) -> None:
        from sidecar_kuro.dispatcher import _ASYNC_METHODS

        assert self._METHOD in _ASYNC_METHODS, f"'{self._METHOD}' not in _ASYNC_METHODS"

    def test_existing_fetch_domains_unchanged(self) -> None:
        """Regression: existing fetch_domains must still be registered."""
        from sidecar_kuro.dispatcher import _METHODS, _ASYNC_METHODS

        assert "fetch_domains" in _METHODS
        assert "fetch_domains" in _ASYNC_METHODS
