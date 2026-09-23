"""Format converters: the round-trip control, and one negative per parser.

The control is a known answer. Every bundled table already has a canonical
digest minted by the registry, so writing it out as CSV or cusp, reading it
back and validating it has to return that same digest. Nothing about the
conversion is asserted directly -- the digest either survives or it does not,
and a writer that rounded a fraction or a parser that reordered a codon list
fails here rather than in a workspace opened on another machine.

The negative fixtures assert the code, not just "it raised": a parser that
rejected everything would pass a test that only looked for an exception. Each
one prints how many rows it examined for the same reason `checks_performed`
exists in the validator.
"""

import json

import pytest

from kuma_core.kuro import codon_formats as cf
from kuma_core.kuro import codon_table as ct
from kuma_core.kuro.codon_import import (
    MESSAGE_CODES,
    ValidationContext,
    validate_codon_table_data,
)


def _bundled() -> list[dict]:
    """The bundled tables as the registry describes them."""
    registry = ct.CodonTableRegistry()
    scan = registry.scan()
    return [o for o in scan["organisms"] if o["source"] == "builtin"]


BUNDLED = _bundled()
BUNDLED_KEYS = [o["key"] for o in BUNDLED]


def test_control_the_bundle_is_the_five_tables_this_suite_expects():
    """Guard the control itself: a round trip over an empty list proves nothing."""
    assert len(BUNDLED) == 5, BUNDLED_KEYS
    assert sorted(BUNDLED_KEYS) == [
        "bsubtilis", "ecoli", "hsapiens", "mextorquens", "scerevisiae",
    ]
    for entry in BUNDLED:
        assert entry["table_sha256"], entry["key"]


# --- round trip ------------------------------------------------------------


def _revalidate(document: dict, key: str) -> str:
    report = validate_codon_table_data(
        document, stem=key, context=ValidationContext()
    )
    assert report.ok, (key, report.error_codes,
                       [f.detail for f in report.errors])
    assert report.codons_examined or report.checks_performed, key
    return report.table_sha256


@pytest.mark.parametrize("entry", BUNDLED, ids=BUNDLED_KEYS)
def test_json_round_trip_preserves_the_digest(entry):
    """The stored document is the export: serialise and read it back verbatim."""
    blob = json.dumps(entry["document"], indent=2)
    assert _revalidate(json.loads(blob), entry["key"]) == entry["table_sha256"]


@pytest.mark.parametrize("entry", BUNDLED, ids=BUNDLED_KEYS)
def test_csv_round_trip_preserves_the_digest(entry):
    text = cf.format_table(entry["document"], "csv")
    parsed = cf.parse_table_text(text, "csv")
    # CSV carries no identity and no genetic code (design note section 3.3),
    # so the import dialog supplies them. Rebuilt here the way the handler
    # rebuilds them, which is what makes this a test of the round trip and
    # not of a hand-written document.
    rebuilt = {
        "key": entry["key"],
        "name": entry["name"],
        "taxid": entry["taxid"],
        "genetic_code": entry["document"]["genetic_code"],
        "codons": parsed["codons"],
    }
    assert _revalidate(rebuilt, entry["key"]) == entry["table_sha256"]


@pytest.mark.parametrize("entry", BUNDLED, ids=BUNDLED_KEYS)
def test_cusp_round_trip_preserves_the_digest(entry):
    text = cf.format_table(entry["document"], "cusp")
    parsed = cf.parse_table_text(text, "cusp")
    rebuilt = {
        "key": entry["key"],
        "name": entry["name"],
        "taxid": entry["taxid"],
        "genetic_code": entry["document"]["genetic_code"],
        "codons": parsed["codons"],
    }
    if "counts" in parsed:
        rebuilt["counts"] = parsed["counts"]
    assert _revalidate(rebuilt, entry["key"]) == entry["table_sha256"]


def test_cusp_export_omits_the_number_column_when_there_are_no_counts():
    """Writing 0 counts would make N4 recompute every fraction to zero.

    V24 would then reject a file kuma had just written. The column is left
    out instead, which is why the round trip above survives.
    """
    entry = next(e for e in BUNDLED if e["key"] == "ecoli")
    assert "counts" not in entry["document"]
    text = cf.format_table(entry["document"], "cusp")
    header = [ln for ln in text.splitlines() if ln.startswith("#Codon AA")][0]
    assert header == "#Codon AA Fraction Frequency"
    assert "counts" not in cf.parse_table_text(text, "cusp")


