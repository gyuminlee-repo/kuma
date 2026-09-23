"""Tests for ``kuma_core.kuro.codon_compute``.

THE POINT OF THIS FILE IS THE KNOWN-ANSWER CONTROL, NOT THE UNIT TESTS.
A codon counter that is wrong is wrong quietly: it still emits 64 codons that
still sum to one per amino acid, and every structural assertion still passes.
So the load-bearing assertions here are the two that compare against numbers
this module did not produce.

**Known answer.** The design note measured *Methylorubrum extorquens* AM1 from
RefSeq ``GCF_000022685.1`` on 2026-09-09 with an independent script: 6,420 CDS
records, 164 of them pseudo, 6,256 counted, 1,930,715 codons, and a full
``counts`` block. ``tests/fixtures/codon_compute/mextorquens_am1.json`` is this
module's output on that same file, and its ``counts`` block is equal to the
note's, entry for entry, which was checked before the fixture was committed.
The provenance literals below are transcribed from the note, so they fail if
this module's tally drifts from that independent measurement.

**Discrimination.** A comparison that cannot fail proves nothing. The computed
*E. coli* K-12 table agrees with the bundled Kazusa ``ecoli.json`` on the most
frequent codon of all 21 amino acid groups; the AM1 table agrees on 9. The same
comparison, run the same way, separates a matching organism from a
non-matching one by 12 groups.

**Why fixtures rather than genomes.** The two source files are 4.9 MB and
7.2 MB and do not belong in the repository. The fixtures are this module's
*output* on them, a few kilobytes each, and the recomputation tests marked
``needs_genome`` rebuild them from the real files when the paths are given in
the environment:

    KUMA_TEST_AM1_CDS=/path/to/cds_from_genomic.fna \\
    KUMA_TEST_ECOLI_CDS=/path/to/cds_from_genomic.fna \\
    KUMA_TEST_ECOLI_GBFF=/path/to/genomic.gbff \\
    python3 -m pytest tests/test_codon_compute.py

Everything else -- the filters, the two input paths, the progress callback --
runs against a synthetic genome this file builds, because a filter needs an
input that trips it and RefSeq annotation is too clean to trip four of the
five.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord

from kuma_core.kuro import codon_compute as cc
from kuma_core.kuro.codon_import import (
    DEFAULT_GENETIC_CODE,
    canonical_digest,
    SUPPORTED_GENETIC_CODES,
    validate_codon_table_data,
)

FIXTURES = Path(__file__).parent / "fixtures" / "codon_compute"
BUNDLED = (
    Path(__file__).parent.parent
    / "kuma_core" / "kuro" / "resources" / "codon_tables"
)


# --- helpers ---------------------------------------------------------------


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _top_codons(codons: dict) -> dict[str, str]:
    """The most frequent codon of each amino acid group."""
    return {aa: max(pairs, key=lambda p: p[1])[0] for aa, pairs in codons.items()}


def _agreement(a: dict, b: dict) -> int:
    ta, tb = _top_codons(a), _top_codons(b)
    return sum(1 for aa in tb if ta.get(aa) == tb[aa])


# --- the synthetic genome --------------------------------------------------

# One codon per amino acid plus a stop. Every group has to be represented or
# the validator rejects the result under V24 ("every codon for X is zero"),
# which would mask whatever the test was actually checking.
_ALL_AA_CDS = (
    "GCT" "CGT" "AAT" "GAT" "TGT" "CAA" "GAA" "GGT" "CAT" "ATT"
    "CTT" "AAA" "ATG" "TTT" "CCT" "TCT" "ACT" "TGG" "TAT" "GTT" "TAA"
)
_JOIN_EXON1 = "ATGGCT"
_JOIN_EXON2 = "AAATTTGGGTAA"
_SPACER = "AAACCCGGGTTT"

# name -> (sequence, pseudo, expected exclusion reason or None)
_GENES: tuple[tuple[str, str, bool, str | None], ...] = (
    ("good_plus", _ALL_AA_CDS, False, None),
    ("good_minus", _ALL_AA_CDS, False, None),
    ("good_join", _JOIN_EXON1 + _JOIN_EXON2, False, None),
    ("drop_pseudo", "ATGGCTAAATAA", True, "pseudo"),
    ("drop_length", "ATGGCTAAATA", False, "not_multiple_of_3"),
    ("drop_internal", "ATGTAAATGTAA", False, "internal_stop"),
    ("drop_nostop", "ATGGCTAAAGGT", False, "no_terminal_stop"),
    ("drop_ambiguous", "ATGGCNAAATAA", False, "ambiguous_base"),
)


def _build_synthetic(tmp_path: Path) -> tuple[Path, Path]:
    """Write the same eight coding sequences as a GenBank file and a CDS FASTA.

    The two files are built from one list so they cannot drift apart. One gene
    sits on the minus strand and one is a two-exon ``join``, because those are
    the two things the GenBank path does that the FASTA path does not: if
    ``feature.extract`` were dropped, only these two would change.
    """
    genome = ""
    features = []
    for name, seq, pseudo, _ in _GENES:
        genome += _SPACER
        start = len(genome)
        if name == "good_minus":
            placed = str(Seq(seq).reverse_complement())
            genome += placed
            location = SimpleLocation(start, start + len(placed), strand=-1)
        elif name == "good_join":
            genome += _JOIN_EXON1
            mid = len(genome)
            genome += _SPACER
            second = len(genome)
            genome += _JOIN_EXON2
            location = CompoundLocation([
                SimpleLocation(start, mid, strand=1),
                SimpleLocation(second, second + len(_JOIN_EXON2), strand=1),
            ])
        else:
            genome += seq
            location = SimpleLocation(start, start + len(seq), strand=1)
        quals = {"locus_tag": [name]}
        if pseudo:
            quals["pseudo"] = [""]
        features.append(SeqFeature(location, type="CDS", qualifiers=quals))
    genome += _SPACER

    record = SeqRecord(
        Seq(genome), id="SYN000001.1", name="SYN000001",
        description="synthetic test genome", features=features,
        annotations={"molecule_type": "DNA"},
    )
    gbff = tmp_path / "synthetic.gbff"
    SeqIO.write([record], str(gbff), "genbank")

    fasta = tmp_path / "synthetic_cds.fna"
    lines = []
    for name, seq, pseudo, _ in _GENES:
        tag = " [pseudo=true]" if pseudo else ""
        lines.append(f">lcl|SYN000001.1_cds_{name} [locus_tag={name}]{tag}")
        lines.append(seq)
    fasta.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return gbff, fasta


# --- the genetic code is the caller's ---------------------------------------


@pytest.mark.parametrize("code", [4, 2, 25, 0, -1, "11", 11.0, None, True])
def test_unsupported_genetic_code_is_refused(tmp_path, code):
    """Mycoplasma and friends are refused by name, not counted under code 11."""
    _, fasta = _build_synthetic(tmp_path)
    with pytest.raises(cc.UnsupportedGeneticCodeError) as exc:
        cc.compute_codon_table(fasta, key="syn", name="Synthetic",
                               genetic_code=code)
    assert str(code) in str(exc.value) or repr(code) in str(exc.value)


@pytest.mark.parametrize("code", SUPPORTED_GENETIC_CODES)
def test_declared_code_is_written_out_verbatim(tmp_path, code):
    """The caller's code reaches the file unchanged.

    Codes 1 and 11 share ``forward_table`` and ``stop_codons`` and differ only
    in start codons, so the counts below are identical and no codon-level rule
    can tell them apart. That is exactly why the declared value must not be
    rewritten: nothing downstream would catch it, and the number lands in the
    canonical digest.
    """
    _, fasta = _build_synthetic(tmp_path)
    result = cc.compute_codon_table(fasta, key="syn", name="Synthetic",
                                    genetic_code=code)
    assert result.document["genetic_code"] == code


def test_codes_1_and_11_produce_the_same_counts(tmp_path):
    _, fasta = _build_synthetic(tmp_path)
    one = cc.compute_codon_table(fasta, key="syn", name="S", genetic_code=1)
    eleven = cc.compute_codon_table(fasta, key="syn", name="S", genetic_code=11)
    assert one.document["counts"] == eleven.document["counts"]
    assert one.document["genetic_code"] != eleven.document["genetic_code"]


def test_default_code_is_the_shared_constant(tmp_path):
    _, fasta = _build_synthetic(tmp_path)
    result = cc.compute_codon_table(fasta, key="syn", name="Synthetic")
    assert result.document["genetic_code"] == DEFAULT_GENETIC_CODE == 11


# --- the filters -----------------------------------------------------------


@pytest.mark.parametrize("fmt", ["fasta", "genbank"])
def test_every_exclusion_reason_fires_exactly_once(tmp_path, fmt):
    gbff, fasta = _build_synthetic(tmp_path)
    result = cc.compute_codon_table(
        gbff if fmt == "genbank" else fasta, key="syn", name="Synthetic"
    )
    assert result.cds_total == len(_GENES)
    assert result.cds_counted == 3
    assert result.cds_excluded == {r: 1 for r in cc.EXCLUSION_REASONS}
    assert set(result.cds_excluded) == set(cc.EXCLUSION_REASONS)


def test_the_two_input_paths_agree(tmp_path):
    """A GenBank file and a CDS FASTA of the same genes give the same table.

    Each parser passing its own test and the two parsers producing the same
    table are different propositions. This asserts the second one, which is
    what makes the minus-strand gene and the ``join`` gene meaningful.
    """
    gbff, fasta = _build_synthetic(tmp_path)
    from_gb = cc.compute_codon_table(gbff, key="syn", name="Synthetic")
    from_fa = cc.compute_codon_table(fasta, key="syn", name="Synthetic")
    assert from_gb.document["counts"] == from_fa.document["counts"]
    assert from_gb.codon_count == from_fa.codon_count
    assert from_gb.cds_excluded == from_fa.cds_excluded


def test_excluded_examples_name_the_records(tmp_path):
    _, fasta = _build_synthetic(tmp_path)
    result = cc.compute_codon_table(fasta, key="syn", name="Synthetic")
    for reason in cc.EXCLUSION_REASONS:
        assert result.excluded_examples[reason], reason


def test_counted_codons_add_up(tmp_path):
    """``codon_count`` is the sum of the counts block, stops included."""
    _, fasta = _build_synthetic(tmp_path)
    result = cc.compute_codon_table(fasta, key="syn", name="Synthetic")
    total = sum(v for pairs in result.document["counts"].values()
                for _, v in pairs)
    assert total == result.codon_count
    stops = sum(v for _, v in result.document["counts"]["*"])
    assert stops == result.cds_counted


def test_all_64_codons_are_emitted_even_at_zero(tmp_path):
    """V18 wants all 64 codons exactly once, whether or not the genome used them."""
    _, fasta = _build_synthetic(tmp_path)
    result = cc.compute_codon_table(fasta, key="syn", name="Synthetic")
    flat = [c for pairs in result.document["counts"].values() for c, _ in pairs]
    assert len(flat) == 64
    assert len(set(flat)) == 64
    assert any(v == 0 for pairs in result.document["counts"].values()
               for _, v in pairs)


# --- progress --------------------------------------------------------------


def test_progress_callback_is_monotonic_and_finishes_at_the_total(tmp_path):
    _, fasta = _build_synthetic(tmp_path)
    seen: list[tuple[int, int | None]] = []
    result = cc.compute_codon_table(
        fasta, key="syn", name="Synthetic",
        on_progress=lambda done, total: seen.append((done, total)),
    )
    assert seen, "the callback was never called"
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)
    assert seen[-1][0] == result.cds_total
    # The FASTA path counts records before it counts codons, so it can offer a
    # denominator. The GenBank path cannot without parsing twice.
    assert seen[-1][1] == result.cds_total


def test_progress_is_optional(tmp_path):
    _, fasta = _build_synthetic(tmp_path)
    assert cc.compute_codon_table(fasta, key="syn", name="S").cds_total == 8


# --- input errors ----------------------------------------------------------


def test_unknown_suffix_is_refused(tmp_path):
    path = tmp_path / "genome.txt"
    path.write_text(">x\nATGTAA\n", encoding="utf-8")
    with pytest.raises(cc.GenomeParseError):
        cc.compute_codon_table(path, key="syn", name="S")
    result = cc.compute_codon_table(path, key="syn", name="S",
                                    genome_format="fasta")
    assert result.cds_total == 1


def test_missing_file_is_refused(tmp_path):
    with pytest.raises(cc.GenomeParseError):
        cc.compute_codon_table(tmp_path / "nope.fna", key="syn", name="S")


def test_genbank_without_sequence_says_so(tmp_path):
    """A CONTIG-only GenBank file names the problem instead of raising from Bio."""
    gbff, _ = _build_synthetic(tmp_path)
    text = gbff.read_text(encoding="utf-8")
    head, _, _ = text.partition("ORIGIN")
    stripped = tmp_path / "noseq.gbff"
    stripped.write_text(head + "CONTIG      join(SYN000001.1:1..1000)\n//\n",
                        encoding="utf-8")
    with pytest.raises(cc.GenomeParseError) as exc:
        cc.compute_codon_table(stripped, key="syn", name="S")
    assert "sequence" in str(exc.value).lower()


# --- the output is a table the importer accepts -----------------------------


@pytest.mark.parametrize("stem", ["mextorquens_am1", "ecoli_k12_mg1655"])
def test_computed_table_passes_the_importer(stem):
    """The whole point of the schema: a computed table imports with 0 errors.

    Warnings are allowed; V34 (a codon at frequency zero) is expected on a
    real genome and is information, not a fault.
    """
    report = validate_codon_table_data(_load(stem), stem=stem)
    assert report.errors == [], report.error_codes
    assert report.ok
    assert report.codons_examined == 64
    assert report.table_sha256


@pytest.mark.parametrize("stem", ["mextorquens_am1", "ecoli_k12_mg1655"])
def test_stored_fractions_match_their_own_counts(stem):
    """V27 is the hand-edit detector; a computed file must never trip it."""
    report = validate_codon_table_data(_load(stem), stem=stem)
    assert "V27" not in report.error_codes


@pytest.mark.parametrize("stem", ["mextorquens_am1", "ecoli_k12_mg1655"])
def test_the_stored_fractions_are_the_ones_the_importer_will_digest(stem):
    """The digest of the file as written equals the digest kuma computes on load.

    ``_check_counts`` N4 treats counts as authoritative and replaces every
    stored fraction with ``count / group total`` before ``canonical_digest``
    runs, so a file whose fractions were rounded on the way out hashes to one
    value on paper and another inside kuma. That is not hypothetical: the
    design note's own section 3.2 file declares
    ``07a30a7af3317e14bf4ca5e45054dc32f297d437fe8a73e0243036a1de522ce6``,
    which is the digest of its three-decimal codons block, while the importer
    returns ``511945235fcfb0507a11e497a7321e2ea1c21a4c646ecaba99a7923236495d84``
    for the same file. Writing fractions unrounded is what closes that gap, and
    the workspace digest comparison of section 8 depends on it being closed.
    """
    document = _load(stem)
    stored = canonical_digest(
        {aa: [tuple(pair) for pair in pairs]
         for aa, pairs in document["codons"].items()},
        document["genetic_code"],
    )
    report = validate_codon_table_data(document, stem=stem)
    assert stored == report.table_sha256


def test_computed_table_is_refused_when_it_declares_an_unsupported_code():
    """The refusal lives in both modules, and they agree on the list."""
    data = _load("ecoli_k12_mg1655")
    data["genetic_code"] = 4
    report = validate_codon_table_data(data, stem="ecoli_k12_mg1655")
    assert "V15" in report.error_codes


# --- known answer ----------------------------------------------------------


def test_am1_matches_the_independently_measured_tally():
    """Transcribed from design note section 3.2, measured 2026-09-09."""
    prov = _load("mextorquens_am1")["provenance"]
    assert prov["cds_total"] == 6420
    assert prov["cds_counted"] == 6256
    assert prov["codon_count"] == 1930715
    assert prov["cds_excluded"] == {
        "pseudo": 164, "not_multiple_of_3": 0, "internal_stop": 0,
        "no_terminal_stop": 0, "ambiguous_base": 0,
    }
    assert prov["source_sha256"] == (
        "1d94ed29351b7d1e529956e30dc91f278b44731c0ebf1c8ee2ccb9b7d8233011"
    )
    counts = _load("mextorquens_am1")["counts"]
    # Four rows of the note's block, one per magnitude, verbatim.
    assert counts["A"] == [["GCC", 136595], ["GCG", 104287],
                           ["GCT", 13316], ["GCA", 13027]]
    assert counts["M"] == [["ATG", 37776]]
    assert counts["L"][0] == ["CTC", 87117]
    assert counts["*"] == [["TGA", 4631], ["TAG", 982], ["TAA", 643]]


def test_ecoli_tally_is_what_the_refseq_file_holds():
    prov = _load("ecoli_k12_mg1655")["provenance"]
    assert prov["cds_total"] == 4318
    assert prov["cds_counted"] == 4297
    assert prov["codon_count"] == 1331587
    # The three internal stops are fdnG, fdoG and fdhF, the K-12
    # selenoproteins, whose in-frame TGA is read as Sec only through a
    # /transl_except this module deliberately does not honour. A tally that
    # reported zero here would be counting a Sec codon as a stop.
    assert prov["cds_excluded"]["internal_stop"] == 3
    assert prov["cds_excluded"]["pseudo"] == 18


def test_computed_ecoli_agrees_with_the_bundled_table():
    """Rank agreement, not byte agreement: the bundled table is Kazusa's.

    Measured 2026-09-23: 21 of 21 amino acid groups pick the same most
    frequent codon. The floor is set below the measurement so a change in the
    bundled file's tail does not fail this, but the signal stays far above the
    non-matching organism below.
    """
    computed = _load("ecoli_k12_mg1655")["codons"]
    bundled = json.loads(
        (BUNDLED / "ecoli.json").read_text(encoding="utf-8")
    )["codons"]
    assert _agreement(computed, bundled) >= 19


def test_the_same_comparison_separates_a_different_organism():
    """Discrimination. Without this the test above could pass on any input.

    Measured 2026-09-23: AM1 against the bundled E. coli table agrees on 9 of
    21 groups, against 21 of 21 for the matching organism.
    """
    am1 = _load("mextorquens_am1")["codons"]
    bundled = json.loads(
        (BUNDLED / "ecoli.json").read_text(encoding="utf-8")
    )["codons"]
    agreement = _agreement(am1, bundled)
    assert agreement <= 13
    computed = _load("ecoli_k12_mg1655")["codons"]
    assert _agreement(computed, bundled) - agreement >= 6


# --- recomputation from the real genomes -----------------------------------


def _genome(var: str) -> Path:
    path = os.environ.get(var)
    if not path or not Path(path).is_file():
        pytest.skip(f"set {var} to the genome file to run this check")
    return Path(path)


def _recompute(path: Path, stem: str, fmt: str | None = None) -> dict:
    expected = _load(stem)
    prov = expected["provenance"]
    return cc.compute_codon_table(
        path,
        key=expected["key"],
        name=expected["name"],
        taxid=expected["taxid"],
        genetic_code=expected["genetic_code"],
        genome_format=fmt,
        aliases=expected["aliases"],
        source=expected["source"],
        source_file=prov["source_file"],
        generated_at=prov["generated_at"],
    ).document


def test_am1_fixture_is_reproducible_from_the_genome():
    path = _genome("KUMA_TEST_AM1_CDS")
    assert _recompute(path, "mextorquens_am1") == _load("mextorquens_am1")


def test_ecoli_fixture_is_reproducible_from_the_genome():
    path = _genome("KUMA_TEST_ECOLI_CDS")
    assert _recompute(path, "ecoli_k12_mg1655") == _load("ecoli_k12_mg1655")


def test_ecoli_genbank_and_fasta_agree_on_the_real_genome():
    """The synthetic two-path check, repeated on 4,318 real coding sequences."""
    gbff = _genome("KUMA_TEST_ECOLI_GBFF")
    expected = _load("ecoli_k12_mg1655")
    from_gb = cc.compute_codon_table(
        gbff, key=expected["key"], name=expected["name"],
        genetic_code=expected["genetic_code"],
    )
    assert from_gb.document["counts"] == expected["counts"]
    assert from_gb.cds_excluded == expected["provenance"]["cds_excluded"]
