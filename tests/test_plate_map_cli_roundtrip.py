"""The plate-map CLI reads the design TSV the CLI itself writes.

``export_results_tsv`` puts a ``# overlap_mode=...`` line above the header and
renames the third Tm column in full-overlap mode. ``kuro plate-map`` fed that
file straight into ``csv.DictReader``, so the metadata line became the header
and the first row lookup raised ``KeyError: 'Mutation'``.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

import pytest

from kuma_core.kuro.cli import cmd_plate_map
from kuma_core.kuro.mutation import Mutation
from kuma_core.kuro.overlap import OverlapWindow
from kuma_core.kuro.sdm_engine import (
    OverlapMode,
    SdmPrimerResult,
    export_results_tsv,
)


def _result(raw: str, fwd: str, rev: str) -> SdmPrimerResult:
    mutation = Mutation(
        raw=raw, wt_aa=raw[0], position=int(raw[1:-1]), mt_aa=raw[-1],
        codon_start=30, wt_codon="GCT", mt_codon="GTT",
    )
    return SdmPrimerResult(
        mutation=mutation,
        forward_seq=fwd,
        reverse_seq=rev,
        forward_binding=fwd[-12:],
        reverse_binding=rev[-12:],
        overlap_window=OverlapWindow(sequence=fwd[:18], start=12, end=30, codon_offset=18),
        tm_fwd=62.1,
        tm_rev=58.4,
        tm_overlap=42.3,
        tm_condition_met=True,
        tolerance_used=1.0,
    )


_RESULTS = [
    _result("A10V", "ACGTACGTACGTACGTACGTTACGTACGTA", "TGCATGCATGCATGCATGCATG"),
    _result("A20V", "GGCTACGTACGTACGTACGTTACGTACGTA", "TTCATGCATGCATGCATGCATG"),
]


@pytest.mark.parametrize("mode", ["partial", "full"])
def test_plate_map_reads_exported_design_tsv(tmp_path: Path, mode: str) -> None:
    tsv = tmp_path / "design.tsv"
    export_results_tsv(_RESULTS, tsv, overlap_mode=cast(OverlapMode, mode))
    assert tsv.read_text(encoding="utf-8").splitlines()[0].startswith("# overlap_mode=")

    out = tmp_path / "plate_mapping.xlsx"
    cmd_plate_map(argparse.Namespace(primers=str(tsv), output=str(out)))
    assert out.exists()


def test_plate_map_recovers_full_mode_temperatures(tmp_path: Path) -> None:
    """Full mode writes Tm_Primer, so the reader must not read 0.0 instead."""
    from kuma_core.kuro.cli import read_design_tsv

    tsv = tmp_path / "design.tsv"
    export_results_tsv(_RESULTS, tsv, overlap_mode="full")
    mode, results = read_design_tsv(tsv)
    assert mode == "full"
    assert [r.overlap_mode for r in results] == ["full", "full"]
    # The exporter writes tm_overlap under the Tm_Primer name, so the value has
    # to survive the round trip instead of falling back to 0.0.
    assert [r.tm_overlap for r in results] == [42.3, 42.3]
    assert [r.mutation.raw for r in results] == ["A10V", "A20V"]