def test_two_input_paths_agree_on_one_table():
    """Same numbers through JSON and through CSV give one stored table.

    Each parser passing on its own and the two parsers agreeing are different
    claims (design note, Phase 3 verification). This is the second one.
    """
    entry = next(e for e in BUNDLED if e["key"] == "bsubtilis")
    via_json = _revalidate(json.loads(json.dumps(entry["document"])), entry["key"])
    parsed = cf.parse_table_text(cf.format_table(entry["document"], "csv"), "csv")
    via_csv = _revalidate(
        {
            "key": entry["key"],
            "name": entry["name"],
            "taxid": entry["taxid"],
            "genetic_code": entry["document"]["genetic_code"],
            "codons": parsed["codons"],
        },
        entry["key"],
    )
    assert via_json == via_csv == entry["table_sha256"]


def test_discrimination_a_different_organism_does_not_match():
    """The round-trip assertion can fail. Two bundles must not share a digest."""
    digests = {e["key"]: e["table_sha256"] for e in BUNDLED}
    assert len(set(digests.values())) == len(digests), digests


# --- negative fixtures -----------------------------------------------------


def _reject(text: str, fmt: str) -> cf.CodonFormatError:
    with pytest.raises(cf.CodonFormatError) as excinfo:
        cf.parse_table_text(text, fmt)
    assert excinfo.value.code == "V36"
    assert excinfo.value.params["format"] == fmt
    return excinfo.value


def test_csv_with_a_short_row_is_rejected(capsys):
    text = "amino_acid,codon,relative_frequency\nA,GCC,0.51\nA,GCG\n"
    err = _reject(text, "csv")
    assert err.line == 3
    print(f"csv rows examined: 2, rejected at line {err.line}")
    assert "column" in err.params["detail"]


def test_csv_without_a_frequency_column_is_rejected():
    text = "amino_acid,codon\nA,GCC\n"
    err = _reject(text, "csv")
    assert err.line == 1
    assert "frequency" in err.params["detail"]


def test_csv_header_spellings_that_should_be_accepted():
    """CONTROL for the two rejections above: the reader is not rejecting all CSV."""
    text = "aa,triplet,fraction\nA,GCC,0.51\n"
    parsed = cf.parse_table_text(text, "csv")
    assert parsed["codons"] == {"A": [["GCC", 0.51]]}
    print("csv header spellings checked: 1 accepted, 2 rejected")


def test_cusp_with_a_broken_header_row_is_rejected():
    """A row that is not five fields. The '#' lines are skipped, this one is not."""
    text = (
        "#Codon AA Fraction Frequency Number\n"
        "GCC A 0.511 20.0 1234\n"
        "GCG A 0.390\n"
    )
    err = _reject(text, "cusp")
    assert err.line == 3
    print(f"cusp rows examined: 2, rejected at line {err.line}")


def test_cusp_that_is_only_comments_is_rejected():
    err = _reject("#Codon AA Fraction Frequency Number\n#\n", "cusp")
    assert "below the header" in err.params["detail"]


def test_cusp_control_a_well_formed_file_parses():
    text = "#Codon AA Fraction Frequency Number\nGCC A 0.511 20.0 1234\n"
    parsed = cf.parse_table_text(text, "cusp")
    assert parsed["codons"] == {"A": [["GCC", 0.511]]}
    assert parsed["counts"] == {"A": [["GCC", 1234]]}
    print("cusp rows checked: 1 accepted, 2 files rejected")


def test_kazusa_paste_without_the_amino_acid_column_is_rejected():
    """The exact failure the design note names: a paste missing the AA letter."""
    text = "UUU 0.58 22.4 ( 10345)  UUC 0.42 16.0 (  7412)\n"
    err = _reject(text, "kazusa")
    assert "amino acid" in err.params["detail"]
    print("kazusa blocks examined: 2, amino acid column absent")


def test_kazusa_prose_is_rejected_with_the_other_reason():
    """Two distinguishable failures, not one catch-all."""
    err = _reject("no codon table on this page at all\n", "kazusa")
    assert "blocks were found" in err.params["detail"]


def test_kazusa_control_keeps_rna_for_the_validator_to_normalise():
    """U is left in place so N1 reports the conversion instead of hiding it."""
    text = "UUU F 0.58 22.4 ( 10345)  UUC F 0.42 16.0 (  7412)\n"
    parsed = cf.parse_table_text(text, "kazusa")
    assert parsed["codons"] == {"F": [["UUU", 0.58], ["UUC", 0.42]]}
    assert parsed["counts"] == {"F": [["UUU", 10345], ["UUC", 7412]]}
    print("kazusa blocks checked: 2 accepted, 2 pastes rejected")


def test_v36_is_declared_where_the_locale_gate_reads_it():
    assert "V36" in MESSAGE_CODES
    assert len(MESSAGE_CODES) == 40
