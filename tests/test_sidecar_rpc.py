"""Integration tests for sidecar RPC dispatch.

Tests each JSON-RPC handler via the dispatch() function,
capturing stdout JSON responses with io.StringIO.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import time
from dataclasses import replace as dc_replace
from pathlib import Path

import pytest

# sidecar package lives in python-core/
_PROJECT_ROOT = Path(__file__).parent.parent
_SIDECAR_DIR = _PROJECT_ROOT / "python-core"
if str(_SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(_SIDECAR_DIR))

from sidecar_kuro.dispatcher import dispatch  # noqa: E402
from sidecar_kuro.core import _state, SidecarState  # noqa: E402
from sidecar_kuro.handlers.external import (  # noqa: E402
    _candidate_rank_key,
    _organism_match_score,
    _sequence_identity,
)
import sidecar_kuro.handlers.design as _design_handlers  # noqa: E402
import sidecar_kuro.core as _sidecar_core  # noqa: E402

FIXTURES_DIR = _PROJECT_ROOT / "fixtures"
FASTA_PATH = str(FIXTURES_DIR / "pSHCE-dmpR.gb")
MUTATIONS_CSV = str(FIXTURES_DIR / "mutation_list_insilico_test.csv")
TARGET_START = 1790


def _minimal_workspace_v2() -> dict:
    return {
        "version": 2,
        "inputs": {
            "fastaPath": FASTA_PATH,
            "mutationInputMode": "text",
            "mutationText": "Q232A",
            "evolveproCsvPath": "",
            "selectedGene": "",
        },
        "settings": {
            "codonStrategy": "closest",
            "maxPrimers": 95,
            "tmFwdTarget": 62.0,
            "tmRevTarget": 58.0,
            "tmOverlapTarget": 42.0,
            "gcMin": 40.0,
            "gcMax": 60.0,
        },
        "results": {
            "designResults": [],
            "successCount": 0,
            "totalCount": 0,
            "failedMutations": [],
            "plateMappings": [],
            "dedupInfo": {},
            "manuallySwapped": {},
            "customCandidates": {},
        },
        "ui": {
            "tableSorting": [],
        },
    }


def _dispatch_and_parse(request: dict, timeout: float = 30.0) -> dict:
    """Call dispatch() and capture the JSON response from stdout.

    For async methods that run in background threads, waits up to *timeout*
    seconds for a response message matching the request id to appear. Skips
    intermediate `progress` notifications so the returned value is always
    the final result or error object.
    """
    import time as _time

    req_id = request.get("id")
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        dispatch(request)
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            raw = buf.getvalue()
            for ln in raw.split("\n"):
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    msg = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == req_id and ("result" in msg or "error" in msg):
                    return msg
            _time.sleep(0.05)
    finally:
        sys.stdout = old_stdout
    raise AssertionError(
        f"no response with id={req_id} within {timeout}s; stdout={buf.getvalue()!r}"
    )


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
        # Design now follows the paper targets (62/58/42) + min_3prime_dist 4 on the
        # fixed Benchling Tm scale, so the yield changed: 5/12.
        assert designed_primers["success_count"] >= 5

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

    def test_non_finite_diagnostics_are_sanitized(self, monkeypatch, loaded_fasta):
        results, all_cands, failures = _design_handlers.design_sdm_primers(
            fasta_path=Path(FASTA_PATH),
            target_start=TARGET_START,
            mutations_csv=Path(MUTATIONS_CSV),
            polymerase="Q5",
            overlap_len=18,
        )
        bad = dc_replace(
            results[0],
            hairpin_tm_fwd=float("nan"),
            homodimer_tm_rev=float("inf"),
            synthesis_score_fwd=float("nan"),
        )

        def fake_design_sdm_primers(**kwargs):
            patched_results = [bad, *results[1:]]
            patched_candidates = dict(all_cands)
            patched_candidates[bad.mutation.raw] = [bad]
            return patched_results, patched_candidates, failures

        monkeypatch.setattr(_design_handlers, "design_sdm_primers", fake_design_sdm_primers)

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
        first = resp["result"]["results"][0]
        assert "hairpin_tm_fwd" not in first
        assert "homodimer_tm_rev" not in first
        assert "synthesis_score_fwd" not in first


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

    def test_plate_map_updates_after_swap(self, designed_primers):
        mutation = designed_primers["results"][0]["mutation"]
        candidates_resp = _rpc("get_alternatives", {"mutation": mutation})
        candidates = candidates_resp["result"]["candidates"]
        if len(candidates) < 2:
            pytest.skip("Need at least two candidates to verify swap state sync")

        swapped = _rpc(
            "swap_primer",
            {"mutation": mutation, "candidate_idx": 1, "swap_type": "both"},
        )["result"]
        plate = _rpc("get_plate_map")["result"]

        forward_mapping = next(
            m
            for m in plate["mappings"]
            if m["primer_type"] == "forward" and m["mutation"] == mutation
        )
        assert forward_mapping["sequence"] == swapped["forward_seq"]
        assert swapped["reverse_seq"] in plate["dedup_info"]
        assert mutation in plate["dedup_info"][swapped["reverse_seq"]]


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

        test_data = _minimal_workspace_v2()
        save_resp = _rpc(
            "save_workspace", {"filepath": tmp_path, "data": test_data}
        )
        assert "result" in save_resp
        assert save_resp["result"]["success"] is True

        load_resp = _rpc("load_workspace", {"filepath": tmp_path})
        assert "result" in load_resp
        assert load_resp["result"] == test_data

        Path(tmp_path).unlink(missing_ok=True)

    def test_save_missing_params(self):
        resp = _rpc("save_workspace", {})
        assert "error" in resp

    def test_save_rejects_invalid_workspace_shape(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name

        resp = _rpc(
            "save_workspace",
            {
                "filepath": tmp_path,
                "data": {"version": 2, "inputs": {}, "settings": {}, "results": {}, "ui": {}},
            },
        )
        assert "error" in resp
        Path(tmp_path).unlink(missing_ok=True)

    def test_load_nonexistent_file(self):
        resp = _rpc("load_workspace", {"filepath": "/tmp/nonexistent_ws_xyz.json"})
        assert "error" in resp

    def test_load_rejects_invalid_workspace_shape(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f:
            json.dump({"version": 2, "inputs": {}, "settings": {}, "results": {}, "ui": {}}, f)
            tmp_path = f.name

        resp = _rpc("load_workspace", {"filepath": tmp_path})
        assert "error" in resp
        Path(tmp_path).unlink(missing_ok=True)


# ── 9. cancel_design ─────────────────────────────────────────────────────

class TestCancelDesign:
    def test_cancel_reports_idle_state(self):
        resp = _rpc("cancel_design")
        assert "result" in resp
        assert resp["result"]["cancelled"] is True
        assert resp["result"]["active_design"] is False

    def test_cancel_reaches_active_design(self, monkeypatch):
        started = threading.Event()

        def slow_design(*args, cancel_check=None, **kwargs):
            started.set()
            for _ in range(200):
                if cancel_check and cancel_check():
                    return [], {}, {}
                time.sleep(0.01)
            return [], {}, {}

        monkeypatch.setattr(_design_handlers, "design_sdm_primers", slow_design)

        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            dispatch({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "design_sdm_primers",
                "params": {
                    "fasta_path": FASTA_PATH,
                    "target_start": TARGET_START,
                    "mutations_csv_or_text": "Q232A",
                    "polymerase": "Q5",
                    "overlap_len": 18,
                },
            })
            assert started.wait(2.0)

            dispatch({"jsonrpc": "2.0", "id": 2, "method": "cancel_design", "params": {}})

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
                if any('"id": 1' in ln for ln in lines) and any('"id": 2' in ln for ln in lines):
                    break
                time.sleep(0.05)
        finally:
            sys.stdout = old_stdout

        responses = [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]
        cancel_resp = next(item for item in responses if item.get("id") == 2)
        design_resp = next(item for item in responses if item.get("id") == 1 and "result" in item)

        assert cancel_resp["result"]["cancelled"] is True
        assert cancel_resp["result"]["active_design"] is True
        assert design_resp["result"]["cancelled"] is True


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


class TestOrganismAwareUniprotRanking:
    def test_organism_match_score_prefers_exact_then_species_then_genus(self):
        assert _organism_match_score("Pseudomonas putida", "Pseudomonas putida") == (3, 1.0)
        assert _organism_match_score("Pseudomonas putida", "Pseudomonas putida KT2440") == (2, 1.0)
        assert _organism_match_score("Pseudomonas putida", "Pseudomonas aeruginosa") == (1, 1.0)

    def test_candidate_rank_key_uses_organism_to_break_identity_ties(self):
        query = "Pseudomonas putida"
        exact = {
            "accession": "A0A000",
            "organism": "Pseudomonas putida",
            "identity": 87.5,
            "length": 510,
        }
        species = {
            "accession": "A0A001",
            "organism": "Pseudomonas putida KT2440",
            "identity": 87.5,
            "length": 530,
        }
        genus = {
            "accession": "A0A002",
            "organism": "Pseudomonas aeruginosa",
            "identity": 87.5,
            "length": 560,
        }
        other = {
            "accession": "A0A003",
            "organism": "Escherichia coli",
            "identity": 87.5,
            "length": 700,
        }

        ranked = sorted(
            [other, genus, species, exact],
            key=lambda c: _candidate_rank_key(query, c),
            reverse=True,
        )

        assert [c["accession"] for c in ranked] == ["A0A000", "A0A001", "A0A002", "A0A003"]

    def test_candidate_rank_key_keeps_higher_identity_above_better_organism(self):
        query = "Pseudomonas putida"
        better_identity = {
            "accession": "A0A010",
            "organism": "Escherichia coli",
            "identity": 95.0,
            "length": 400,
        }
        better_organism = {
            "accession": "A0A011",
            "organism": "Pseudomonas putida",
            "identity": 90.0,
            "length": 400,
        }

        ranked = sorted(
            [better_organism, better_identity],
            key=lambda c: _candidate_rank_key(query, c),
            reverse=True,
        )

        assert [c["accession"] for c in ranked] == ["A0A010", "A0A011"]


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

    def test_export_order_accepts_frontend_results_payload(self, designed_primers):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp_path = f.name
        try:
            _sidecar_core._state = SidecarState()
            resp = _rpc(
                "export_order",
                {
                    "filepath": tmp_path,
                    "format": "idt",
                    "results": [
                        {
                            "mutation": r["mutation"],
                            "forward_seq": r["forward_seq"],
                            "reverse_seq": r["reverse_seq"],
                        }
                        for r in designed_primers["results"]
                    ],
                },
            )
            assert "result" in resp, f"export_order with payload failed: {resp}"
            assert resp["result"]["success"] is True
            assert resp["result"]["primer_count"] == len(designed_primers["results"]) * 2
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


class TestExportMapping:
    def test_export_mapping_accepts_frontend_payload(self, designed_primers):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            tmp_path = f.name
        try:
            plate_resp = _rpc("get_plate_map")
            plate = plate_resp["result"]
            _sidecar_core._state = SidecarState()
            resp = _rpc(
                "export_mapping",
                {
                    "filepath": tmp_path,
                    "format": "echo",
                    "mappings": plate["mappings"],
                    "dedup_info": plate["dedup_info"],
                },
            )
            assert "result" in resp, f"export_mapping with payload failed: {resp}"
            assert resp["result"]["success"] is True
            assert resp["result"]["primer_count"] > 0
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_export_mapping_rejects_fractional_echo_transfer_volume(self, designed_primers):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            tmp_path = f.name
        try:
            plate_resp = _rpc("get_plate_map")
            plate = plate_resp["result"]
            resp = _rpc(
                "export_mapping",
                {
                    "filepath": tmp_path,
                    "format": "echo",
                    "transfer_vol": 100.5,
                    "mappings": plate["mappings"],
                    "dedup_info": plate["dedup_info"],
                },
            )
            assert "error" in resp
            assert "whole number" in resp["error"]["message"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_export_mapping_rejects_non_positive_janus_transfer_volume(self, designed_primers):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp_path = f.name
        try:
            plate_resp = _rpc("get_plate_map")
            plate = plate_resp["result"]
            resp = _rpc(
                "export_mapping",
                {
                    "filepath": tmp_path,
                    "format": "janus",
                    "transfer_vol": 0,
                    "mappings": plate["mappings"],
                    "dedup_info": plate["dedup_info"],
                },
            )
            assert "error" in resp
            assert "greater than 0" in resp["error"]["message"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestRetryFailedMutation:
    def test_retry_accepts_current_design_context_params(self, loaded_fasta):
        resp = _rpc(
            "retry_failed_mutation",
            {
                "mutation": "Q232A",
                "fasta_path": FASTA_PATH,
                "target_start": TARGET_START,
                "polymerase": "Q5",
                "organism": "ecoli",
                "tm_fwd_target": 62.0,
                "tm_rev_target": 58.0,
                "tm_overlap_target": 42.0,
                "gc_min": 40.0,
                "gc_max": 60.0,
                "fwd_len_min": 17,
                "fwd_len_max": 39,
                "rev_len_min": 19,
                "rev_len_max": 27,
                "tol_max": 5.0,
                "codon_strategy": "closest",
            },
        )
        assert "result" in resp, f"retry_failed_mutation failed: {resp}"
        assert "candidates" in resp["result"]

# ── 15. load_evolvepro_csv — structural diversity 3D Cα coords wiring ─────


class TestStructuralDiversity3DCoords:
    """Regression guard for the app's structural-diversity 3D wiring.

    The structural selector must receive cached AlphaFold Cα coords via
    ``structure_accession``; the coords change the selection vs the positional
    fallback, so a matching accession must reproduce the 3D result and a
    non-matching one must fall back.
    """

    ACC = "TESTACC1"

    @staticmethod
    def _write_csv(tmp_path) -> str:
        # 4 single-mut variants at distinct positions; y_pred descending so the
        # maximin seed (max fitness) is A10G.
        csv = tmp_path / "df_test.csv"
        csv.write_text(
            "variant,y_pred\n"
            "A10G,0.9\n"
            "A20G,0.8\n"
            "A30G,0.7\n"
            "A40G,0.6\n"
        )
        return str(csv)

    @staticmethod
    def _coords():
        # 1-based Cα coords. In sequence space pos40 is farthest from pos10,
        # but in 3D space pos20 is farthest (pos40 sits right next to pos10),
        # so 3D vs positional selection diverge on the second pick.
        coords = [None] * 41
        coords[10] = (0.0, 0.0, 0.0)
        coords[20] = (100.0, 0.0, 0.0)
        coords[30] = (50.0, 0.0, 0.0)
        coords[40] = (1.0, 0.0, 0.0)
        return coords

    def test_cached_coords_drive_3d_structural_selection(self, tmp_path):
        from kuma_core.kuro.evolvepro import load_evolvepro_csv

        path = self._write_csv(tmp_path)
        coords = self._coords()

        expected_3d = load_evolvepro_csv(
            path, top_n=2, structural_diversity=True, ca_coords=coords,
            structural_kappa=0.0,
        )["variants"]
        expected_pos = load_evolvepro_csv(
            path, top_n=2, structural_diversity=True, ca_coords=None,
            structural_kappa=0.0,
        )["variants"]
        # Coords must actually change the outcome, else the test proves nothing.
        assert expected_3d != expected_pos
        assert expected_3d == ["A10G", "A20G"]
        assert expected_pos == ["A10G", "A40G"]

        # RPC with a matching accession + cached coords → 3D path.
        _sidecar_core._state.ca_coords = coords
        _sidecar_core._state.ca_coords_accession = self.ACC
        resp = _rpc("load_evolvepro_csv", {
            "filepath": path, "top_n": 2,
            "structural_diversity": True, "structure_accession": self.ACC,
            "structural_kappa": 0.0, "anchor_variants": [],
        })
        assert resp["result"]["variants"] == expected_3d

    def test_missing_accession_falls_back_to_positional(self, tmp_path):
        path = self._write_csv(tmp_path)
        coords = self._coords()
        # Coords cached under a different accession → not resolved → fallback.
        _sidecar_core._state.ca_coords = coords
        _sidecar_core._state.ca_coords_accession = "OTHERACC"
        resp = _rpc("load_evolvepro_csv", {
            "filepath": path, "top_n": 2,
            "structural_diversity": True, "structure_accession": self.ACC,
            "structural_kappa": 0.0, "anchor_variants": [],
        })
        assert resp["result"]["variants"] == ["A10G", "A40G"]
