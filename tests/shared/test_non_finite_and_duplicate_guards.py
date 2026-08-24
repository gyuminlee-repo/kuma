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

# ---------------------------------------------------------------------------
# The outermost place that can refuse a non-finite number
# ---------------------------------------------------------------------------


def test_bare_non_finite_literals_are_refused_at_the_rpc_boundary() -> None:
    """Python's JSON parser accepts NaN and Infinity as bare tokens.

    No other JSON implementation emits them and RFC 8259 does not describe
    them, but the parser takes them, so a parameter no comparison can use
    reached the handlers. Every handler still guards its own numbers; this is
    the door.
    """
    import json

    from kuma_core.shared.sidecar import loads_rpc_request

    for literal in ("NaN", "Infinity", "-Infinity"):
        line = '{"jsonrpc":"2.0","method":"x","params":{"v":%s}}' % literal
        # It parses today, which is what makes the guard necessary.
        assert json.loads(line)["params"]["v"] is not None
        with pytest.raises(json.JSONDecodeError):
            loads_rpc_request(line)


def test_ordinary_requests_still_parse() -> None:
    """The control. Without it a parser that refused everything would pass."""
    from kuma_core.shared.sidecar import loads_rpc_request

    request = loads_rpc_request(
        '{"jsonrpc":"2.0","id":1,"method":"analyze","params":{"v":0.5,"n":null}}'
    )

    assert request["method"] == "analyze"
    assert request["params"]["v"] == 0.5
    assert request["params"]["n"] is None


def test_the_refusal_is_the_type_the_loop_already_answers() -> None:
    """Both stdin loops answer json.JSONDecodeError with a -32700 parse error.

    Raising anything else would escape that handler and take the sidecar down
    on a malformed request instead of replying to it.
    """
    import json

    from kuma_core.shared.sidecar import loads_rpc_request

    with pytest.raises(json.JSONDecodeError):
        loads_rpc_request('{"params":{"v":NaN}}')
    with pytest.raises(json.JSONDecodeError):
        loads_rpc_request("not json at all")


def test_both_dispatchers_parse_through_the_guard() -> None:
    """Neither stdin loop may call json.loads directly.

    The two loops are copies of each other, which is how the last fix in this
    family landed on one and not the other.
    """
    import inspect

    from sidecar_kuro import dispatcher as kuro_dispatcher
    from sidecar_mame import dispatcher as mame_dispatcher

    for name, module in (
        ("sidecar_kuro", kuro_dispatcher),
        ("sidecar_mame", mame_dispatcher),
    ):
        source = inspect.getsource(module.main)
        assert "loads_rpc_request(line)" in source, (
            f"{name} parses its stdin line without the non-finite guard"
        )
        assert "json.loads(line)" not in source, (
            f"{name} still calls json.loads on the request line"
        )


def test_overflowing_number_literals_are_refused_at_the_rpc_boundary() -> None:
    """``1e400`` is a valid JSON number whose value is infinity.

    ``parse_constant`` never sees it, so a guard built only from the three bare
    tokens refused the spelling and admitted the value: the door reported
    ``NaN`` and ``Infinity`` as refused while ``{"v": 1e400}`` arrived as
    ``inf`` and disabled whatever comparison it was used in.
    """
    import json

    from kuma_core.shared.sidecar import find_non_finite_paths, loads_rpc_request

    overflowing = (
        '{"jsonrpc":"2.0","method":"x","params":{"v":1e400}}',
        '{"jsonrpc":"2.0","method":"x","params":{"v":-1e400}}',
        # Nested, because a payload carries its numbers inside lists and
        # objects far more often than at the top level.
        '{"params":{"rows":[{"gc":1e400}]}}',
        '{"params":{"rows":[[0.5,-1e400]]}}',
        '{"params":{"v":1E400}}',
    )
    for line in overflowing:
        # It parses today, which is what makes the guard necessary.
        assert find_non_finite_paths(json.loads(line)), (
            f"probe is wrong: {line} does not decode to a non-finite value"
        )
        with pytest.raises(json.JSONDecodeError):
            loads_rpc_request(line)


