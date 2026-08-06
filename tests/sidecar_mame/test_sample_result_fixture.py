"""The committed MAME sample fixture against the serializer that shipped it.

``src-tauri/samples/mame/sample_analysis_result.json`` is what the app loads
when a user picks "sample data", and it is written by
``python-core/scripts/generate_mame_sample_result.py``. That script used to
carry its own copy of ``_serialize_verdict``, and the copy went stale silently:
v0.16.1 added ``median_minor_allele_fraction`` and
``consensus_n_fraction_evaluable`` to the real serializer and the fixture kept
shipping 22 keys per verdict, because nothing compared the two. Both fields are
optional on the TypeScript side, so the app rendered an "unknown" branch instead
of failing.

The script now imports the serializers rather than copying them, which is what
the first test pins. The rest compare the committed JSON against what those
serializers emit, by key set rather than by value: values legitimately depend on
the synthetic inputs and on the machine that ran the generator, key sets do not.

The ``runHealth`` block had the same defect for the same reason: the generator
mirrored ``sidecar_mame.handlers.health.handle_get_run_health`` by hand and the
mirror lost ``cross_talk_status`` (added in v0.13.23.0). An absent status reads
as ``ok`` in the panel, so the sample plate claimed "no cross-talk candidates
detected" for a check that never ran. The generator calls the handler now, and
the tests below pin both the call and the resulting key set.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from sidecar_mame.core import reset_state, set_last_analyze
from sidecar_mame.handlers.analyze import (
    _deserialize_replicate,
    _deserialize_verdict,
    _serialize_replicate,
    _serialize_verdict,
    _summarize,
)
from sidecar_mame.handlers.health import handle_get_run_health

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _REPO_ROOT / "src-tauri" / "samples" / "mame" / "sample_analysis_result.json"
_GENERATOR = (
    _REPO_ROOT / "python-core" / "scripts" / "generate_mame_sample_result.py"
)


def _import_generator() -> ModuleType:
    """Import the generator script without installing it as a package.

    Importing is side-effect free: the module only extends ``sys.path`` at
    import time and guards the pipeline run behind ``__main__``.
    """
    spec = importlib.util.spec_from_file_location(
        "generate_mame_sample_result", _GENERATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load a ModuleSpec for {_GENERATOR}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def fixture_json() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_generator_reuses_the_handler_serializers() -> None:
    """No second copy of the serializers, by identity rather than by content.

    A content comparison passes the moment someone copies the current version
    back in, which is how this drifted the first time.
    """
    mod = _import_generator()
    assert mod._serialize_verdict is _serialize_verdict
    assert mod._serialize_replicate is _serialize_replicate
    assert mod._summarize is _summarize


def test_generator_reuses_the_run_health_handler() -> None:
    """``runHealth`` comes from the handler too, not from a mirror of its dict.

    The mirror is how ``cross_talk_status`` went missing: it was added to the
    handler and never copied across, and the fixture kept shipping a status-less
    run health that the panel reads as a clean plate.
    """
    mod = _import_generator()
    assert mod.handle_get_run_health is handle_get_run_health


def test_fixture_verdicts_carry_every_serialized_field(fixture_json: dict) -> None:
    """Every verdict in the committed JSON has the key set analyze emits.

    Round-tripping through the deserializer is what makes this a comparison
    against the CURRENT serializer without needing a synthetic record: a key
    the fixture lacks comes back as its dataclass default and is re-emitted,
    so the two sets differ exactly when the fixture is stale.
    """
    verdicts = fixture_json["verdicts"]
    assert verdicts, "fixture carries no verdicts"
    for entry in verdicts:
        expected = set(_serialize_verdict(_deserialize_verdict(entry)))
        assert set(entry) == expected, (
            f"{sorted(expected - set(entry))} missing from fixture verdict "
            f"{entry.get('custom_barcode')!r}; regenerate with "
            "python-core/scripts/generate_mame_sample_result.py"
        )


def test_fixture_replicates_carry_every_serialized_field(fixture_json: dict) -> None:
    """Same for replicates, including the verdicts nested under plate_verdicts."""
    replicates = fixture_json["replicates"]
    assert replicates, "fixture carries no replicates"
    for entry in replicates:
        expected = set(_serialize_replicate(_deserialize_replicate(entry)))
        assert set(entry) == expected, (
            f"{sorted(expected - set(entry))} missing from fixture replicate "
            f"{entry.get('mutant_id')!r}; regenerate with "
            "python-core/scripts/generate_mame_sample_result.py"
        )
        for plate, nested in entry["plate_verdicts"].items():
            nested_expected = set(_serialize_verdict(_deserialize_verdict(nested)))
            assert set(nested) == nested_expected, (
                f"{sorted(nested_expected - set(nested))} missing from "
                f"plate_verdicts[{plate!r}] of replicate "
                f"{entry.get('mutant_id')!r}"
            )


def test_fixture_summary_matches_the_summarizer(fixture_json: dict) -> None:
    """``_summarize`` over an empty run states the key set, independent of counts."""
    assert set(fixture_json["summary"]) == set(_summarize([]))


def test_fixture_top_level_shape_is_what_the_loader_reads(fixture_json: dict) -> None:
    """The keys the app reaches for.

    ``runHealth`` is the one the sample loader actually consumes
    (``src/store/mame/slices/analysisSlice.ts``); the rest are asserted so a
    generator change that drops a section is caught here rather than as an
    empty panel.
    """
    assert set(fixture_json) == {
        "schema",
        "verdicts",
        "replicates",
        "summary",
        "wells",
        "runHealth",
    }
    assert isinstance(fixture_json["runHealth"], dict)
    assert fixture_json["runHealth"]["per_plate_summary"]


def test_fixture_run_health_carries_every_handler_field(fixture_json: dict) -> None:
    """``runHealth`` has the key set ``handle_get_run_health`` returns.

    Driven off an empty analyze state rather than a synthetic run: the handler
    assembles the same dict literal either way, so the key set is exact while
    the values stay irrelevant. This is the assertion that would have caught
    the missing ``cross_talk_status``.
    """
    try:
        set_last_analyze([], [], "", run_meta=None)
        expected = set(handle_get_run_health({}))
    finally:
        reset_state()
    missing = sorted(expected - set(fixture_json["runHealth"]))
    assert set(fixture_json["runHealth"]) == expected, (
        f"{missing} missing from fixture runHealth; regenerate with "
        "python-core/scripts/generate_mame_sample_result.py"
    )


def test_fixture_run_health_states_the_cross_talk_check_never_ran(
    fixture_json: dict,
) -> None:
    """The status has to say ``not_run``, and that is not a formality.

    The fixture is generated from consensus FASTA files, never from a raw
    MinKNOW run, so ``barcode_distribution`` is ``None`` and the cross-talk
    check has nothing to run over. The panel reads a missing status as ``ok``
    and then, seeing an empty candidate list, states that no cross-talk
    candidates were detected. For this fixture that sentence is false.
    """
    run_health = fixture_json["runHealth"]
    assert run_health["barcode_distribution"] is None
    assert run_health["cross_talk_candidates"] == []
    assert run_health["cross_talk_status"] == "not_run"
