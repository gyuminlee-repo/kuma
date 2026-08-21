"""Run manifests must name what produced the primers they sit next to.

Three things were missing before, and each is pinned here.

- Every ``build_run_manifest`` call in the kuro export handlers passed
  ``inputs={}``, so the manifest never named the fasta the design read, even
  though the UI describes that field as "input checksum, exact input bytes".
- ``handlers/design.py`` recorded nothing at all, so the design parameters were
  gone the moment the call returned.
- ``retry_failed_mutation``, ``swap_primer`` and ``commit_design_result``
  rewrite results after a design with parameters of their own. A workbook whose
  reverse primer is 29 bp under a 27 bp default cap is the visible symptom, and
  the first design's parameters alone cannot explain it.

The manifest schema is NOT touched: everything new rides in ``extra``, which
``src/lib/runManifest.ts`` types as free-form and its ``isRunManifest`` guard
does not inspect. A schema bump would make the frontend reject every manifest
already on disk.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from kuma_core.shared.run_manifest import compute_input_sha256
from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.design import (
    handle_commit_design_result,
    handle_design_sdm_primers,
    handle_retry_failed,
    handle_swap_primer,
)
from sidecar_kuro.handlers.export import (
    handle_export_excel,
    handle_export_mapping,
    handle_export_order,
)
from tests.conftest import TARGET_START
from tests.shared.test_run_manifest import EXPECTED_SCHEMA_VERSION

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
GENBANK = FIXTURES_DIR / "pSHCE-dmpR.gb"
EVOLVEPRO_CSV = FIXTURES_DIR / "dmpR_evolvepro.csv"

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture
def restore_state():
    """A real design mutates module-level state; put it back afterwards."""
    with _state_lock:
        saved = (
            list(_state.results),
            dict(_state.candidates),
            list(_state.plate_mappings),
            dict(_state.dedup_info or {}),
            _state.design_provenance,
            list(_state.interventions),
        )
    yield
    with _state_lock:
        (
            _state.results,
            _state.candidates,
            _state.plate_mappings,
            _state.dedup_info,
            _state.design_provenance,
            _state.interventions,
        ) = saved


@pytest.fixture(scope="module")
def mutation_lines() -> list[str]:
    with EVOLVEPRO_CSV.open() as fh:
        return [row["mutation"] for row in csv.DictReader(fh)][:6]


def _design(mutation_text: str, **overrides) -> dict:
    params = {
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "mutations_csv_or_text": mutation_text,
        "polymerase": "KOD",
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": False,
    }
    params.update(overrides)
    return handle_design_sdm_primers(params)


def _designed(mutation_lines: list[str], **overrides) -> str:
    """Run a design that produces at least one result, return its first mutation."""
    text = "\n".join(mutation_lines)
    result = _design(text, **overrides)
    assert result["success_count"] > 0, "fixture must design at least one primer"
    return result["results"][0]["mutation"]


def _export_excel_manifest(tmp_path: Path, name: str = "plate") -> dict:
    out = tmp_path / f"{name}.xlsx"
    handle_export_excel({"filepath": str(out)})
    return json.loads((tmp_path / f"{name}.run.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# inputs: the design fasta is named and hashed
# ---------------------------------------------------------------------------

def test_manifest_names_the_design_fasta(tmp_path, mutation_lines, restore_state):
    _designed(mutation_lines)
    manifest = _export_excel_manifest(tmp_path)

    assert "design_fasta" in manifest["inputs"], (
        f"inputs did not name the design fasta: {manifest['inputs']}"
    )
    entry = manifest["inputs"]["design_fasta"]
    assert entry["path"] == str(GENBANK.resolve())
    assert SHA256_HEX.match(entry["sha256"]), entry["sha256"]
    assert entry["sha256"] == compute_input_sha256(GENBANK)
    assert entry["size_bytes"] == GENBANK.stat().st_size


def test_export_order_and_mapping_name_the_fasta_too(
    tmp_path, mutation_lines, restore_state
):
    """All three kuro export handlers, not just the Excel one."""
    _designed(mutation_lines)

    handle_export_order({"filepath": str(tmp_path / "order.csv"), "format": "idt"})
    order = json.loads((tmp_path / "order.run.json").read_text(encoding="utf-8"))

    handle_export_mapping({"filepath": str(tmp_path / "map.csv"), "format": "echo"})
    mapping = json.loads((tmp_path / "map.run.json").read_text(encoding="utf-8"))

    for name, manifest in (("export_order", order), ("export_mapping", mapping)):
        assert "design_fasta" in manifest["inputs"], name
        assert manifest["inputs"]["design_fasta"]["sha256"] == compute_input_sha256(
            GENBANK
        ), name


def test_design_time_digest_matches_export_time_digest(
    tmp_path, mutation_lines, restore_state
):
    """The two digests exist so an edited fasta shows up as a disagreement.

    The design hashes the file when it reads it and the export hashes it again
    when it writes the manifest. On an untouched file they agree; that is what
    makes a mismatch mean something.
    """
    _designed(mutation_lines)
    manifest = _export_excel_manifest(tmp_path)

    assert (
        manifest["extra"]["design"]["fasta_sha256"]
        == manifest["inputs"]["design_fasta"]["sha256"]
    )


def test_typed_mutations_are_recorded_inline_not_as_a_dead_path(
    tmp_path, mutation_lines, restore_state
):
    """Text input goes through a temp CSV this handler deletes on the way out.

    Naming that path would leave a manifest entry pointing at a file that no
    longer exists, which build_run_manifest drops silently, which then reads
    exactly like "no mutations were supplied".
    """
    _designed(mutation_lines)
    manifest = _export_excel_manifest(tmp_path)

    assert "design_mutations" not in manifest["inputs"]
    mutations = manifest["extra"]["design"]["mutations"]
    assert mutations["source"] == "text"
    assert mutations["count"] == len(mutation_lines)
    assert mutations["lines"] == mutation_lines
    assert SHA256_HEX.match(mutations["sha256"]), mutations["sha256"]


def test_mutation_csv_file_is_named_and_hashed(
    tmp_path, mutation_lines, restore_state
):
    """A mutations file on disk does get an inputs entry, unlike typed text."""
    mutations_csv = tmp_path / "muts.csv"
    with mutations_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["mutation"])
        for line in mutation_lines:
            writer.writerow([line])

    _designed(mutation_lines, mutations_csv_or_text=str(mutations_csv))
    manifest = _export_excel_manifest(tmp_path)

    entry = manifest["inputs"]["design_mutations"]
    assert entry["path"] == str(mutations_csv.resolve())
    assert entry["sha256"] == compute_input_sha256(mutations_csv)
    assert manifest["extra"]["design"]["mutations"]["source"] == "file"


# ---------------------------------------------------------------------------
# extra.design: the parameters the run actually used
# ---------------------------------------------------------------------------

def test_manifest_records_resolved_design_parameters(
    tmp_path, mutation_lines, restore_state
):
    _designed(mutation_lines, tol_max=5.5, gc_min=35.0, gc_max=65.0)
    manifest = _export_excel_manifest(tmp_path)

    params = manifest["extra"]["design"]["params"]
    assert params["tol_max"] == 5.5
    assert params["gc_min"] == 35.0
    assert params["gc_max"] == 65.0
    assert params["polymerase"] == "KOD"
    assert params["target_start"] == TARGET_START
    # Defaults are filled in by pydantic, so a parameter the caller never sent
    # is still on the record with the value the run used.
    assert params["codon_strategy"] == "closest"
    assert params["overlap_mode"] == "partial"
    # The mutation blob is not duplicated here; it is under extra.design.mutations.
    assert "mutations_csv_or_text" not in params


def test_seed_stays_null(tmp_path, mutation_lines, restore_state):
    """Nothing in this path draws from an RNG any more, so null is the truth.

    ca_max_dist used to sample without a seed. It is exact now, so there is no
    seed to record and a filled-in value would claim a determinism mechanism
    that does not exist.
    """
    _designed(mutation_lines)
    manifest = _export_excel_manifest(tmp_path)
    assert manifest["seed"] is None


def test_schema_version_did_not_move(tmp_path, mutation_lines, restore_state):
    """Everything new rides in `extra`; the contract version must not move.

    src/lib/runManifest.ts keeps its own copy and rejects any manifest whose
    version differs, so a bump would make the app refuse every file already
    written.
    """
    _designed(mutation_lines)
    manifest = _export_excel_manifest(tmp_path)
    assert manifest["schema_version"] == EXPECTED_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# extra.interventions: what happened after the design, in order
# ---------------------------------------------------------------------------

def test_retry_failed_lands_in_the_manifest_with_its_own_parameters(
    tmp_path, mutation_lines, restore_state
):
    """The retry parameters are the ones that explain an off-default primer."""
    mutation = _designed(mutation_lines)

    handle_retry_failed({
        "mutation": mutation,
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "polymerase": "KOD",
        "overlap_len": 18,
        "rev_len_max": 29,
        "tol_max": 6.0,
    })

    manifest = _export_excel_manifest(tmp_path)
    interventions = manifest["extra"]["interventions"]
    assert len(interventions) == 1

    entry = interventions[0]
    assert entry["type"] == "retry_failed"
    assert entry["seq"] == 1
    assert entry["mutation"] == mutation
    assert entry["fasta_path"] == str(GENBANK.resolve())
    assert entry["params"]["rev_len_max"] == 29
    assert entry["params"]["tol_max"] == 6.0
    assert entry["candidates_returned"] >= 1
    assert entry["at"].endswith("+00:00")


def test_interventions_keep_call_order(tmp_path, mutation_lines, restore_state):
    """Order is the point: a later swap overwrites what an earlier retry chose."""
    mutation = _designed(mutation_lines)

    retried = handle_retry_failed({
        "mutation": mutation,
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "polymerase": "KOD",
        "overlap_len": 18,
        "num_return": 3,
    })
    # The engine returns what it can find, which is not always num_return.
    last_idx = retried["count"] - 1
    commit_idx = min(1, last_idx)

    handle_commit_design_result({"mutation": mutation, "candidate_idx": commit_idx})
    handle_swap_primer({
        "mutation": mutation, "candidate_idx": last_idx, "swap_type": "rev",
    })

    manifest = _export_excel_manifest(tmp_path)
    interventions = manifest["extra"]["interventions"]

    assert [e["type"] for e in interventions] == [
        "retry_failed", "commit_design_result", "swap_primer",
    ]
    assert [e["seq"] for e in interventions] == [1, 2, 3]
    assert interventions[1]["candidate_idx"] == commit_idx
    assert interventions[2]["candidate_idx"] == last_idx
    assert interventions[2]["swap_type"] == "rev"
    # A rev swap rewrites every mutation at the same position, so the record has
    # to name the position and not only the mutation the operator clicked.
    assert interventions[2]["propagated_to_position"] is not None


def test_a_new_design_clears_the_previous_intervention_log(
    tmp_path, mutation_lines, restore_state
):
    mutation = _designed(mutation_lines)
    handle_swap_primer({
        "mutation": mutation, "candidate_idx": 0, "swap_type": "both",
    })

    _designed(mutation_lines)

    manifest = _export_excel_manifest(tmp_path, name="redesigned")
    assert manifest["extra"]["interventions"] == []


# ---------------------------------------------------------------------------
# The caller-supplied path must not borrow this session's provenance
# ---------------------------------------------------------------------------

def test_caller_supplied_rows_do_not_inherit_session_provenance(
    tmp_path, mutation_lines, restore_state
):
    """A live design in state must not stamp itself onto someone else's rows.

    handle_load_workspace restores a workspace without repopulating
    _state.results, so after a load the frontend exports rows the last design in
    this process did not produce. Naming that design's fasta there would put a
    confident falsehood in the one artifact whose job is to be trusted.
    """
    _designed(mutation_lines)

    handle_export_order({
        "filepath": str(tmp_path / "handed_in.csv"),
        "format": "idt",
        "results": [{
            "mutation": "M1T",
            "forward_seq": "ACGTACGTACGT",
            "reverse_seq": "TTTTACGTACGT",
        }],
    })
    manifest = json.loads(
        (tmp_path / "handed_in.run.json").read_text(encoding="utf-8")
    )

    assert manifest["inputs"] == {}
    assert manifest["extra"]["results_source"] == "payload"
    assert manifest["extra"]["design"] is None
    assert manifest["extra"]["interventions"] is None
    assert "provenance_omitted" in manifest["extra"]


def test_excel_export_records_where_the_plate_layout_came_from(
    tmp_path, mutation_lines, restore_state
):
    """Excel rows always come from state; only the well layout can be handed in."""
    _designed(mutation_lines)
    manifest = _export_excel_manifest(tmp_path, name="from_state")

    assert manifest["extra"]["results_source"] == "state"
    assert manifest["extra"]["mappings_source"] == "state"

    handle_export_excel({
        "filepath": str(tmp_path / "given_layout.xlsx"),
        "mappings": [{
            "well": "A1",
            "primer_name": "M1_F",
            "sequence": "ACGTACGTACGT",
            "primer_type": "forward",
            "mutation": "M1",
        }],
        "dedup_info": {},
    })
    handed = json.loads(
        (tmp_path / "given_layout.run.json").read_text(encoding="utf-8")
    )
    assert handed["extra"]["results_source"] == "state"
    assert handed["extra"]["mappings_source"] == "payload"
