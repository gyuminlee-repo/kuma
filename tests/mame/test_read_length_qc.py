"""Read length QC quoted out of a MinKNOW ``report_*.json``.

The fixtures below are hand written rather than copied from a run folder, and
they carry the quirks that actually break a parser rather than the bulk of a
2.3 MB file: bucket edges and values written as STRINGS, a first bucket with no
``start`` key, an entry with no ``read_length_type`` at all, an ``n50`` that can
arrive as either an int or a numeric string, and a calibration acquisition that
carries no histogram. A fixture of clean integers would pass a parser that
crashes on the real thing.

The numbers are chosen so every expected fraction is exact against a reference
of 1000 bp: 950 bases inside the plot, 50 in the tail, 700 of them in the
900-1100 window and 200 at or past 2000.
"""

from __future__ import annotations

import json
from pathlib import Path

from kuma_core.mame.ingest.read_length import (
    read_read_length_qc,
    serialise_read_length_qc,
)

REFERENCE_BP = 1000


def _plot() -> dict:
    """A three-bin plot. Bin 1 sits inside the window, bin 2 past the doubling."""
    return {
        "bucket_value_type": "ReadLengths",
        # The first range carries no `start`, exactly as MinKNOW writes it.
        "bucket_ranges": [
            {"end": "500"},
            {"start": "500", "end": "1500"},
            {"start": "1500", "end": "2500"},
        ],
        "histogram_data": [{"bucket_values": ["100", "700", "150"], "n50": "1900"}],
        "source_data_end": 2500,
    }


def _outliers() -> dict:
    """The tail. Labelled from zero even though it holds only long reads."""
    return {
        "bucket_value_type": "ReadLengths",
        "bucket_ranges": [{"end": "4000"}],
        "histogram_data": [{"bucket_values": ["50"]}],
        "source_data_end": 4000,
    }


def _report_payload(*, with_histograms: bool = True) -> dict:
    acquisition: dict = {"acquisition_run_info": {}}
    if with_histograms:
        acquisition["read_length_histogram"] = [
            # No `read_length_type`: the real file's first entry has none.
            {
                "bucket_value_type": "ReadLengths",
                "plot": _plot(),
                "outliers": _outliers(),
            },
            {
                "read_length_type": "EstimatedBases",
                "bucket_value_type": "ReadLengths",
                "plot": {**_plot(), "histogram_data": [{
                    "bucket_values": ["100", "700", "150"], "n50": 1500,
                }]},
                "outliers": _outliers(),
            },
            # A value type this module has not verified: the fractions must go
            # null while the quoted N50 stays.
            {
                "read_length_type": "BasecalledBases",
                "bucket_value_type": "SomethingElse",
                "plot": {**_plot(), "bucket_value_type": "SomethingElse"},
                "outliers": None,
            },
        ]
        acquisition["qscore_histograms"] = [
            {
                "bucket_value_type": "QScore_BasecalledBases",
                "bucket_ranges": [{"end": 1}, {"start": 1, "end": 2}],
                "histogram_data": [
                    {
                        "filtering": [
                            {"read_type": "Simplex", "call_status": "Passed"}
                        ],
                        "bucket_values": ["0", "12"],
                        "modal_q_score": 16.65,
                    },
                    {
                        "filtering": [
                            {"read_type": "Simplex", "call_status": "Failed"}
                        ],
                        "bucket_values": ["3", "0"],
                        "modal_q_score": 8.1,
                    },
                ],
            }
        ]
    return {
        # A calibration acquisition first, which carries none of this. The
        # parser must not index into acquisition zero.
        "acquisitions": [{"acquisition_run_info": {}}, acquisition],
    }


