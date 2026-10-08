"""The compute RPC: that wiring it changed no number, and how it refuses.

WHY THE CONTROL IS "SAME AS THE MODULE", NOT "SAME AS A LITERAL".
``tests/test_codon_compute.py`` already pins the arithmetic against an
independently measured tally and against two RefSeq genomes. What Phase 4b
added is a wire: parameters in, a tally, a validation, a file. The defect this
file exists to catch is a wire that alters what it carries -- a genetic code
substituted for a default, an alias list dropped, a document rebuilt from raw
bytes instead of from the validator's normalised form. So the control is the
module called directly with the same arguments, and the assertion is that the
two documents are the same object down to the canonical digest. A literal
expected value could not tell a wiring defect from a counting defect.

THE NEGATIVE CASES ARE PART OF THE CONTROL.
A path that accepts everything and a path that accepts the right things look
identical on a positive fixture. Three refusals are pinned here with the
channel each arrives on, because "it was rejected" and "it was rejected with a
sentence the dialog can translate" are different promises: a suffix kuma does
not read, a GenBank file that is not one, and a file with no coding sequences
at all.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python-core"))
# The sibling test module is imported for its synthetic genome. Appended
# rather than inserted: tests/ holds a ``sidecar_kuro`` stub-free namespace
# and putting it first shadows the real package under python-core.
sys.path.append(str(Path(__file__).parent))

from kuma_core.kuro import codon_compute as cc  # noqa: E402
from kuma_core.kuro import codon_table as codon_table_mod  # noqa: E402
from kuma_core.kuro.codon_import import canonical_digest  # noqa: E402

from sidecar_kuro.handlers.codon import (  # noqa: E402
    handle_compute_codon_table,
)

# The eight genes of the synthetic genome, reused rather than re-declared: the
# two files this test computes over have to be the ones whose expected
# exclusion reasons are already pinned in test_codon_compute.py, or a change
# there would leave this file asserting against a genome nobody checks.
from test_codon_compute import _ALL_AA_CDS, _build_synthetic  # noqa: E402


@pytest.fixture
def user_dir(tmp_path, monkeypatch) -> Iterator[Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".kuma" / "kuro" / "codon_tables"
    directory.mkdir(parents=True)
    codon_table_mod.get_registry().refresh()
    yield directory
    codon_table_mod.get_registry().refresh()


def _digest(document: dict) -> str:
    """The digest of a whole document, which is what a run manifest records."""
    return canonical_digest(document["codons"], document["genetic_code"])


def _params(path: Path, **over) -> dict:
    base = {
        "filepath": str(path),
        "key": "syn_strain",
        "name": "Synthetic strain",
        "aliases": ["synthetic strain"],
        "source": "test",
        "dry_run": True,
    }
    base.update(over)
    return base


def _direct(path: Path, **over) -> dict:
    """The same table, computed by calling the module rather than the RPC."""
    kwargs: dict = {
        "key": "syn_strain",
        "name": "Synthetic strain",
        "aliases": ("synthetic strain",),
        "source": "test",
        "taxid": None,
        "genetic_code": 11,
    }
    kwargs.update(over)
    return cc.compute_codon_table(path, **kwargs).document


# --- known answer: the wire carries the module's numbers unchanged ----------


@pytest.mark.parametrize("which", [0, 1])
def test_rpc_document_equals_the_module_called_directly(tmp_path, user_dir, which):
    """Both input formats, both through the RPC, against the module itself."""
    genome = _build_synthetic(tmp_path)[which]
    result = handle_compute_codon_table(_params(genome))
    assert result["ok"], result["errors"]

    expected = _direct(genome)
    stored = result["document"]
    assert stored["counts"] == expected["counts"]
    assert stored["codons"] == expected["codons"]
    assert stored["genetic_code"] == expected["genetic_code"]
    assert stored["aliases"] == expected["aliases"]
    # The digest is the value a run manifest records, so equality of the
    # rendered blocks is not enough on its own.
    assert _digest(stored) == _digest(expected)
    assert result["table_sha256"] == _digest(expected)


def test_the_two_input_formats_agree_through_the_rpc(tmp_path, user_dir):
    gbff, fasta = _build_synthetic(tmp_path)
    from_gb = handle_compute_codon_table(_params(gbff))
    from_fa = handle_compute_codon_table(_params(fasta, key="syn_strain_fa"))
    assert from_gb["document"]["counts"] == from_fa["document"]["counts"]
    assert from_gb["preview"]["cds_counted"] == from_fa["preview"]["cds_counted"]


def test_preview_reports_the_tally_the_module_measured(tmp_path, user_dir):
    fasta = _build_synthetic(tmp_path)[1]
    computed = cc.compute_codon_table(
        fasta, key="syn_strain", name="Synthetic strain"
    )
    preview = handle_compute_codon_table(_params(fasta))["preview"]

    assert preview["source_format"] == "fasta"
    assert preview["cds_total"] == computed.cds_total == 8
    assert preview["cds_counted"] == computed.cds_counted == 3
    assert preview["codon_count"] == computed.codon_count
    # One gene per reason, which is what the synthetic genome was built to be.
    assert preview["cds_excluded"] == {
        "pseudo": 1, "not_multiple_of_3": 1, "internal_stop": 1,
        "no_terminal_stop": 1, "ambiguous_base": 1,
    }
    # The identifier is the first word of the FASTA title, verbatim: it is
    # what the user will grep for in the file they are looking at.
    assert preview["excluded_examples"]["pseudo"] == [
        "lcl|SYN000001.1_cds_drop_pseudo"
    ]


def test_preview_names_a_most_frequent_codon_for_every_amino_acid(tmp_path, user_dir):
    """21 rows, one per group including the stop, in the module's order."""
    fasta = _build_synthetic(tmp_path)[1]
    top = handle_compute_codon_table(_params(fasta))["preview"]["top_codons"]
    assert [row["aa"] for row in top] == list(cc.AMINO_ACID_ORDER)
    assert len(top) == 21
    # The synthetic genes use exactly one codon per amino acid, so the most
    # frequent one is known without recomputing a ranking.
    by_aa = {row["aa"]: row["codon"] for row in top}
    assert by_aa["M"] == "ATG"
    assert by_aa["W"] == "TGG"
    assert by_aa["*"] == "TAA"