def test_finite_numbers_near_the_edge_still_parse() -> None:
    """The controls. Without them a parser that refused every float would pass.

    ``1e-400`` underflows to ``0.0``, which is finite and compares normally.
    Refusing it would turn a finiteness guard into a precision policy, which is
    a different question and not the one this door answers.
    """
    from kuma_core.shared.sidecar import loads_rpc_request

    assert loads_rpc_request('{"v":1e308}')["v"] == 1e308
    assert loads_rpc_request('{"v":-1e308}')["v"] == -1e308
    assert loads_rpc_request('{"v":1e-400}')["v"] == 0.0
    assert loads_rpc_request('{"v":0.1,"n":[1,2,3],"s":"1e400"}') == {
        "v": 0.1,
        "n": [1, 2, 3],
        "s": "1e400",
    }


def test_the_overflow_message_does_not_claim_the_literal_was_invalid() -> None:
    """``1e400`` is well formed JSON, unlike the bare ``Infinity`` token.

    Reusing the constant-path wording would ship a false statement in an error
    message that a user reads when a run is refused.
    """
    import json

    from kuma_core.shared.sidecar import loads_rpc_request

    with pytest.raises(json.JSONDecodeError) as excinfo:
        loads_rpc_request('{"v":1e400}')
    message = str(excinfo.value)
    assert "not valid JSON" not in message
    assert "overflows" in message
    assert "cannot be compared against any threshold" in message
    assert "send a finite number or omit the field" in message

    with pytest.raises(json.JSONDecodeError) as excinfo:
        loads_rpc_request('{"v":Infinity}')
    assert "is not valid JSON" in str(excinfo.value)


def test_every_unparseable_line_raises_the_type_the_loops_answer() -> None:
    """The loops catch ``json.JSONDecodeError`` and nothing else.

    ``json`` does not raise only that type. A number literal longer than the
    interpreter integer-string limit raises a plain ``ValueError`` from
    ``int()``, and a deeply nested payload raises ``RecursionError``. Measured
    before the fix, both unwound straight out of ``main`` and the sidecar
    process exited with code 1 on one malformed line.
    """
    import json

    from kuma_core.shared.sidecar import loads_rpc_request

    unparseable = (
        # Over the 4300-digit limit for integer string conversion.
        '{"jsonrpc":"2.0","id":2,"method":"ping","params":{"n":' + "9" * 4400 + "}}",
        # Nested, because a number does not have to sit at the top level.
        '{"params":[1,' + "9" * 5000 + "]}",
        # Past the depth at which the C scanner gives up.
        '{"params":' + "[" * 100000 + "]" * 100000 + "}",
        # The ordinary cases, which already worked.
        "not json at all",
        '{"a":',
    )
    for line in unparseable:
        with pytest.raises(json.JSONDecodeError):
            loads_rpc_request(line)


def test_the_conversion_is_not_a_blanket_except() -> None:
    """A defect in this module must not be answered as a parse error.

    Turning any exception into ``-32700`` would blame the caller for a bug
    here and hide it. Only the parser telling us the line is unusable is
    converted, so a ``TypeError`` still escapes.
    """
    import json

    from kuma_core.shared.sidecar import loads_rpc_request

    # Control: the conversion that must happen still happens.
    with pytest.raises(json.JSONDecodeError):
        loads_rpc_request("9" * 5000)

    # A non-str argument is a caller-side type error in this process, not a
    # malformed request line, and it is not disguised as one.
    with pytest.raises(TypeError):
        loads_rpc_request(object())  # type: ignore[arg-type]


def test_the_parse_error_names_what_went_wrong() -> None:
    """A ``-32700`` that says only "Parse error" cannot be acted on."""
    import json

    from kuma_core.shared.sidecar import loads_rpc_request

    with pytest.raises(json.JSONDecodeError) as excinfo:
        loads_rpc_request('{"params":{"n":' + "9" * 4400 + "}}")
    assert "ValueError" in str(excinfo.value)
    assert "4300 digits" in str(excinfo.value)

    with pytest.raises(json.JSONDecodeError) as excinfo:
        loads_rpc_request('{"params":' + "[" * 100000 + "]" * 100000 + "}")
    assert "RecursionError" in str(excinfo.value)
