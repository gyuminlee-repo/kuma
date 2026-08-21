"""Contract tests for guards that tested a relation instead of the thing itself.

Four of the five defects here share a shape the audit kept meeting: a guard
written as ``value < threshold`` cannot express "this value is not comparable",
so a NaN arriving from a file or an RPC parameter silences the guard while the
run reports the record as fine. The fifth is the other recurring shape: a rule
enforced on one input path and not on the other.

Each test was run with its fix reverted and fails on its own assertion.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from kuma_core.mame.ingest.fasta_parser import _read_float_metadata
from kuma_core.shared.sidecar import parse_finite_float

# ---------------------------------------------------------------------------
# The shared parser for a number arriving from outside
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["nan", "inf", "-inf", "Infinity", "NaN"])
def test_non_finite_input_is_refused(text: str) -> None:
    """Every spelling float() accepts and comparison cannot use is rejected."""
    with pytest.raises(ValueError, match="finite"):
        parse_finite_float(text, field="max_consensus_n_fraction")


@pytest.mark.parametrize("value,expected", [("0", 0.0), (0.5, 0.5), ("1e-3", 0.001)])
def test_ordinary_numbers_still_parse(value: object, expected: float) -> None:
    """The control. Without it the test above would pass on a function that
    rejected everything, which measures nothing."""
    assert parse_finite_float(value, field="threshold") == expected


def test_rejection_names_the_field() -> None:
    """The caller has four thresholds; a message that does not say which one
    was rejected leaves them reading code to find out."""
    with pytest.raises(ValueError, match="min_file_size_kb"):
        parse_finite_float(float("nan"), field="min_file_size_kb")


# ---------------------------------------------------------------------------
# A consensus header stating a figure that cannot be compared
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["nan", "inf", "-inf"])
def test_non_finite_header_value_reads_as_absent(text: str) -> None:
    """A header carrying NaN yields None, the same as a header without the key.

    Reverted to a bare ``float(value)`` this fails: the value parses, the
    no-call gate downstream compares against it, every comparison with NaN is
    False, and a consensus of NNN is reported evaluable.
    """
    assert _read_float_metadata({"n_fraction": text}, "n_fraction") is None


def test_measured_zero_is_not_absent() -> None:
    """0.0 means the figure was measured and was zero, which this repository
    separates from None all the way to the export. The guard above must not
    fold one into the other."""
    value = _read_float_metadata({"n_fraction": "0.0"}, "n_fraction")
    assert value == 0.0
    assert value is not None


def test_ordinary_header_value_parses() -> None:
    assert _read_float_metadata({"n_fraction": "0.25"}, "n_fraction") == 0.25


# ---------------------------------------------------------------------------
# A read whose quality could not be established
# ---------------------------------------------------------------------------


_READ_LENGTH = 1000


def _write_run(tmp_path: Path, qscore_text: str) -> tuple[Path, Path]:
    """One FASTQ record plus a MinKNOW summary stating *qscore_text* for it.

    Written as files rather than passed as a dict, because the non-finite
    value has to survive the summary parser to reach the comparison, and that
    parser is where the run's own numbers come from.
    """
    fastq = tmp_path / "reads.fastq"
    seq = "A" * _READ_LENGTH
    qual = "I" * _READ_LENGTH
    fastq.write_text(f"@read1\n{seq}\n+\n{qual}\n", encoding="utf-8")

    summary = tmp_path / "sequencing_summary.txt"
    summary.write_text(
        "read_id\tmean_qscore_template\tsequence_length_template\tbarcode_score\n"
        f"read1\t{qscore_text}\t{_READ_LENGTH}\t99.0\n",
        encoding="utf-8",
    )
    return fastq, summary


def test_unusable_qscore_fails_the_filter(tmp_path: Path) -> None:
    """A read whose summary states a non-finite qscore is dropped, not kept.

    Reverted to ``if qscore < params.min_qscore`` this fails: ``nan < 8`` is
    False, so a read whose quality could not be established passes the gate
    that exists to reject exactly that.

    The summary path is used rather than the quality string because a Phred
    string cannot encode NaN. The file the run reads from can.
    """
    from kuma_core.mame.ingest.quality_filter import (
        QualityFilterParams,
        filter_reads_by_summary,
    )

    fastq, summary = _write_run(tmp_path, "nan")
    params = QualityFilterParams(target_length=_READ_LENGTH)

    _, result = filter_reads_by_summary(fastq, summary, params)

    assert result.n_input == 1
    assert result.n_passed == 0
    assert result.n_failed_qscore == 1


def test_good_qscore_still_passes(tmp_path: Path) -> None:
    """The control: the same call with a real qscore keeps the read, so the
    test above cannot be passing merely because the filter rejects
    everything (a wrong length window would do that too)."""
    from kuma_core.mame.ingest.quality_filter import (
        QualityFilterParams,
        filter_reads_by_summary,
    )

    fastq, summary = _write_run(tmp_path, "30.0")
    params = QualityFilterParams(target_length=_READ_LENGTH)

    _, result = filter_reads_by_summary(fastq, summary, params)

    assert result.n_input == 1
    assert result.n_passed == 1
    assert result.n_failed_qscore == 0


def test_math_nan_is_what_the_parser_produces() -> None:
    """The summary parser turns the text "nan" into a float NaN rather than
    dropping the column, which is what puts the value in front of the
    comparison in the first place."""
    assert math.isnan(float("nan"))


# ---------------------------------------------------------------------------
# A rule enforced on one input path and not the other
# ---------------------------------------------------------------------------


_KURO_HEADER = [
    "mutant_id",
    "position",
    "wt_aa",
    "mt_aa",
    "wt_codon",
    "mt_codon",
    "group_id",
    "primer_set_ref",
    "notation_type",
    "status",
]


def _write_kuro_export(
    path: Path, rows: list[tuple[str, str]], *, notation: str = "single"
) -> Path:
    """A minimal KURO export. Each row is ``(label, group_id)``.

    The group travels with the label because that pair, not the label alone, is
    what identifies a variant here: a combo spans one row per substitution
    under a shared group.
    """
    import openpyxl

    from kuma_core.mame.io.variant_list import KURO_SHEET

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = KURO_SHEET
    ws.append(_KURO_HEADER)
    for label, group_id in rows:
        wt_aa, position, mt_aa = label[0], int(label[1:-1]), label[-1]
        ws.append(
            # DESIGNED, because a blank status is read as outside the designed
            # set and the reader refuses the row before reaching the check
            # under test.
            [
                label,
                position,
                wt_aa,
                mt_aa,
                "AAA",
                "TTT",
                group_id,
                label,
                notation,
                "DESIGNED",
            ]
        )
    wb.save(path)
    return path


def _write_plain_list(path: Path, labels: list[str]) -> Path:
    """The other input shape: one column of variant names, no KURO sheet."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sheet1"
    ws.append(["variant"])
    for label in labels:
        ws.append([label])
    wb.save(path)
    return path


