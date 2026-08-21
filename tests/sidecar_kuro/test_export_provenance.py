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
    _design_provenance_for_manifest,
    handle_export_all,
    handle_export_excel,
    handle_export_macrogen,
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


# ---------------------------------------------------------------------------
# The batch folder, which is the path primers are actually ordered from.
#
# It was the one export path with no manifest at all: `_export_run_json` wrote
# a plate dump carrying `exported_at`, `mappings`, `dedup_info` and
# `result_count`, so a folder of order files named no kuma version, no input
# digest and no design parameters. The manifest is merged into that same
# `{prefix}_run.json` instead of being added beside it, because
# `src/components/layout/export-handlers.ts` maps the `_run.json` suffix to the
# `kuro_run_json` artifact type, so a rename or a new sibling would drag the
# frontend into a Python fix.
# ---------------------------------------------------------------------------

#: The keys `isRunManifest` in src/lib/runManifest.ts requires, with the types it
#: checks, restated here on purpose. The batch run.json now has to satisfy a
#: guard written in TypeScript, and no Python test would otherwise notice a
#: change on this side that stops satisfying it.
FRONTEND_GUARD_KEYS: dict[str, type | tuple[type, ...]] = {
    "schema_version": str,
    "method": str,
    "kuma_version": str,
    "python_version": str,
    "platform": str,
    "started_at": str,
    "finished_at": str,
    "duration_seconds": (int, float),
    "inputs": dict,
    "params": dict,
}

#: What the batch run.json held before it also became a manifest. Anything
#: written against the old file reads exactly these.
LEGACY_RUN_JSON_KEYS = {"exported_at", "mappings", "dedup_info", "result_count"}

LEGACY_MAPPING_KEYS = {
    "well", "primer_name", "sequence", "primer_type", "mutation",
}


def _export_all(tmp_path: Path, name: str = "Batch", **overrides) -> dict:
    """Run the batch export, return the parsed ``{prefix}_run.json``."""
    params = {
        "output_dir": str(tmp_path),
        "project_name": name,
        "fwd_plate_name": "Pfwd",
        "rev_plate_name": "Prev",
    }
    params.update(overrides)
    result = handle_export_all(params)
    target = Path(result["output_dir"])
    run_json = target / f"{target.name}_run.json"
    assert run_json.exists(), f"batch export wrote no run json: {result}"
    return json.loads(run_json.read_text(encoding="utf-8"))


def test_batch_export_writes_a_real_manifest(tmp_path, mutation_lines, restore_state):
    _designed(mutation_lines)
    manifest = _export_all(tmp_path)

    assert manifest["method"] == "export_all"
    assert manifest["schema_version"] == EXPECTED_SCHEMA_VERSION
    assert manifest["kuro_module_version"]
    for key, expected_type in FRONTEND_GUARD_KEYS.items():
        assert key in manifest, f"isRunManifest requires {key}"
        assert isinstance(manifest[key], expected_type), key
    assert manifest["seed"] is None or isinstance(manifest["seed"], (int, float))


def test_batch_manifest_names_the_design_fasta(tmp_path, mutation_lines, restore_state):
    """An order placed from this folder can be traced back to exact bytes."""
    _designed(mutation_lines)
    manifest = _export_all(tmp_path)

    entry = manifest["inputs"]["design_fasta"]
    assert entry["path"] == str(GENBANK.resolve())
    assert SHA256_HEX.match(entry["sha256"]), entry["sha256"]
    assert entry["sha256"] == compute_input_sha256(GENBANK)
    assert entry["size_bytes"] == GENBANK.stat().st_size


def test_batch_manifest_carries_the_design_parameters(
    tmp_path, mutation_lines, restore_state
):
    _designed(mutation_lines, tol_max=5.5, gc_min=35.0, gc_max=65.0)
    manifest = _export_all(tmp_path)

    params = manifest["extra"]["design"]["params"]
    assert params["tol_max"] == 5.5
    assert params["gc_min"] == 35.0
    assert params["gc_max"] == 65.0
    assert params["polymerase"] == "KOD"
    assert params["target_start"] == TARGET_START


def test_batch_manifest_carries_the_intervention_log(
    tmp_path, mutation_lines, restore_state
):
    """An off-default primer in an ordered plate has to be explainable."""
    mutation = _designed(mutation_lines)
    handle_retry_failed({
        "mutation": mutation,
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "polymerase": "KOD",
        "overlap_len": 18,
        "rev_len_max": 29,
    })

    manifest = _export_all(tmp_path)
    interventions = manifest["extra"]["interventions"]

    assert [e["type"] for e in interventions] == ["retry_failed"]
    assert interventions[0]["mutation"] == mutation
    assert interventions[0]["params"]["rev_len_max"] == 29


def test_batch_run_json_keeps_every_key_it_had_before(
    tmp_path, mutation_lines, restore_state
):
    """Merging the manifest in must not break a reader of the old file.

    This is the constraint that picked the shape. Writing the manifest to a
    second file would have needed a new suffix, and export-handlers.ts maps
    suffixes to artifact types, so the plate dump and the manifest share one
    file and the plate-dump keys keep their names and their shapes.
    """
    _designed(mutation_lines)
    manifest = _export_all(tmp_path)

    missing = LEGACY_RUN_JSON_KEYS - set(manifest)
    assert not missing, f"lost a pre-manifest key: {missing}"
    assert manifest["exported_at"]
    assert manifest["mappings"], "the plate map itself must still be in the file"
    for row in manifest["mappings"]:
        assert set(row) == LEGACY_MAPPING_KEYS, row
    assert isinstance(manifest["dedup_info"], dict)
    assert isinstance(manifest["result_count"], int)
    assert manifest["result_count"] > 0
    # If these two key sets ever overlap, one half of the file silently
    # overwrites the other.
    assert LEGACY_RUN_JSON_KEYS.isdisjoint(FRONTEND_GUARD_KEYS)


