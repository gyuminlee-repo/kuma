"""``demux_and_filter`` with no sequencing_summary: the gates still run.

The handler used to wrap its whole A3 stage in ``if sequencing_summary is not
None``.  A run handed no summary therefore skipped the quality filter outright:
``min_qscore`` was ignored, every read reached the per-well FASTA, and
``filter_stats`` came back null while the reads the caller asked to be dropped
were counted as having passed.

``kuma_core.mame.ingest.quality_filter.filter_reads_by_summary`` never had that
hole; with ``sequencing_summary=None`` it computes the Q-score from the FASTQ
Phred string and applies the length window to ``len(seq)``.  These tests pin the
sidecar to that same behaviour, and the last one compares the two directly so a
future edit to one side cannot drift away from the other in silence.

No alignment happens here (no ``reference_fasta``), so the module needs no
minimap2 marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.ingest.quality_filter import (
    QualityFilterParams,
    filter_reads_by_summary,
)
from sidecar_mame.handlers.demux import handle_demux_and_filter

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

_BODY = (
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)

_BARCODES = {
    "1_1": "AATCCCACT",
    "1_2": "TTGGAACCC",
}

#: Full-length read: barcode prefix plus body. linked_trim is off, so the
#: record written to the per-well FASTA is this whole string.
_READ_LENGTH = len(_BARCODES["1_1"]) + len(_BODY)

#: Phred+33 "I" is Q40, comfortably above the default min_qscore of 8.0.
_HIGH_Q = "I"
#: Phred+33 "!" is Q0, below every usable threshold.
_LOW_Q = "!"

#: read_id of the one record that must not survive the Q-score gate.
_LOW_Q_READ = "read_lowq"
#: read_id of the one record that must not survive the length window.
_SHORT_READ = "read_short"


def _write_fastq(path: Path, reads: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for read_id, seq, qual in reads:
            fh.write(f"@{read_id}\n{seq}\n+\n{qual}\n")


@pytest.fixture()
def fastq_file(tmp_path: Path) -> Path:
    """One FASTQ carrying four reads with three distinct fates.

    Two pass, one fails on Q-score alone, one fails on length alone.  Keeping
    the two failure reasons on separate records is what lets the tallies below
    distinguish the gates instead of only counting a total.
    """
    good_seq = _BARCODES["1_1"] + _BODY
    reads = [
        ("read_pass_a", good_seq, _HIGH_Q * len(good_seq)),
        ("read_pass_b", good_seq, _HIGH_Q * len(good_seq)),
        # Same length and same well, unusable basecalls.
        (_LOW_Q_READ, _BARCODES["1_2"] + _BODY, _LOW_Q * (len(_BARCODES["1_2"]) + len(_BODY))),
        # Same quality as the passing reads, far outside the length window.
        (_SHORT_READ, _BARCODES["1_1"] + _BODY[:100], _HIGH_Q * (len(_BARCODES["1_1"]) + 100)),
    ]
    fastq = tmp_path / "fastq_pass" / "barcode06" / "reads.fastq"
    _write_fastq(fastq, reads)
    return fastq


def _run_handler(fastq_file: Path, tmp_path: Path, **overrides: object) -> dict:
    params: dict = {
        "fastq_dir": str(fastq_file.parent),
        "custom_barcodes": _BARCODES,
        "output_dir": str(tmp_path / "out"),
        "use_cutadapt": False,
        "auto_detect_length": False,
        "target_length": _READ_LENGTH,
    }
    params.update(overrides)
    return handle_demux_and_filter(params)


def _headers(output_dir: Path) -> list[str]:
    """Every FASTA header under *output_dir*, per-well files only."""
    found: list[str] = []
    for fasta in sorted(output_dir.rglob("*.fasta")):
        if fasta.name.startswith("_"):
            continue
        for line in fasta.read_text(encoding="utf-8").splitlines():
            if line.startswith(">"):
                found.append(line[1:].split()[0])
    return found


# ---------------------------------------------------------------------------
# The gate runs at all
# ---------------------------------------------------------------------------


def test_filter_stats_is_reported_without_a_summary(
    fastq_file: Path, tmp_path: Path
) -> None:
    """A run with no summary reports what the filter did, rather than null.

    Against the unfixed handler this fails here: ``filter_stats`` stayed None
    because the whole stage sat behind ``if sequencing_summary is not None``.
    """
    result = _run_handler(fastq_file, tmp_path)

    assert result["filter_stats"] is not None, (
        "filter_stats is null on a run with no sequencing_summary, so nothing "
        "reports whether min_qscore was applied"
    )
    assert result["filter_stats"]["n_input"] == 4


def test_low_qscore_read_is_removed_without_a_summary(
    fastq_file: Path, tmp_path: Path
) -> None:
    """The Q0 read is gone from the output and counted as a Q-score failure."""
    result = _run_handler(fastq_file, tmp_path)
    stats = result["filter_stats"]

    assert stats is not None
    assert stats["n_failed_qscore"] == 1, (
        f"expected the Q0 read to fail min_qscore, got {stats}"
    )
    assert _LOW_Q_READ not in _headers(tmp_path / "out")


def test_passing_reads_survive_without_a_summary(
    fastq_file: Path, tmp_path: Path
) -> None:
    """The control: the test above is not passing because the filter rejects
    everything, which a wrong length window would also produce."""
    result = _run_handler(fastq_file, tmp_path)
    stats = result["filter_stats"]

    assert stats is not None
    assert stats["n_passed"] == 2
    assert result["per_well_counts"].get("1_1") == 2


def test_out_of_window_read_is_removed_without_a_summary(
    fastq_file: Path, tmp_path: Path
) -> None:
    """The length window is enforced from ``len(seq)``, as the library does.

    A caller who sets target_length and hands no summary is asking for this
    window; leaving it unapplied would repeat the Q-score defect one parameter
    over.
    """
    result = _run_handler(fastq_file, tmp_path)
    stats = result["filter_stats"]

    assert stats is not None
    assert stats["n_failed_length"] == 1, (
        f"expected the short read to fail the length window, got {stats}"
    )
    assert _SHORT_READ not in _headers(tmp_path / "out")


def test_barcode_gate_reports_unmeasured_not_zero(
    fastq_file: Path, tmp_path: Path
) -> None:
    """barcode_score lives only in the summary, so with none given the gate did
    not run.  It is reported as null, never 0: RunQcSection.tsx renders null as
    the localized not-measured text and 0 as a reading of "none failed"."""
    result = _run_handler(fastq_file, tmp_path)
    stats = result["filter_stats"]

    assert stats is not None
    assert stats["n_failed_barcode"] is None, (
        "0 here would claim the barcode_score gate ran and cleared every read"
    )


def test_legacy_output_keeps_well_name_headers(
    fastq_file: Path, tmp_path: Path
) -> None:
    """Filtering moved header normalization into the strip pass, so the output
    format a legacy caller sees must be unchanged: one ``>{well}`` per record."""
    _run_handler(fastq_file, tmp_path)

    headers = _headers(tmp_path / "out")
    assert headers == ["1_1", "1_1"], f"expected well-name headers, got {headers}"


# ---------------------------------------------------------------------------
# The two implementations of the same gate
# ---------------------------------------------------------------------------


def test_sidecar_and_library_agree_on_the_no_summary_gate(
    fastq_file: Path, tmp_path: Path
) -> None:
    """Both implementations of the A3 filter must decide the same reads.

    The handler reimplements the filter that ``kuma_core`` already owns, and a
    fix landing on one side and not the other has shipped in this repository
    before (the NaN guard, v0.16.33.05).  Feeding one FASTQ through both and
    comparing the tallies is what makes that drift fail a test rather than a
    run.

    ``n_failed_barcode`` is deliberately excluded: the library reports 0 for a
    gate it never ran, the handler reports None.  That divergence is the point
    of ``test_barcode_gate_reports_unmeasured_not_zero`` and is asserted there.
    """
    handler_stats = _run_handler(fastq_file, tmp_path)["filter_stats"]

    params = QualityFilterParams(target_length=_READ_LENGTH)
    _, library = filter_reads_by_summary(fastq_file, None, params)

    assert handler_stats is not None
    compared = ("n_input", "n_passed", "n_failed_qscore", "n_failed_length")
    handler_side = {k: handler_stats[k] for k in compared}
    library_side = {k: getattr(library, k) for k in compared}

    assert handler_side == library_side, (
        "the no-summary quality gate drifted between its two implementations. "
        f"sidecar python-core/sidecar_mame/handlers/demux.py says {handler_side}; "
        f"library kuma_core/mame/ingest/quality_filter.py says {library_side}. "
        "The side that changed most recently is the one that drifted; the "
        "library is the reference form."
    )


# ---------------------------------------------------------------------------
# Multi-NB mode
# ---------------------------------------------------------------------------


def test_explicit_nb_dirs_outside_fastq_dir_are_all_gated(tmp_path: Path) -> None:
    """With explicit ``nb_dirs``, every listed directory feeds the gate.

    The no-summary branch enumerates ``nb_dirs`` when they are given and
    ``fastq_dir`` otherwise, and the two are not required to be nested.  Reading
    only ``fastq_dir`` here would find no FASTQ at all, leave the fail set
    empty, and hand back a filter_stats of all zeros while every low-quality
    read survived, which is the same silent pass in a different shape.
    """
    fastq_root = tmp_path / "fastq_pass"
    fastq_root.mkdir()

    good_seq = _BARCODES["1_1"] + _BODY
    low_seq = _BARCODES["1_2"] + _BODY
    nb_dirs = []
    for nb in ("NB01", "NB02"):
        nb_dir = tmp_path / "elsewhere" / nb
        _write_fastq(
            nb_dir / "reads.fastq",
            [
                (f"{nb}_pass", good_seq, _HIGH_Q * len(good_seq)),
                (f"{nb}_low", low_seq, _LOW_Q * len(low_seq)),
            ],
        )
        nb_dirs.append(str(nb_dir))

    output_dir = tmp_path / "out"
    result = handle_demux_and_filter(
        {
            "fastq_dir": str(fastq_root),
            "custom_barcodes": _BARCODES,
            "output_dir": str(output_dir),
            "nb_dirs": nb_dirs,
            "use_cutadapt": False,
            "auto_detect_length": False,
            "target_length": _READ_LENGTH,
            # Keep read IDs so the assertions below can name the record that
            # had to go, rather than counting anonymous well-name headers.
            "normalize_headers": False,
        }
    )

    stats = result["filter_stats"]
    assert stats is not None
    assert stats["n_input"] == 4, f"both nb_dirs must be read, got {stats}"
    assert stats["n_failed_qscore"] == 2, f"expected one Q0 read per NB, got {stats}"

    surviving = _headers(output_dir)
    assert sorted(surviving) == ["NB01_pass", "NB02_pass"], surviving