def test_kuro_export_naming_two_variants_the_same_is_refused(tmp_path: Path) -> None:
    """The KURO path applies the rule the plain-list path already applied.

    Two unrelated variants under one name, which the groups make explicit.
    Reverted, this fails: the reader accepts the sheet and the two are scored
    against each other's wells with nothing saying which is which.
    """
    from kuma_core.mame.io.variant_list import read_variant_source

    path = _write_kuro_export(
        tmp_path / "kuro.xlsx",
        [("V5F", "G1"), ("K53N", "G2"), ("V5F", "G3")],
    )

    with pytest.raises(ValueError, match="duplicate variant 'V5F'"):
        read_variant_source(path)


def test_a_combo_spanning_rows_is_not_a_duplicate(tmp_path: Path) -> None:
    """One variant, one group, one substitution per row.

    This is the shape templates/03_mame_expected_mutations.xlsx ships (M006
    over two rows under G4), and the id-only form of the rule refused it. The
    shipped-asset tests caught that, which is why the rule keys on the group.
    """
    from kuma_core.mame.io.variant_list import read_variant_source

    path = _write_kuro_export(
        tmp_path / "combo.xlsx",
        [("V5F", "G1"), ("M6A", "G2"), ("M6A", "G2")],
        notation="combo",
    )

    result = read_variant_source(path)

    assert [m.mutant_id for m in result.expected] == ["V5F", "M6A", "M6A"]


def test_the_shipped_template_still_reads() -> None:
    """The bytes the operator downloads, through the reader that loads them.

    A synthetic fixture agreeing with the rule says nothing about the file
    actually shipped, and this rule was wrong about that file once already.
    """
    from kuma_core.mame.io.variant_list import read_variant_source

    repo_root = Path(__file__).resolve().parents[2]
    template = repo_root / "templates" / "03_mame_expected_mutations.xlsx"

    result = read_variant_source(template)

    assert [m.mutant_id for m in result.expected] == [
        "M001",
        "M002",
        "M003",
        "M004",
        "M005",
        "M006",
        "M006",
    ]