def _write_report(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report_TEST_20260101_0000_abcdef.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_no_report_json_is_null_everywhere(tmp_path: Path) -> None:
    """A folder with no report reports nothing, and nothing is zero."""
    block = serialise_read_length_qc(read_read_length_qc(tmp_path), REFERENCE_BP)
    assert block["histograms"] is None
    assert block["qscore_histograms"] is None
    # Null, not an empty list: a run whose report was never read is not a run
    # whose reads had no lengths.
    assert block["histograms"] != []


def test_report_without_read_length_histogram_is_null(tmp_path: Path) -> None:
    """Older MinKNOW writes the report without the histogram key."""
    _write_report(tmp_path, _report_payload(with_histograms=False))
    qc = read_read_length_qc(tmp_path)
    assert qc.histograms is None
    assert qc.qscore_histograms is None


def test_unreadable_report_is_null_rather_than_an_error(tmp_path: Path) -> None:
    tmp_path.joinpath("report_TEST.json").write_text("{not json", encoding="utf-8")
    assert read_read_length_qc(tmp_path).histograms is None


def test_report_is_found_one_level_up(tmp_path: Path) -> None:
    """A consensus-directory run is analysed from inside the run folder."""
    _write_report(tmp_path, _report_payload())
    consensus = tmp_path / "consensus"
    consensus.mkdir()
    assert read_read_length_qc(consensus).histograms is not None


def test_every_n50_is_carried_with_its_own_label(tmp_path: Path) -> None:
    """Three entries, three N50s, and the unlabelled one stays unlabelled."""
    _write_report(tmp_path, _report_payload())
    block = serialise_read_length_qc(read_read_length_qc(tmp_path), REFERENCE_BP)
    entries = block["histograms"]
    assert [e["read_length_type"] for e in entries] == [
        None, "EstimatedBases", "BasecalledBases",
    ]
    # A string n50 and an int n50 both arrive as ints.
    assert [e["n50"] for e in entries] == [1900, 1500, 1900]
    assert [e["n50_over_reference"] for e in entries] == [1.9, 1.5, 1.9]


def test_buckets_survive_string_encoding_and_a_missing_first_start(
    tmp_path: Path,
) -> None:
    _write_report(tmp_path, _report_payload())
    entry = serialise_read_length_qc(
        read_read_length_qc(tmp_path), REFERENCE_BP
    )["histograms"][0]
    assert entry["plot"]["bucket_starts"] == [0, 500, 1500]
    assert entry["plot"]["bucket_ends"] == [500, 1500, 2500]
    assert entry["plot"]["bucket_values"] == [100, 700, 150]
    assert entry["plot"]["total"] == 950
    # The tail is a separate distribution, never concatenated onto the plot.
    assert entry["outliers"]["bucket_values"] == [50]


def test_fractions_count_the_tail_and_are_shares_of_bases(tmp_path: Path) -> None:
    """700 of 1000 bases inside the window, 150 + 50 at or past the doubling."""
    _write_report(tmp_path, _report_payload())
    entry = serialise_read_length_qc(
        read_read_length_qc(tmp_path), REFERENCE_BP
    )["histograms"][0]
    assert entry["near_reference_bases_fraction"] == 0.7
    # The outlier bin only qualifies once its start is clipped to where its
    # reads actually begin; leaving it out would undercount concatemers, which
    # is the one thing this number exists to show.
    assert entry["over_2x_reference_bases_fraction"] == 0.2


def test_unverified_bucket_value_type_yields_null_fractions(tmp_path: Path) -> None:
    """A value type nobody checked cannot be turned into a share of anything."""
    _write_report(tmp_path, _report_payload())
    entry = serialise_read_length_qc(
        read_read_length_qc(tmp_path), REFERENCE_BP
    )["histograms"][2]
    assert entry["bucket_value_type"] == "SomethingElse"
    assert entry["near_reference_bases_fraction"] is None
    assert entry["over_2x_reference_bases_fraction"] is None
    # The buckets themselves are still carried, and the quoted N50 still
    # divides by a length.
    assert entry["plot"]["total"] == 950
    assert entry["n50_over_reference"] == 1.9
    # An entry that carried no tail says so with null rather than an empty one.
    assert entry["outliers"] is None


def test_no_reference_length_leaves_the_relative_numbers_null(
    tmp_path: Path,
) -> None:
    _write_report(tmp_path, _report_payload())
    block = serialise_read_length_qc(read_read_length_qc(tmp_path), None)
    assert block["reference_length_bp"] is None
    for entry in block["histograms"]:
        assert entry["n50_over_reference"] is None
        assert entry["near_reference_bases_fraction"] is None
        assert entry["over_2x_reference_bases_fraction"] is None
        # The instrument's own figures are unaffected by our not knowing a
        # reference length.
        assert entry["n50"] is not None


def test_qscore_series_keep_the_filter_they_were_measured_under(
    tmp_path: Path,
) -> None:
    _write_report(tmp_path, _report_payload())
    block = serialise_read_length_qc(read_read_length_qc(tmp_path), REFERENCE_BP)
    series = block["qscore_histograms"][0]["series"]
    assert len(series) == 2
    assert series[0]["filtering"] == [
        {"read_type": "Simplex", "call_status": "Passed"}
    ]
    assert series[0]["modal_q_score"] == 16.65
    assert series[1]["filtering"][0]["call_status"] == "Failed"


def test_the_block_says_where_its_numbers_came_from(tmp_path: Path) -> None:
    """The N50 is quoted from the instrument, and the block admits it."""
    _write_report(tmp_path, _report_payload())
    block = serialise_read_length_qc(read_read_length_qc(tmp_path), REFERENCE_BP)
    assert block["provenance"]["n50"]["kind"] == "instrument_report"
    assert block["provenance"]["n50"]["computed"] is False
    assert block["provenance"]["relative"]["computed"] is True
    # Nothing on this block gates anything.
    assert all(p["enforced"] is False for p in block["provenance"].values())
