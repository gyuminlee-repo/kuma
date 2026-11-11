"""The notice reads the payload the sidecar sends, field for field.

The crosscheck is reportable rather than blocking, so the notice is the whole
of it: no exception, no refused run, no verdict changes if it never renders.
Rename a wire key or the gated status value on one side only and
``ClonePlateCrosscheckNotice`` reads ``undefined``, returns ``null`` and takes
the finding off the screen in silence.

Two defences already exist and neither closes that case.
``src/types/mame/models.ts`` declares ``status: string``, so ``tsc`` accepts any
literal, and the component's own vitest file carries its own fixture, so a
rename applied to the component, the interface and the fixture together is
self-consistent and passes. ``.cross-layer-sync.json`` ``symbols`` cannot help
either: ``scripts/sync-check.mjs`` concatenates every file a group names and
asks only whether the token appears somewhere in the group, so the Python side
keeps the token alive for the TypeScript side (measured 2026-11-11: with
``mismatch`` declared as a symbol and the component's literal renamed, the group
still reported ``PASS``).

So this compares the two sides directly. The payload is the one
``_clone_plate_crosscheck`` builds from a real workbook rather than a literal
copied here, because a copy drifts the same way the component does.
"""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.layout import DEFAULT_WT_PLACEMENT
from sidecar_mame.handlers.analyze import _clone_plate_crosscheck

REPO = Path(__file__).resolve().parents[1]
NOTICE = REPO / "src/components/mame/widgets/ClonePlateCrosscheckNotice.tsx"

#: Every ``finding.<key>`` the component reads off the stored payload.
_FINDING_FIELD = re.compile(r"\bfinding\.([A-Za-z_][A-Za-z0-9_]*)")
#: Every ``example.<key>`` it reads off one entry of ``examples``.
_EXAMPLE_FIELD = re.compile(r"\bexample\.([A-Za-z_][A-Za-z0-9_]*)")
#: The status the notice renders for, as the component spells it.
_GATED_STATUS = re.compile(r"finding\.status\s*!==\s*\"([^\"]+)\"")

_STRICT_HEADER = [
    "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon",
    "mt_codon", "group_id", "primer_set_ref", "notation_type", "status",
]


def _design_ordered_export(path: Path) -> Path:
    """A KURO export written in design order, which is what disagrees.

    The primer plate gets well *i* for sheet row *i*
    (``kuro.plate_mapper._assign_well``) and the run orders the clone plate by
    residue position, so A1 and B1 swap and the payload comes back a mismatch.
    """
    workbook = openpyxl.Workbook()
    plate = workbook.worksheets[0]
    plate.title = "Fwd List"
    plate.append(["Well", "Primer Name", "Mutation"])
    for well, mutation in [("A1", "S22T"), ("B1", "S11I"), ("C1", "N28S")]:
        plate.append([well, f"{mutation}_F", mutation])
    sheet = workbook.create_sheet("expected_mutations")
    sheet.append(_STRICT_HEADER)
    for mutation in ["S22T", "S11I", "N28S"]:
        sheet.append([
            mutation, int(mutation[1:-1]), mutation[0], mutation[-1],
            "GTG", "TTT", "", "", "single", "DESIGNED",
        ])
    workbook.save(str(path))
    return path


@pytest.fixture
def payload(tmp_path: Path) -> dict:
    """The dict ``validate_inputs`` puts on ``clone_plate_crosscheck``."""
    sent = _clone_plate_crosscheck(
        _design_ordered_export(tmp_path / "design_order.xlsx"),
        None,
        None,
        DEFAULT_WT_PLACEMENT,
    )
    assert sent is not None, "the design-ordered fixture must produce a finding"
    return sent


@pytest.fixture
def source() -> str:
    return NOTICE.read_text(encoding="utf-8")


def test_the_extraction_reads_the_component_rather_than_a_constant(source: str) -> None:
    """A rename in the source must move what these patterns return.

    A matcher is wrong until measured, so it is run here against the one input
    whose answer is known: the component with its own names replaced. Patterns
    that passed this file by accident would report the shipped names on the
    renamed copy too.
    """
    renamed = (
        source.replace("finding.mismatch_count", "finding.n_mismatched")
        .replace('finding.status !== "mismatch"', 'finding.status !== "plates_differ"')
        .replace("example.primer_plate", "example.source_plate")
    )

    assert "n_mismatched" in set(_FINDING_FIELD.findall(renamed))
    assert "mismatch_count" not in set(_FINDING_FIELD.findall(renamed))
    assert "source_plate" in set(_EXAMPLE_FIELD.findall(renamed))
    assert _GATED_STATUS.findall(renamed) == ["plates_differ"]


def test_every_field_the_notice_reads_is_on_the_payload(
    source: str, payload: dict
) -> None:
    read = set(_FINDING_FIELD.findall(source))
    assert read, "the component must read the finding, or this check is vacuous"
    missing = sorted(read - set(payload))
    assert not missing, (
        f"{NOTICE.name} reads {missing} off the finding and "
        "_clone_plate_crosscheck sends no such key: the notice would read "
        "undefined and disappear in silence"
    )


def test_every_example_field_the_notice_reads_is_on_the_payload(
    source: str, payload: dict
) -> None:
    examples = payload["examples"]
    assert examples, "the design-ordered fixture must report example wells"
    read = set(_EXAMPLE_FIELD.findall(source))
    assert read, "the component must read an example, or this check is vacuous"
    missing = sorted(read - set(examples[0]))
    assert not missing, (
        f"{NOTICE.name} reads {missing} off one example and "
        "_clone_plate_crosscheck sends no such key"
    )


def test_the_status_the_notice_renders_for_is_the_status_sent(
    source: str, payload: dict
) -> None:
    gated = _GATED_STATUS.findall(source)
    assert len(gated) == 1, (
        f"expected exactly one status gate in {NOTICE.name}, found {gated}"
    )
    assert gated[0] == payload["status"], (
        f"{NOTICE.name} renders only for status {gated[0]!r} and the sidecar "
        f"sends {payload['status']!r}, so the notice never appears"
    )