def test_preview_compares_against_the_bundled_reference(tmp_path, user_dir):
    """The comparison is presentational, but it has to be against a real table."""
    fasta = _build_synthetic(tmp_path)[1]
    preview = handle_compute_codon_table(_params(fasta))["preview"]
    assert preview["reference_key"] == "ecoli"
    rows = preview["divergent_codons"]
    assert 0 < len(rows) <= 10
    bundled = json.loads(
        (codon_table_mod._RESOURCES_DIR / "ecoli.json").read_text(encoding="utf-8")
    )["codons"]
    reference = {c: f for pairs in bundled.values() for c, f in pairs}
    for row in rows:
        assert row["reference_fraction"] == pytest.approx(reference[row["codon"]])
        assert row["delta"] == pytest.approx(
            row["fraction"] - row["reference_fraction"]
        )
    # Sorted by how far apart the two tables are, largest first.
    deltas = [abs(r["delta"]) for r in rows]
    assert deltas == sorted(deltas, reverse=True)


# --- the caller's genetic code is not rewritten -----------------------------


@pytest.mark.parametrize("code", [1, 11])
def test_the_chosen_genetic_code_reaches_the_stored_file(tmp_path, user_dir, code):
    """Codes 1 and 11 count identically, so only the declared number can differ.

    That is exactly why this is worth a test rather than an inspection: no
    codon-level check can tell the two apart, and the number is an input to the
    canonical digest, so a silent substitution would show up only as two
    colleagues holding tables that disagree on paper about the same science.
    """
    fasta = _build_synthetic(tmp_path)[1]
    result = handle_compute_codon_table(
        _params(fasta, genetic_code=code, dry_run=False)
    )
    assert result["ok"], result["errors"]
    assert result["document"]["genetic_code"] == code
    written = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert written["genetic_code"] == code
    assert _digest(written) == _digest(_direct(fasta, genetic_code=code))


def test_an_unsupported_genetic_code_is_refused_as_a_finding(tmp_path, user_dir):
    """G2, not a transport error: the dialog has to be able to translate it."""
    fasta = _build_synthetic(tmp_path)[1]
    result = handle_compute_codon_table(_params(fasta, genetic_code=4))
    assert result["ok"] is False
    assert [f["code"] for f in result["errors"]] == ["G2"]
    assert result["errors"][0]["params"]["code"] == 4
    assert result["checks_performed"] == 0
    assert result["document"] is None


# --- negative fixtures ------------------------------------------------------


