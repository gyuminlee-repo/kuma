"""Integration tests for sidecar RPC dispatch.

Tests each JSON-RPC handler via the dispatch() function,
capturing stdout JSON responses with io.StringIO.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

# sidecar package lives in python-core/
_PROJECT_ROOT = Path(__file__).parent.parent
_SIDECAR_DIR = _PROJECT_ROOT / "python-core"
if str(_SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(_SIDECAR_DIR))

from sidecar.dispatcher import dispatch  # noqa: E402
from sidecar.core import _state, _cancel_event, SidecarState  # noqa: E402
from sidecar.handlers.external import _sequence_identity  # noqa: E402
import sidecar.core as _sidecar_core  # noqa: E402

FIXTURES_DIR = _PROJECT_ROOT / "fixtures"
FASTA_PATH = str(FIXTURES_DIR / "pSHCE-dmpR.fa")
MUTATIONS_CSV = str(FIXTURES_DIR / "mutation_list_insilico_test.csv")
TARGET_START = 1790


def _dispatch_and_parse(request: dict, timeout: float = 30.0) -> dict:
    """Call dispatch() and capture the JSON response from stdout.

    For async methods that run in background threads, waits up to *timeout*
    seconds for the response to appear on the redirected stdout.
    """
    import time as _time
    import threading

    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        dispatch(request)
        # Wait for response — async methods write from background threads
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            if buf.getvalue().strip():
                break
            _time.sleep(0.1)
    finally:
        sys.stdout = old_stdout
    raw = buf.getvalue().strip()
    # dispatch may emit multiple lines (progress + result); take the last one
    lines = [ln for ln in raw.split("\n") if ln.strip()]
    assert lines, "dispatch produced no output"
    return json.loads(lines[-1])


def _rpc(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    """Build a JSON-RPC request, dispatch it, return the parsed response."""
    return _dispatch_and_parse(
        {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    )


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_state():
    """Reset sidecar state before each test."""
    _sidecar_core._state = SidecarState()
    _sidecar_core._cancel_event.clear()
    yield


@pytest.fixture()
def loaded_fasta() -> dict:
    """Pre-load the FASTA fixture, return the response result."""
    resp = _rpc("load_fasta", {"filepath": FASTA_PATH})
    assert "result" in resp, f"load_fasta failed: {resp}"
    return resp["result"]


@pytest.fixture()
def designed_primers(loaded_fasta) -> dict:
    """Run a full design pipeline, return the response result."""
    resp = _rpc(
        "design_sdm_primers",
        {
            "fasta_path": FASTA_PATH,
            "target_start": TARGET_START,
            "mutations_csv_or_text": MUTATIONS_CSV,
            "polymerase": "Q5",
            "overlap_len": 18,
        },
    )
    assert "result" in resp, f"design_sdm_primers failed: {resp}"
    return resp["result"]


# ── 1. list_polymerases ──────────────────────────────────────────────────

class TestListPolymerases:
    def test_returns_list(self):
        resp = _rpc("list_polymerases")
        assert "result" in resp
        profiles = resp["result"]
        assert isinstance(profiles, list)
        assert len(profiles) > 0

    def test_each_profile_has_required_keys(self):
        resp = _rpc("list_polymerases")
        for p in resp["result"]:
            assert "name" in p
            assert "manufacturer" in p
            assert "fidelity" in p

    def test_q5_present(self):
        resp = _rpc("list_polymerases")
        names = [p["name"] for p in resp["result"]]
        assert "Q5" in names


# ── 2. load_fasta ────────────────────────────────────────────────────────

class TestLoadFasta:
    def test_returns_header_and_length(self, loaded_fasta):
        assert "header" in loaded_fasta
        assert loaded_fasta["seq_length"] > 0

    def test_genes_structure(self, loaded_fasta):
        genes = loaded_fasta["genes"]
        assert isinstance(genes, list)
        if genes:
            gene = genes[0]
            for key in ("gene", "product", "cds_start", "cds_end", "aa_length"):
                assert key in gene, f"Missing key: {key}"

    def test_missing_filepath_returns_error(self):
        resp = _rpc("load_fasta", {})
        assert "error" in resp

    def test_nonexistent_file_returns_error(self):
        resp = _rpc("load_fasta", {"filepath": "/tmp/nonexistent_xyz.fa"})
        assert "error" in resp


# ── 3. parse_mutations_text ──────────────────────────────────────────────

class TestParseMutationsText:
    def test_valid_single_mutation(self):
        resp = _rpc("parse_mutations_text", {"text": "Q232A"})
        result = resp["result"]
        assert len(result["parsed"]) == 1
        assert result["parsed"][0]["wt_aa"] == "Q"
        assert result["parsed"][0]["position"] == 232
        assert result["parsed"][0]["mt_aa"] == "A"
        assert len(result["errors"]) == 0

    def test_multiple_mutations(self):
        resp = _rpc("parse_mutations_text", {"text": "Q232A\nY233A\nE335A"})
        result = resp["result"]
        assert len(result["parsed"]) == 3

    def test_invalid_mutation_returns_error_entry(self):
        resp = _rpc("parse_mutations_text", {"text": "INVALID_MUTATION"})
        result = resp["result"]
        assert len(result["errors"]) > 0

    def test_empty_text_returns_error(self):
        resp = _rpc("parse_mutations_text", {"text": ""})
        assert "error" in resp

    def test_comments_are_skipped(self):
        resp = _rpc("parse_mutations_text", {"text": "# comment\nQ232A"})
        result = resp["result"]
        assert len(result["parsed"]) == 1


# ── 4. design_sdm_primers ───────────────────────────────────────────────

class TestDesignSdmPrimers:
    def test_full_pipeline_structure(self, designed_primers):
        assert "results" in designed_primers
        assert "success_count" in designed_primers
        assert "total_count" in designed_primers
        assert "failed_mutations" in designed_primers

    def test_majority_success(self, designed_primers):
        assert designed_primers["success_count"] >= 10

    def test_result_fields(self, designed_primers):
        for r in designed_primers["results"]:
            assert "mutation" in r
            assert "forward_seq" in r
            assert "reverse_seq" in r
            assert "tm_no_fwd" in r
            assert "tm_no_rev" in r
            assert "tm_overlap" in r

    def test_text_input_mode(self, loaded_fasta):
        resp = _rpc(
            "design_sdm_primers",
            {
                "fasta_path": FASTA_PATH,
                "target_start": TARGET_START,
                "mutations_csv_or_text": "Q232A\nY233A",
                "polymerase": "Q5",
                "overlap_len": 18,
            },
        )
        assert "result" in resp
        assert resp["result"]["success_count"] >= 1

    def test_missing_fasta_returns_error(self):
        resp = _rpc("design_sdm_primers", {"mutations_csv_or_text": "Q232A"})
        assert "error" in resp


# ── 5. get_plate_map ─────────────────────────────────────────────────────

class TestGetPlateMap:
    def test_plate_map_structure(self, designed_primers):
        resp = _rpc("get_plate_map")
        assert "result" in resp
        result = resp["result"]
        assert "mappings" in result
        assert "dedup_info" in result

    def test_plate_map_well_format(self, designed_primers):
        resp = _rpc("get_plate_map")
        for m in resp["result"]["mappings"]:
            assert "well" in m
            assert "primer_name" in m
            assert "sequence" in m
            assert "primer_type" in m
            assert "mutation" in m

    def test_no_design_returns_error(self):
        resp = _rpc("get_plate_map")
        assert "error" in resp


# ── 6. get_alternatives ──────────────────────────────────────────────────

class TestGetAlternatives:
    def test_returns_candidates(self, designed_primers):
        mutation = designed_primers["results"][0]["mutation"]
        resp = _rpc("get_alternatives", {"mutation": mutation})
        assert "result" in resp
        result = resp["result"]
        assert result["mutation"] == mutation
        assert isinstance(result["candidates"], list)

    def test_missing_mutation_param(self):
        resp = _rpc("get_alternatives", {})
        assert "error" in resp

    def test_nonexistent_mutation(self, designed_primers):
        resp = _rpc("get_alternatives", {"mutation": "ZZZZZ"})
        result = resp["result"]
        assert result["candidates"] == []


# ── 7. evaluate_primer ───────────────────────────────────────────────────

class TestEvaluatePrimer:
    def test_evaluate_structure(self, loaded_fasta):
        resp = _rpc(
            "evaluate_primer",
            {
                "mutation": "custom",
                "fasta_path": FASTA_PATH,
                "forward_seq": "ATGCATGCATGCATGCATGC",
                "reverse_seq": "GCATGCATGCATGCATGCAT",
                "overlap_len": 18,
            },
        )
        assert "result" in resp
        result = resp["result"]
        assert "tm_no_fwd" in result
        assert "tm_no_rev" in result
        assert "forward_seq" in result
        assert "reverse_seq" in result

    def test_missing_sequences_returns_error(self, loaded_fasta):
        resp = _rpc(
            "evaluate_primer",
            {"fasta_path": FASTA_PATH, "forward_seq": "", "reverse_seq": ""},
        )
        assert "error" in resp

    def test_invalid_bases_returns_error(self, loaded_fasta):
        resp = _rpc(
            "evaluate_primer",
            {
                "fasta_path": FASTA_PATH,
                "forward_seq": "ATGCXYZ",
                "reverse_seq": "GCATGCATGCATGCATGCAT",
            },
        )
        assert "error" in resp


# ── 8. save_workspace / load_workspace ───────────────────────────────────

class TestWorkspaceRoundTrip:
    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name

        test_data = {"version": 1, "results": [{"mutation": "Q232A"}]}
        save_resp = _rpc(
            "save_workspace", {"filepath": tmp_path, "data": test_data}
        )
        assert "result" in save_resp
        assert save_resp["result"]["success"] is True

        load_resp = _rpc("load_workspace", {"filepath": tmp_path})
        assert "result" in load_resp
        assert load_resp["result"]["version"] == 1
        assert load_resp["result"]["results"][0]["mutation"] == "Q232A"

        Path(tmp_path).unlink(missing_ok=True)

    def test_save_missing_params(self):
        resp = _rpc("save_workspace", {})
        assert "error" in resp

    def test_load_nonexistent_file(self):
        resp = _rpc("load_workspace", {"filepath": "/tmp/nonexistent_ws_xyz.json"})
        assert "error" in resp


# ── 9. cancel_design ─────────────────────────────────────────────────────

class TestCancelDesign:
    def test_cancel_sets_event(self):
        assert not _sidecar_core._cancel_event.is_set()
        resp = _rpc("cancel_design")
        assert "result" in resp
        assert resp["result"]["cancelled"] is True
        assert _sidecar_core._cancel_event.is_set()


# ── 10. GeneInfo extended fields ─────────────────────────────────────────

class TestGeneInfoExtended:
    def test_genes_include_extended_fields(self, loaded_fasta):
        """Verify organism, translation, uniprot_accession fields are returned."""
        genes = loaded_fasta["genes"]
        if genes:
            gene = genes[0]
            for key in ("organism", "translation", "uniprot_accession"):
                assert key in gene, f"Missing extended key: {key}"


# ── 11. search_uniprot ──────────────────────────────────────────────────

class TestSearchUniprot:
    def test_missing_params_returns_error(self):
        resp = _rpc("search_uniprot", {})
        assert "error" in resp

    def test_returns_candidates_structure(self):
        """Verify the response structure (may have 0 candidates if offline)."""
        resp = _rpc("search_uniprot", {
            "gene_name": "dmpR",
            "organism": "",
            "translation": "",
            "known_accession": "",
        })
        result = resp.get("result")
        if result:
            assert "candidates" in result
            assert "auto_selected" in result
            assert isinstance(result["candidates"], list)


# ── 12. _sequence_identity ──────────────────────────────────────────────

class TestSequenceIdentity:
    def test_identical_sequences(self):
        assert _sequence_identity("MVKLT", "MVKLT") == 100.0

    def test_empty_sequences(self):
        assert _sequence_identity("", "") == 0.0
        assert _sequence_identity("MVKLT", "") == 0.0

    def test_partial_match(self):
        # 2/5 match (M, V match; K vs X, L vs X, T vs X do not)
        identity = _sequence_identity("MVKLT", "MVXXX")
        assert identity == 40.0

    def test_different_lengths_substring(self):
        # "MV" is a substring of "MVKLT" → treated as 100% (signal peptide trimming)
        identity = _sequence_identity("MV", "MVKLT")
        assert identity == 100.0

    def test_different_lengths_no_substring(self):
        # "MX" is NOT a substring of "MVKLT" → positional: 1/5 = 20%
        identity = _sequence_identity("MX", "MVKLT")
        assert identity == 20.0


# ── 13. list_organisms ──────────────────────────────────────────────────

class TestListOrganisms:
    def test_returns_list(self):
        resp = _rpc("list_organisms")
        assert "result" in resp
        organisms = resp["result"]
        assert isinstance(organisms, list)
        assert len(organisms) == 4

    def test_each_organism_has_required_keys(self):
        resp = _rpc("list_organisms")
        for org in resp["result"]:
            assert "key" in org
            assert "name" in org
            assert "taxid" in org

    def test_ecoli_present(self):
        resp = _rpc("list_organisms")
        keys = [o["key"] for o in resp["result"]]
        assert "ecoli" in keys

    def test_all_four_organisms_present(self):
        resp = _rpc("list_organisms")
        keys = {o["key"] for o in resp["result"]}
        expected = {"ecoli", "bsubtilis", "scerevisiae", "hsapiens"}
        assert keys == expected


# ── 14. export_order ───────────────────────────────────────────────────

class TestExportOrder:
    def test_no_design_returns_error(self):
        resp = _rpc("export_order", {"filepath": "/tmp/test_idt.csv", "format": "idt"})
        assert "error" in resp

    def test_idt_export_after_design(self, designed_primers):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp_path = f.name
        try:
            resp = _rpc("export_order", {"filepath": tmp_path, "format": "idt"})
            assert "result" in resp, f"export_order failed: {resp}"
            result = resp["result"]
            assert result["success"] is True
            assert result["format"] == "idt"
            assert result["primer_count"] > 0
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_twist_export_after_design(self, designed_primers):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp_path = f.name
        try:
            resp = _rpc("export_order", {"filepath": tmp_path, "format": "twist"})
            assert "result" in resp, f"export_order failed: {resp}"
            result = resp["result"]
            assert result["success"] is True
            assert result["format"] == "twist"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_invalid_format_returns_error(self, designed_primers):
        resp = _rpc("export_order", {"filepath": "/tmp/test.csv", "format": "invalid_format"})
        assert "error" in resp

    def test_design_with_organism_param(self, loaded_fasta):
        """Verify design_sdm_primers accepts organism parameter."""
        resp = _rpc(
            "design_sdm_primers",
            {
                "fasta_path": FASTA_PATH,
                "target_start": TARGET_START,
                "mutations_csv_or_text": "Q232A\nY233A",
                "polymerase": "Q5",
                "overlap_len": 18,
                "organism": "ecoli",
            },
        )
        assert "result" in resp
        assert resp["result"]["success_count"] >= 1

    def test_design_with_unknown_organism_returns_error(self, loaded_fasta):
        """Unknown organism should return a validation error."""
        resp = _rpc(
            "design_sdm_primers",
            {
                "fasta_path": FASTA_PATH,
                "target_start": TARGET_START,
                "mutations_csv_or_text": "Q232A",
                "polymerase": "Q5",
                "overlap_len": 18,
                "organism": "unknown_organism_xyz",
            },
        )
        assert "error" in resp


# ── Edge: unknown method ─────────────────────────────────────────────────

class TestUnknownMethod:
    def test_unknown_method_returns_error(self):
        resp = _rpc("nonexistent_method_xyz")
        assert "error" in resp
        assert resp["error"]["code"] == -32601
