"""Static ownership check: GC sample-name judgement lives in gc_sample alone.

Sharing ``WT_PATTERN`` as a "single source of truth" constant did not stop the
drift: each reader applied the pattern itself, and the readers ended up
treating the same ``BLANK`` five different ways. The drift was in the code
that applied the patterns, so this test watches the application.

In the GC chain modules below, every load of a judgement symbol must appear in
``ALLOWED`` with a reason. A new reader that tests a name directly instead of
asking ``gc_sample.classify_sample`` fails here. A stale allowance fails too,
so the list cannot quietly grow past what the code does. Same AST-registry
approach as ``tests/shared/test_audit_io_boundaries.py``.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "kuma_core" / "mame" / "activity"

# The modules a GC report row passes through. gc_sample.py itself is the owner
# and is not scanned.
GC_CHAIN = (
    "evolvepro_xlsx.py",
    "build_evolvepro_input.py",
    "detect_measurement_source.py",
    "numeric_id_decode.py",
    "plate_layout_xlsx.py",
)

# Judgement symbols, and the WT pattern's former alias.
WATCHED = frozenset({
    "WT_PATTERN",
    "_WT_RE",
    "_WELL_RE",
    "WT_RELATIVE",
    "_BLOCK_REP_ID_RE",
    "_REP_BATCH_SAMPLE_RE",
    "_sample_name_is_calibration",
    "_short_variant",
    "_strip_confirmation_rep_suffix",
    # Used as a judgement when its ValueError is caught to mean "not a well".
    "_normalise_well",
})

ALLOWED: dict[tuple[str, str, str], str] = {
    # Layout and verdict labels, not GC rows: the variant notation of a mutant
    # the plate file or the verdict workbook declares.
    ("build_evolvepro_input.py", "_layout_maps", "_short_variant"): "layout mutant notation",
    ("build_evolvepro_input.py", "_verdict_maps", "_short_variant"): "verdict mutant_id notation",
    ("build_evolvepro_input.py", "_strict_ngs_gate", "_short_variant"): "verdict mutant_id notation",
    # Resequencing links name their wells explicitly; this spells them.
    ("build_evolvepro_input.py", "_judge_build", "_normalise_well"): "resequence link well spelling",
    ("build_evolvepro_input.py", "_read_sources", "_normalise_well"): "resequence link well spelling",
    ("numeric_id_decode.py", "expected_variant_order", "_normalise_well"): "design-list well spelling",
    # Selection rule (WT-exceeding variants). Two copies remain until the
    # selection layer is unified; both compare a mean, neither reads a name.
    ("build_evolvepro_input.py", "_above_wt_subset", "WT_RELATIVE"): "selection rule",
    ("numeric_id_decode.py", "above_wt_subset", "WT_RELATIVE"): "selection rule",
    ("numeric_id_decode.py", "decode_confirmation_against", "WT_RELATIVE"): "threshold quoted in a message",
    # The plate layout reader judges layout cells, not GC rows. Recorded as a
    # known second judgement site in the plan (layout WT cell, section 5).
    ("plate_layout_xlsx.py", "_normalise_well", "_WELL_RE"): "definition of the normaliser",
    ("plate_layout_xlsx.py", "parse_plate_layout_xlsx", "_WELL_RE"): "layout cell, not a GC row",
    ("plate_layout_xlsx.py", "parse_plate_layout_xlsx", "_normalise_well"): "layout cell, not a GC row",
    ("plate_layout_xlsx.py", "parse_plate_layout_xlsx", "WT_PATTERN"): "layout cell, not a GC row",
}


def _top_level_name(node: ast.stmt) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                return target.id
    return f"<module line {node.lineno}>"


def watched_uses(source: str, filename: str) -> set[tuple[str, str, str]]:
    """Every (file, top-level definition, symbol) where a watched symbol is loaded."""
    uses: set[tuple[str, str, str]] = set()
    for top in ast.parse(source).body:
        where = _top_level_name(top)
        for node in ast.walk(top):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                symbol = node.id
            elif isinstance(node, ast.Attribute):
                symbol = node.attr
            else:
                continue
            if symbol in WATCHED:
                uses.add((filename, where, symbol))
    return uses


def _all_uses() -> set[tuple[str, str, str]]:
    uses: set[tuple[str, str, str]] = set()
    for filename in GC_CHAIN:
        uses |= watched_uses((PACKAGE / filename).read_text(encoding="utf-8"), filename)
    return uses


def test_gc_chain_asks_gc_sample_instead_of_applying_the_patterns() -> None:
    unexpected = sorted(_all_uses() - ALLOWED.keys())
    assert not unexpected, (
        "GC sample-name judgement applied outside gc_sample. Ask "
        "gc_sample.classify_sample / is_wt_name, or, for a use that is not a "
        "GC-row judgement, add it to ALLOWED with the reason:\n"
        + "\n".join(f"  {file}:{where} uses {symbol}" for file, where, symbol in unexpected)
    )


def test_every_allowance_is_still_used() -> None:
    stale = sorted(ALLOWED.keys() - _all_uses())
    assert not stale, "ALLOWED entries no code needs any more:\n" + "\n".join(f"  {entry}" for entry in stale)


def test_the_scan_catches_a_planted_judgement() -> None:
    """Control: a reader testing a name with the well pattern is caught."""
    planted = (
        "def _gc_primary(rows):\n"
        "    return [r for r in rows if _WELL_RE.fullmatch(r)]\n"
        "def _other(r):\n"
        "    return activity.WT_PATTERN.match(r)\n"
    )
    assert watched_uses(planted, "build_evolvepro_input.py") == {
        ("build_evolvepro_input.py", "_gc_primary", "_WELL_RE"),
        ("build_evolvepro_input.py", "_other", "WT_PATTERN"),
    }