def test_a_suffix_kuma_does_not_read_is_refused(tmp_path, user_dir):
    """A .docx is not a genome, and the refusal is a finding, not a traceback."""
    bad = tmp_path / "genome.docx"
    bad.write_text("not a genome", encoding="utf-8")
    result = handle_compute_codon_table(_params(bad))
    assert result["ok"] is False
    assert [f["code"] for f in result["errors"]] == ["G1"]
    assert result["installed"] is False


def test_a_broken_genbank_file_is_refused(tmp_path, user_dir):
    """Measured, not assumed: this arrives as G3 rather than as G1.

    Biopython's GenBank parser does not raise on a malformed header; it yields
    no records, so ``compute_codon_table`` returns cleanly with a tally of
    zero and there is no parse error for G1 to carry. What the user must read
    is "kuma found no coding sequences in this file", which is what G3 says.
    The G1 channel stays for the failures the parser does raise on -- a
    GenBank file carrying annotations but no sequence is one, and
    test_codon_compute.py pins that at the module level.
    """
    bad = tmp_path / "broken.gbff"
    bad.write_text("LOCUS  this is not a GenBank record at all\n", encoding="utf-8")
    result = handle_compute_codon_table(_params(bad))
    assert result["ok"] is False
    assert [f["code"] for f in result["errors"]] == ["G3"]
    assert result["preview"]["cds_total"] == 0


def test_a_file_with_no_coding_sequences_is_refused_once_not_21_times(
    tmp_path, user_dir
):
    """G3 rather than twenty-one V24s.

    Left to the validator this file fails "every codon for X is zero" once per
    amino acid group, and not one of those twenty-one sentences tells the user
    that the file they chose held nothing to count. The handler refuses it
    before the validator sees it and says the one thing that is actionable.
    """
    empty = tmp_path / "empty_cds.fna"
    empty.write_text(">nothing here\n", encoding="utf-8")
    result = handle_compute_codon_table(_params(empty))
    assert result["ok"] is False
    assert result["installed"] is False
    assert [f["code"] for f in result["errors"]] == ["G3"]
    assert result["preview"]["cds_counted"] == 0
    assert result["preview"]["codon_count"] == 0


def test_a_genome_whose_every_cds_is_filtered_out_is_refused_the_same_way(
    tmp_path, user_dir
):
    """The other file that reaches zero: coding sequences existed, none survived."""
    only_pseudo = tmp_path / "all_pseudo.fna"
    only_pseudo.write_text(
        ">lcl|SYN_cds_a [pseudo=true]\nATGGCTAAATAA\n"
        ">lcl|SYN_cds_b [pseudo=true]\nATGGCTAAATAA\n",
        encoding="utf-8",
    )
    result = handle_compute_codon_table(_params(only_pseudo))
    assert result["ok"] is False
    assert [f["code"] for f in result["errors"]] == ["G3"]
    # The counts are what separate this file from the empty one, and the
    # preview carries them so the dialog can show which case the user hit.
    assert result["preview"]["cds_total"] == 2
    assert result["preview"]["cds_excluded"]["pseudo"] == 2


def test_a_missing_file_raises_rather_than_reporting_a_finding(tmp_path, user_dir):
    """The one case that is not the user's data: the path itself is gone."""
    with pytest.raises(FileNotFoundError):
        handle_compute_codon_table(_params(tmp_path / "absent.fna"))


# --- low-sample warning, install and overwrite ------------------------------


def test_a_tiny_genome_warns_rather_than_passing_silently(tmp_path, user_dir):
    """V31. Three coding sequences is not a codon table anyone should trust."""
    fasta = _build_synthetic(tmp_path)[1]
    result = handle_compute_codon_table(_params(fasta))
    assert "V31" in [f["code"] for f in result["warnings"]]


def test_dry_run_writes_nothing_and_the_install_writes_once(tmp_path, user_dir):
    fasta = _build_synthetic(tmp_path)[1]
    preview = handle_compute_codon_table(_params(fasta))
    assert preview["installed"] is False
    # The folder is seeded with a README and a template on first use, so the
    # assertion is about tables, not about the folder being empty.
    assert [p.name for p in user_dir.glob("*.json")] == []

    installed = handle_compute_codon_table(_params(fasta, dry_run=False))
    assert installed["installed"] is True
    assert [p.name for p in user_dir.glob("*.json")] == ["syn_strain.json"]
    # Preview and install report the same table, which is the whole reason the
    # two share one code path.
    assert installed["table_sha256"] == preview["table_sha256"]