def test_batch_manifest_records_where_the_plate_layout_came_from(
    tmp_path, mutation_lines, restore_state
):
    """Same convention as the Excel export, and for the same reason.

    The design results come from `_state.results` on both branches (a payload
    only filters them), so they are what `results_source` describes, and the
    well layout is reported separately. Keying `results_source` off `mappings`
    the way handle_export_mapping does would read as honest and behave the
    opposite way: export-handlers.ts always sends `mappings` for export_all, so
    every batch export an operator ever runs would come out stamped
    `provenance_omitted` and carry no design at all.
    """
    _designed(mutation_lines)

    from_state = _export_all(tmp_path, name="FromState")
    assert from_state["extra"]["results_source"] == "state"
    assert from_state["extra"]["mappings_source"] == "state"
    assert "provenance_omitted" not in from_state["extra"]

    handed = _export_all(
        tmp_path,
        name="HandedIn",
        mappings=[{
            "well": "A1",
            "primer_name": "M1_F",
            "sequence": "ACGTACGTACGT",
            "primer_type": "forward",
            "mutation": "M1",
        }],
        dedup_info={},
    )
    assert handed["extra"]["mappings_source"] == "payload"
    assert handed["extra"]["results_source"] == "state"
    assert handed["inputs"]["design_fasta"]["sha256"] == compute_input_sha256(GENBANK)


def test_batch_manifest_records_nothing_when_state_holds_no_design(
    tmp_path, mutation_lines, restore_state
):
    """The post-load-workspace case: absent provenance, not borrowed provenance.

    handle_load_workspace does not repopulate `_state.results`, so a workspace
    loaded into a fresh process exports rows no design in this process produced.
    `results_source` still reads "state" because that is where the handler looks,
    and what state has to say is nothing: a null design and an empty inputs read
    as "not recorded", and the legacy `result_count` of 0 says the same thing
    again. The failure mode worth pinning is the opposite one, a filled-in fasta
    digest belonging to some earlier design.
    """
    _designed(mutation_lines)
    with _state_lock:
        _state.results = []
        _state.design_provenance = None
        _state.interventions = []

    manifest = _export_all(
        tmp_path,
        name="AfterLoad",
        mappings=[{
            "well": "A1",
            "primer_name": "M1_F",
            "sequence": "ACGTACGTACGT",
            "primer_type": "forward",
            "mutation": "M1",
        }],
        dedup_info={},
    )

    assert manifest["inputs"] == {}
    assert manifest["extra"]["design"] is None
    assert manifest["extra"]["interventions"] == []
    assert manifest["extra"]["mappings_source"] == "payload"
    assert manifest["result_count"] == 0


def test_the_payload_omission_convention_still_holds(
    tmp_path, mutation_lines, restore_state
):
    """export_all opting out must not have loosened the shared helper.

    handle_export_order and handle_export_mapping still declare a
    caller-supplied source, and the omission still has to be spelled out
    instead of showing up as an inputs dict that merely happens to be empty.
    """
    _designed(mutation_lines)
    inputs, extra = _design_provenance_for_manifest("payload")

    assert inputs == {}
    assert extra["results_source"] == "payload"
    assert extra["design"] is None
    assert extra["interventions"] is None
    assert "provenance_omitted" in extra


def test_macrogen_export_writes_a_sibling_manifest(
    tmp_path, mutation_lines, restore_state
):
    """One file at a path the operator picked, so it gets `.run.json`.

    The batch pipeline cannot share that convention: handle_export_all already
    names a single `{prefix}_run.json` for the whole folder.
    """
    _designed(mutation_lines)
    handle_export_macrogen({
        "output_path": str(tmp_path / "plate.xls"),
        "fwd_plate_name": "Pfwd",
        "rev_plate_name": "Prev",
    })

    manifest = json.loads(
        (tmp_path / "plate.run.json").read_text(encoding="utf-8")
    )
    assert manifest["method"] == "export_macrogen"
    assert manifest["schema_version"] == EXPECTED_SCHEMA_VERSION
    assert manifest["inputs"]["design_fasta"]["sha256"] == compute_input_sha256(
        GENBANK
    )
    assert manifest["extra"]["results_source"] == "state"
    assert manifest["extra"]["design"]["params"]["polymerase"] == "KOD"
    assert manifest["params"]["fwd_plate_name"] == "Pfwd"


def test_macrogen_result_shape_is_untouched(tmp_path, mutation_lines, restore_state):
    """src/types/models.ts types this result as exactly {ok, path}.

    The manifest lands on disk, not in the response, because this change stops
    at the Python layer.
    """
    _designed(mutation_lines)
    result = handle_export_macrogen({
        "output_path": str(tmp_path / "shape.xls"),
        "fwd_plate_name": "Pfwd",
        "rev_plate_name": "Prev",
    })

    assert set(result) == {"ok", "path"}
    assert result["ok"] is True