def test_both_paths_refuse_the_same_sheet(tmp_path: Path) -> None:
    """The two readers agree on this input rather than each merely working.

    Two paths documented as interchangeable have to be compared against each
    other; testing each alone is what let them diverge. The plain list has no
    group column, so a repeated name there is unambiguously two variants.
    """
    from kuma_core.mame.io.variant_list import read_variant_source

    kuro = _write_kuro_export(
        tmp_path / "kuro.xlsx",
        [("V5F", "G1"), ("K53N", "G2"), ("V5F", "G3")],
    )
    plain = _write_plain_list(tmp_path / "plain.xlsx", ["V5F", "K53N", "V5F"])

    with pytest.raises(ValueError, match="duplicate variant"):
        read_variant_source(kuro)
    with pytest.raises(ValueError, match="duplicate variant"):
        read_variant_source(plain)


def test_distinct_variants_still_read(tmp_path: Path) -> None:
    """The control. Without it the tests above would pass on a reader that
    refused every KURO export."""
    from kuma_core.mame.io.variant_list import read_variant_source

    path = _write_kuro_export(
        tmp_path / "kuro.xlsx", [("V5F", "G1"), ("K53N", "G2")]
    )

    result = read_variant_source(path)

    assert [m.mutant_id for m in result.expected] == ["V5F", "K53N"]


# ---------------------------------------------------------------------------
# The sibling gate, and the second implementation of the same filter
# ---------------------------------------------------------------------------


def _write_run_with_barcode(tmp_path: Path, barcode_text: str) -> tuple[Path, Path]:
    """One read whose summary states *barcode_text* as its barcode score."""
    fastq = tmp_path / "reads.fastq"
    seq = "A" * _READ_LENGTH
    qual = "I" * _READ_LENGTH
    fastq.write_text(f"@read1\n{seq}\n+\n{qual}\n", encoding="utf-8")

    summary = tmp_path / "sequencing_summary.txt"
    summary.write_text(
        "read_id\tmean_qscore_template\tsequence_length_template\tbarcode_score\n"
        f"read1\t30.0\t{_READ_LENGTH}\t{barcode_text}\n",
        encoding="utf-8",
    )
    return fastq, summary


def test_an_unusable_barcode_score_fails_the_filter(tmp_path: Path) -> None:
    """The gate five lines above the Q-score one, which was fixed alone.

    Both read the same summary dict and both were written as
    ``float(value) < minimum``. Fixing one and not the other left a read whose
    barcode score could not be established passing the gate that exists to
    reject it.
    """
    from kuma_core.mame.ingest.quality_filter import (
        QualityFilterParams,
        filter_reads_by_summary,
    )

    fastq, summary = _write_run_with_barcode(tmp_path, "nan")
    params = QualityFilterParams(target_length=_READ_LENGTH, min_barcode_score=60.0)

    _, result = filter_reads_by_summary(fastq, summary, params)

    assert result.n_passed == 0
    assert result.n_failed_barcode == 1


def test_a_good_barcode_score_still_passes(tmp_path: Path) -> None:
    """The control for the test above."""
    from kuma_core.mame.ingest.quality_filter import (
        QualityFilterParams,
        filter_reads_by_summary,
    )

    fastq, summary = _write_run_with_barcode(tmp_path, "99.0")
    params = QualityFilterParams(target_length=_READ_LENGTH, min_barcode_score=60.0)

    _, result = filter_reads_by_summary(fastq, summary, params)

    assert result.n_passed == 1
    assert result.n_failed_barcode == 0


def test_the_two_quality_filter_implementations_agree_on_nan() -> None:
    """The sidecar reimplements this filter rather than calling it.

    That is why the v0.16.33.05 fix did not reach the demux path: there are two
    copies of the same gate. Two paths documented as doing the same thing have
    to be compared against each other, so this asserts the shape rather than
    each one alone.
    """
    import inspect

    from kuma_core.mame.ingest import quality_filter
    from sidecar_mame.handlers import demux

    core = inspect.getsource(quality_filter.filter_reads_by_summary)
    sidecar = inspect.getsource(demux.handle_demux_and_filter)

    for source, name in ((core, "quality_filter"), (sidecar, "demux handler")):
        assert "math.isfinite(qscore" in source, (
            f"{name} compares a q-score without checking it is finite"
        )
        assert "math.isfinite(bscore" in source, (
            f"{name} compares a barcode score without checking it is finite"
        )