def test_a_second_compute_under_the_same_key_needs_overwrite(tmp_path, user_dir):
    """V10 reaches the compute path for the same reason it reaches import."""
    fasta = _build_synthetic(tmp_path)[1]
    handle_compute_codon_table(_params(fasta, dry_run=False))
    again = handle_compute_codon_table(_params(fasta, dry_run=False))
    assert again["ok"] is False
    assert "V10" in [f["code"] for f in again["errors"]]
    forced = handle_compute_codon_table(
        _params(fasta, dry_run=False, overwrite=True)
    )
    assert forced["installed"] is True


def test_a_bundled_key_is_refused(tmp_path, user_dir):
    """V9. A computed table may not take the name of a table kuma ships."""
    fasta = _build_synthetic(tmp_path)[1]
    result = handle_compute_codon_table(_params(fasta, key="ecoli"))
    assert result["ok"] is False
    assert "V9" in [f["code"] for f in result["errors"]]


def test_progress_is_reported_while_the_scan_runs(tmp_path, user_dir, monkeypatch):
    """A FASTA has a denominator, so the reported percentage is a real one."""
    seen: list[tuple[int, str]] = []
    import sidecar_kuro.handlers.codon as handler_mod

    monkeypatch.setattr(
        handler_mod, "_progress", lambda v, m="": seen.append((v, m))
    )
    fasta = _build_synthetic(tmp_path)[1]
    handle_compute_codon_table(_params(fasta))
    assert seen, "the scan reported no progress at all"
    assert all(0 <= value <= 100 for value, _ in seen)
    # tally_codons calls back once more at the end with done == total, so the
    # bar lands on the number that means finished rather than short of it.
    assert seen[-1][0] == 100
    assert "8" in seen[-1][1]


def test_a_genbank_scan_reports_a_count_without_a_percentage(
    tmp_path, user_dir, monkeypatch
):
    """The total=None path, asserted rather than assumed.

    ``compute_codon_table`` passes ``total=None`` for GenBank because it will
    not parse the file twice to get a denominator. The requirement is that
    this does not break and does not draw a bar filling at a rate no one can
    interpret: the value stays 0 and the count rides in the message.
    """
    seen: list[tuple[int, str]] = []
    import sidecar_kuro.handlers.codon as handler_mod

    monkeypatch.setattr(
        handler_mod, "_progress", lambda v, m="": seen.append((v, m))
    )
    gbff = _build_synthetic(tmp_path)[0]
    result = handle_compute_codon_table(_params(gbff))
    assert result["ok"], result["errors"]
    assert seen, "the scan reported no progress at all"
    assert all(value == 0 for value, _ in seen)
    assert "8" in seen[-1][1]


def test_a_large_fasta_reports_progress_more_than_once(tmp_path, user_dir, monkeypatch):
    """Above the 500-record callback interval the bar actually moves."""
    seen: list[tuple[int, str]] = []
    import sidecar_kuro.handlers.codon as handler_mod

    monkeypatch.setattr(
        handler_mod, "_progress", lambda v, m="": seen.append((v, m))
    )
    big = tmp_path / "many_cds.fna"
    with big.open("w", encoding="utf-8") as fh:
        for i in range(1200):
            fh.write(f">lcl|SYN_cds_{i} [locus_tag=g{i}]\n{_ALL_AA_CDS}\n")
    result = handle_compute_codon_table(_params(big))
    assert result["ok"], result["errors"]
    assert len(seen) >= 3
    values = [v for v, _ in seen]
    assert values == sorted(values)
    assert max(values) == 100, "a FASTA has a denominator, so the bar must fill"


def test_the_accepted_suffixes_are_the_ones_codon_compute_can_classify():
    """The set in core.py against what _format actually routes.

    The suffix list now exists in three places -- this set, the two branches of
    ``codon_compute._format``, and the browse filter in the dialog. Only the
    first two can be compared by a program, and they are the pair that matters:
    a suffix accepted here that ``_format`` cannot classify would be refused
    one layer deeper with a worse sentence, and one ``_format`` accepts but
    this set does not is a file the user cannot choose at all.
    """
    from sidecar_kuro.core import _ALLOWED_GENOME_EXTENSIONS

    classified = {}
    for suffix in _ALLOWED_GENOME_EXTENSIONS:
        classified[suffix] = cc._format(Path(f"genome{suffix}"), None)
    assert set(classified.values()) == {"fasta", "genbank"}

    # And the other direction: a suffix _format reads but core refuses would be
    # unreachable. .dna is deliberately in neither -- SnapGene is a design
    # template format and _format has no branch for it.
    with pytest.raises(cc.GenomeParseError):
        cc._format(Path("template.dna"), None)

