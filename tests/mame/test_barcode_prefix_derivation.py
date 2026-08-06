# ruff: noqa: S101
"""The barcode seed has to come back out of the file that stated it.

``load_barcode_prefixes`` used to cut the seed at the ispS annealing tail, held
as a module constant, and fall back to a fixed 11 bp (F) / 10 bp (R) when that
constant was absent. Every workbook ``barcode_package`` generates falls in the
second case, because it designs a fresh flanking primer per gene, so the ispS
tail is not in the file at all.

Both fallbacks are now gone: a workbook that does not state where its seeds end
is refused rather than read at an assumed length, because the assumed length is
wrong for every campaign except the one it was copied from, the reverse axis is
the plate row, and the resulting mis-named wells look exactly like correct ones.
The tests below therefore come in two halves: what derivation recovers, and what
the reader now refuses to do instead of guessing.

The fixtures are built so the old rule and the new one DISAGREE. A fixture where
both answer the same is worth nothing here: the seed lengths are 9 bp forward
and 13 bp reverse precisely because neither is the old fallback length, and the
tails are 18 bp of sequence that is not the ispS tail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.ingest.combinatorial_demux import (
    load_barcode_prefixes,
    load_barcode_prefixes_with_provenance,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

#: The ispS constants, spelled out here so a test can say "not this".
_ISPS_F_TAIL = "CACAGGAGGTTAAACC"  # 16 bp
_ISPS_R_TAIL = "TGCGTTGCGCTCTAG"  # 15 bp

#: A gene that is not ispS: 18 bp flanking primers sharing nothing with the
#: constants above, which is what primer3 hands ``barcode_package`` for any
#: other target.
_GENE_F_TAIL = "GGTTCAGACGTATCCTGA"  # 18 bp
_GENE_R_TAIL = "AACCTGGTATCGAGCTTA"  # 18 bp

#: Seed lengths chosen to be neither fallback length (11 F / 10 R), so a seed cut
#: at a fixed length is visibly the wrong string rather than a lucky match.
_GENE_F_SEEDS = [
    "AACGTTCAG",  # 9 bp
    "TTGCAACGT",
    "CGATTGCAA",
    "GCTAACGTT",
    "TACGGTTCA",
    "ATCCGTTAG",
    "CCATGGATC",
    "GGTACCTAG",
    "TGACCAGTT",
    "AGTCCTGAA",
    "CTGAAGGTC",
    "GACTTCCAG",
]
#: R1 and R2 deliberately share their first 10 bases and differ only in the
#: last 3. A seed cut at the fixed 10 bp turns them into the same string, which
#: the matcher then drops as ambiguous, so the end-to-end test below can tell
#: the two rules apart by counting wells rather than by inspecting strings.
_GENE_R_SEEDS = [
    "AACCGGTTACGAT",  # 13 bp
    "AACCGGTTACTCA",  # same first 10 bases as R1
    "CGGATCCATTAGC",
    "GCCTAGGTAACGT",
    "TACCGGATCCAAG",
    "ATGCCATGGTTCA",
    "CCGGTTAACCGAT",
    "GGCCAATTGGCTA",
]

#: The ispS plate as the workbook stores it, used for the regression fixture.
_ISPS_F_SEEDS = [
    "AATCCCACTAC", "TGAACTGAGCG", "TATCTGACCTT", "ATATGAGACG", "CGCTCATTAG",
    "TAATCTCGTC", "GCGCGATTTT", "AGAGCACTAG", "TGCCTTGATC", "CTACTCAGTC",
    "TCGTCTGACT", "GAACATACGG",
]
_ISPS_R_SEEDS = [
    "CCCTATGACA", "TAATGGCAAG", "AACAAGGCGT", "GTATGTAGAA", "TTCTATGGGG",
    "CCTCGCAACC", "TGGATGCTTA", "AGAGTGCGGC",
]


_ALPHABET = "ACGT"


def _unshared_sequence(index: int, length: int = 24) -> str:
    """A 24 bp primer that shares no suffix with any other index.

    The last two bases spell the index in base 4, so no two sequences in a set
    of 16 or fewer end alike and the longest common suffix of the set is 0 bp.
    """
    body = "".join(_ALPHABET[(index + position) % 4] for position in range(length - 2))
    return body + _ALPHABET[index % 4] + _ALPHABET[(index // 4) % 4]


def _write_barcodes(
    dest: Path,
    prefix: str,
    f_sequences: list[str],
    r_sequences: list[str],
) -> Path:
    """Write a barcode workbook: column A the row name, column B the primer."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for i, seq in enumerate(f_sequences, start=1):
        ws.append([f"{prefix}_f_{i}", seq])
    for i, seq in enumerate(r_sequences, start=1):
        ws.append([f"{prefix}_r_{i}", seq])
    wb.save(dest)
    return dest


@pytest.fixture()
def gene_barcodes_xlsx(tmp_path: Path) -> Path:
    """A kuma-generated package shape: per-gene tails, 9 bp / 13 bp seeds."""
    return _write_barcodes(
        tmp_path / "gene_barcodes.xlsx",
        "mygene",
        [seed + _GENE_F_TAIL.lower() for seed in _GENE_F_SEEDS],
        [seed + _GENE_R_TAIL.lower() for seed in _GENE_R_SEEDS],
    )


@pytest.fixture()
def isps_barcodes_xlsx(tmp_path: Path) -> Path:
    """The ispS shape: seed uppercase, annealing tail lowercase."""
    return _write_barcodes(
        tmp_path / "isps_barcodes.xlsx",
        "isps",
        [seed + _ISPS_F_TAIL.lower() for seed in _ISPS_F_SEEDS],
        [seed + _ISPS_R_TAIL.lower() for seed in _ISPS_R_SEEDS],
    )


@pytest.fixture()
def unshared_barcodes_xlsx(tmp_path: Path) -> Path:
    """Primers sharing no suffix at all, the shape the sample workbook has.

    ``src-tauri/samples/mame/04_mame_custom_barcodes.xlsx`` is exactly this:
    24 bp sequences whose common suffix is 0 bp on both axes. Nothing can be
    derived from it and nothing can be found in it, so it is what drives the
    fixed-length path.
    """
    return _write_barcodes(
        tmp_path / "unshared_barcodes.xlsx",
        "odd",
        [_unshared_sequence(i) for i in range(12)],
        [_unshared_sequence(i) for i in range(8)],
    )


# ---------------------------------------------------------------------------
# (a) The derived path, on a file the constants cannot read
# ---------------------------------------------------------------------------


def test_derived_tail_recovers_non_isps_seeds_exactly(
    gene_barcodes_xlsx: Path,
) -> None:
    resolution = load_barcode_prefixes_with_provenance(gene_barcodes_xlsx)

    assert resolution.forward.tail == _GENE_F_TAIL
    assert resolution.reverse.tail == _GENE_R_TAIL

    assert [seed for _, seed in resolution.forward.barcodes] == _GENE_F_SEEDS
    assert [seed for _, seed in resolution.reverse.barcodes] == _GENE_R_SEEDS


def test_fixed_length_rule_returns_the_wrong_seeds_on_the_same_file(
    gene_barcodes_xlsx: Path,
) -> None:
    """What the pre-derivation rule would answer on the fixture above.

    Stated on the same file as the test before it, because a fixture where both
    rules agree proves nothing about which one is in force. The forward axis is
    off by two bases of annealing tail kept, the reverse axis by three bases of
    seed lost, and the reverse axis is the plate row.

    The old rule is spelled out here as the literal slice it was rather than
    called, because ``_extract_f_prefix`` / ``_extract_r_prefix`` are deleted
    along with the fallback. What is asserted, though, is the READER's answer
    against that slice, row by row: an assertion between two test-local
    constants would pass with the module deleted and would pin nothing.
    """
    resolution = load_barcode_prefixes_with_provenance(gene_barcodes_xlsx)

    forward = [seed for _, seed in resolution.forward.barcodes]
    reverse = [seed for _, seed in resolution.reverse.barcodes]
    f_sequences = [seed + _GENE_F_TAIL.lower() for seed in _GENE_F_SEEDS]
    r_sequences = [seed + _GENE_R_TAIL.lower() for seed in _GENE_R_SEEDS]

    # 11 bp (F) and 10 bp (R) were the old fallback lengths. Every row the
    # reader returns differs from what that cut would have produced.
    assert all(
        seed != sequence[:11].upper()
        for seed, sequence in zip(forward, f_sequences, strict=True)
    )
    assert all(
        seed != sequence[:10].upper()
        for seed, sequence in zip(reverse, r_sequences, strict=True)
    )
    # And specifically: the fixed F cut keeps two bases of annealing tail, the
    # fixed R cut throws away three bases of seed.
    assert f_sequences[0][:11].upper() == forward[0] + _GENE_F_TAIL[:2]
    assert r_sequences[0][:10].upper() == reverse[0][:10]
    assert len(reverse[0]) == 13


def test_gene_file_carries_neither_isps_tail(gene_barcodes_xlsx: Path) -> None:
    """The fixture is only meaningful if the constants genuinely cannot match."""
    resolution = load_barcode_prefixes_with_provenance(gene_barcodes_xlsx)
    for _, seed in resolution.forward.barcodes:
        assert _ISPS_F_TAIL not in seed
    assert _ISPS_F_TAIL not in _GENE_F_TAIL
    assert _ISPS_R_TAIL not in _GENE_R_TAIL


def test_load_barcode_prefixes_returns_the_derived_seeds(
    gene_barcodes_xlsx: Path,
) -> None:
    """The two-list entry point is the same work, unchanged signature."""
    r_barcodes, f_barcodes = load_barcode_prefixes(gene_barcodes_xlsx)

    assert [seed for _, seed in f_barcodes] == _GENE_F_SEEDS
    assert [seed for _, seed in r_barcodes] == _GENE_R_SEEDS
    assert [name for name, _ in f_barcodes] == [f"mygene_f_{i}" for i in range(1, 13)]
    assert [name for name, _ in r_barcodes] == [f"mygene_r_{i}" for i in range(1, 9)]


# ---------------------------------------------------------------------------
# (a) on the ispS file: derivation must reproduce the constants exactly
# ---------------------------------------------------------------------------


def test_derived_tail_reproduces_the_isps_constants(
    isps_barcodes_xlsx: Path,
) -> None:
    """Deriving the tail is behaviour-preserving for every ispS-era file.

    The whole change rests on this, and now doubly so: the ispS constants have
    been deleted along with the fallback that used them, so if derivation did
    not reproduce them exactly there would be nothing left to read those files
    with. The longest common suffix of the ispS forward column is the 16 bp
    constant and of the reverse column the 15 bp one, to the base, so files that
    were read by the constants are read identically now and killing the fallback
    costs the legacy campaign nothing.
    """
    resolution = load_barcode_prefixes_with_provenance(isps_barcodes_xlsx)

    assert resolution.forward.tail == "CACAGGAGGTTAAACC"
    assert len(resolution.forward.tail) == 16
    assert resolution.reverse.tail == "TGCGTTGCGCTCTAG"
    assert len(resolution.reverse.tail) == 15

    assert [seed for _, seed in resolution.forward.barcodes] == _ISPS_F_SEEDS
    assert [seed for _, seed in resolution.reverse.barcodes] == _ISPS_R_SEEDS
    # F1-F3 carry an extra 5' base; every R seed is 10 bp.
    assert list(resolution.forward.seed_lengths) == [
        11, 11, 11, 10, 10, 10, 10, 10, 10, 10, 10, 10
    ]
    assert set(resolution.reverse.seed_lengths) == {10}

    # The provenance says what was derived, and says it in the terms an operator
    # can check against the seed workbook they ordered primers from.
    payload = resolution.as_dict()
    assert payload["forward"]["tail_length"] == 16
    assert payload["forward"]["barcode_count"] == 12
    assert payload["reverse"]["seed_lengths"] == [10] * 8
    assert "CACAGGAGGTTAAACC" in payload["note"]
    assert "10-11 bp" in payload["note"]
    # The one thing the sentence must not do is overclaim: a common suffix can
    # run past the annealing region, and the note has to admit that.
    assert "unless the seeds themselves also end alike" in payload["note"]


def test_isps_file_reads_the_same_through_both_entry_points(
    isps_barcodes_xlsx: Path,
) -> None:
    r_barcodes, f_barcodes = load_barcode_prefixes(isps_barcodes_xlsx)
    assert f_barcodes[0] == ("isps_f_1", "AATCCCACTAC")
    assert r_barcodes[0] == ("isps_r_1", "CCCTATGACA")


# ---------------------------------------------------------------------------
# The refusals. Each of these used to be a fallback that PROCEEDED, and the
# assertions below are the inverted form of the tests that pinned that: what
# was "the path is taken and labelled" is now "the path does not exist".
# ---------------------------------------------------------------------------


def test_the_isps_constants_no_longer_rescue_a_file_with_no_derivable_tail(
    tmp_path: Path,
) -> None:
    """Was: the built-in ispS tail reads this file. Now: nothing does.

    Nothing shared sits at the end of these sequences (a variable 3' end hides
    the annealing region), so derivation declines. The ispS constant is still
    inside every row, and the old reader found it there and carried on. That
    rescue is deleted: a constant naming one campaign cannot be the rule for a
    file format, and a file that needs it is a file whose next revision the
    reader would silently mis-cut.
    """
    variable_ends = ["AA", "CC", "GG", "TT", "AC", "AG", "AT", "CA", "CG", "CT", "GA", "GC"]
    path = _write_barcodes(
        tmp_path / "legacy.xlsx",
        "isps",
        [
            seed + _ISPS_F_TAIL.lower() + variable_ends[i]
            for i, seed in enumerate(_ISPS_F_SEEDS)
        ],
        [
            seed + _ISPS_R_TAIL.lower() + variable_ends[i]
            for i, seed in enumerate(_ISPS_R_SEEDS)
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        load_barcode_prefixes_with_provenance(path)

    message = str(excinfo.value)
    assert "legacy.xlsx" in message
    assert "forward" in message
    assert "Read 12 forward rows" in message  # how many rows were read
    assert "12 bp" in message  # the floor it fell short of
    assert "Re-export" in message  # what to do about it


def test_a_file_with_no_shared_suffix_is_refused_not_cut_at_a_fixed_length(
    unshared_barcodes_xlsx: Path,
) -> None:
    """Was: every seed is an 11 bp / 10 bp guess, reported. Now: refused.

    This is the shape the shipped sample workbook used to have: no common suffix
    on either axis (0 bp) and no ispS tail either. Reporting the guess was not
    enough, because the run still finished and still named wells, and a report
    on a response nobody reads is indistinguishable from silence for the person
    holding the plate.
    """
    with pytest.raises(ValueError) as excinfo:
        load_barcode_prefixes_with_provenance(unshared_barcodes_xlsx)

    message = str(excinfo.value)
    assert "unshared_barcodes.xlsx" in message
    assert "share to their 3' end is 0 bp" in message
    assert "Read 12 forward rows of 24-24 bp" in message
    # The old fallback lengths must not appear as an offer of any kind.
    assert "11 bp" not in message
    assert "plate row" in message  # why it matters, not just that it failed


def test_load_barcode_prefixes_refuses_the_same_file(
    unshared_barcodes_xlsx: Path,
) -> None:
    """Both entry points refuse; the two-list view is not a way around it."""
    with pytest.raises(ValueError, match="does not state where its"):
        load_barcode_prefixes(unshared_barcodes_xlsx)


def test_an_axis_only_some_of_whose_rows_carry_the_tail_is_refused(
    tmp_path: Path,
) -> None:
    """Was: the axis proceeds, with the odd row marked as guessed. Now: refused.

    A single primer carrying a different annealing region makes the axis
    internally inconsistent, and an inconsistent axis has no seed rule at all.
    Marking one row while cutting it at an assumed length still produced a plate
    with one well named from a truncated seed.

    The message has to NAME that row. Matching only on "forward barcode seeds
    end" would pass on the unshared-suffix file too, so this test would not be
    telling the two apart: one row out of twelve is a cell to fix, and twelve
    rows that agree on nothing is a file to re-export. The assertions below
    pin that distinction from both sides.
    """
    f_sequences = [seed + _ISPS_F_TAIL.lower() for seed in _ISPS_F_SEEDS]
    # One forward primer carries a different annealing region entirely. The
    # reverse axis is left intact so the forward axis is the only thing wrong.
    f_sequences[4] = _ISPS_F_SEEDS[4] + _GENE_F_TAIL.lower()
    path = _write_barcodes(
        tmp_path / "mixed.xlsx",
        "isps",
        f_sequences,
        [seed + _ISPS_R_TAIL.lower() for seed in _ISPS_R_SEEDS],
    )

    with pytest.raises(ValueError) as excinfo:
        load_barcode_prefixes_with_provenance(path)

    message = str(excinfo.value)
    assert "forward barcode seeds end" in message
    # The row, by name. This is the whole difference between this refusal and
    # the one above it: eleven cells are fine and one is not.
    assert "the ones that end differently are isps_f_5" in message
    assert "The other 11 rows do share 16 bp" in message
    # And the remedy has to be the one that fits: fixing a cell, not throwing
    # away seeds the primers were already ordered against.
    assert "correct those cells" in message
    for index in (1, 2, 3, 4, 6):
        assert f"isps_f_{index}" not in message


def test_a_file_with_no_majority_names_no_rows(
    unshared_barcodes_xlsx: Path,
) -> None:
    """The other side of the test above: no majority, so no row is named.

    Twelve rows that agree with nothing have no reference for one of them to be
    odd against, and naming a subset would be picking a side. So the message
    stays at file level and keeps the re-export remedy, which is the right one
    when the file really is the wrong shape.
    """
    with pytest.raises(ValueError) as excinfo:
        load_barcode_prefixes_with_provenance(unshared_barcodes_xlsx)

    message = str(excinfo.value)
    assert "the ones that end differently are" not in message
    assert "Re-export the workbook" in message


def test_an_axis_of_one_row_is_refused_and_says_why(tmp_path: Path) -> None:
    """A known and accepted consequence of deriving the tail from the file.

    One sequence shares nothing with anything, so a workbook carrying a single
    forward primer states no rule and is refused. That is a real narrowing
    against the deleted constant search, which could still find the ispS tail
    inside a lone row, and it is kept deliberately: the derived rule is the only
    one that survives a change of campaign, and a length recovered from a
    constant is a length this file did not state.

    It is not reachable from a package kuma writes.
    ``barcode_package.parse_barcode_seeds`` refuses any seed workbook that is
    not 12 forward and 8 reverse, so a one-row axis can only be hand-trimmed,
    which is exactly the input the fixed-length cut used to guess at. What the
    refusal owes the operator is a sentence that says so, which is what this
    pins.
    """
    path = _write_barcodes(
        tmp_path / "one_forward.xlsx",
        "mygene",
        [_GENE_F_SEEDS[0] + _GENE_F_TAIL.lower()],
        [seed + _GENE_R_TAIL.lower() for seed in _GENE_R_SEEDS],
    )

    with pytest.raises(ValueError) as excinfo:
        load_barcode_prefixes_with_provenance(path)

    message = str(excinfo.value)
    assert "Read 1 forward row" in message
    assert "at least two rows" in message
    assert "12 forward and 8 reverse" in message


def test_an_empty_axis_is_refused(tmp_path: Path) -> None:
    """Was: the reverse axis reports ``no_rows`` and the run continues. Now: refused.

    A plate with no rows is not a plate. The refusal names the row-naming rule,
    because "carries no reverse barcode rows" is usually a misspelled prefix
    rather than a missing half of the design.
    """
    path = _write_barcodes(
        tmp_path / "forward_only.xlsx",
        "mygene",
        [seed + _GENE_F_TAIL.lower() for seed in _GENE_F_SEEDS],
        [],
    )

    with pytest.raises(ValueError) as excinfo:
        load_barcode_prefixes_with_provenance(path)

    message = str(excinfo.value)
    assert "no reverse barcode rows" in message
    assert "<prefix>_r_<n>" in message


# ---------------------------------------------------------------------------
# The derived path has to be able to decline too
# ---------------------------------------------------------------------------


def test_derivation_declines_when_it_would_leave_a_stub_seed(tmp_path: Path) -> None:
    """A common suffix has no upper bound, so it can eat the seeds.

    Primers designed under a shared 3' constraint end alike, and then the longest
    common suffix runs past the annealing region into the seed. An even overcut
    of a base or two still leaves the seeds mutually distinguishable, but a
    suffix that leaves two bases in front of it is not a rule the file stated,
    so the file is refused. The message has to separate this case from "shares
    too little", because the remedy is the opposite one.
    """
    # 15 bp sequences sharing their last 12: derivation would leave 3 bp seeds.
    shared = "GTCAGTCAGTCA"  # 12 bp, at the MIN_TAIL_LENGTH floor
    path = _write_barcodes(
        tmp_path / "stub_seeds.xlsx",
        "stub",
        [_GENE_F_SEEDS[i][:3] + shared for i in range(12)],
        [_GENE_R_SEEDS[i][:3] + shared for i in range(8)],
    )

    with pytest.raises(ValueError) as excinfo:
        load_barcode_prefixes_with_provenance(path)

    message = str(excinfo.value)
    assert "sharing 12 bp to their 3' end" in message
    assert "leaves 3 bp of seed" in message
    assert "under the 5 bp minimum" in message


def test_derivation_accepts_a_seed_at_the_floor(tmp_path: Path) -> None:
    """The floor is the length ``barcode_package`` itself will write.

    Stated next to the test above so the boundary is pinned from both sides: a
    5 bp seed is a legal package, and refusing it would send a correct file down
    the fallback path.
    """
    shared = "GTCAGTCAGTCA"  # 12 bp
    path = _write_barcodes(
        tmp_path / "floor_seeds.xlsx",
        "floor",
        [_GENE_F_SEEDS[i][:5] + shared for i in range(12)],
        [_GENE_R_SEEDS[i][:5] + shared for i in range(8)],
    )

    resolution = load_barcode_prefixes_with_provenance(path)

    assert resolution.forward.tail == shared
    assert set(resolution.forward.seed_lengths) == {5}


# ---------------------------------------------------------------------------
# The workbooks kuma ships have to survive its own reader
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "src-tauri/samples/mame/04_mame_custom_barcodes.xlsx",
        "templates/04_mame_custom_barcodes.xlsx",
    ],
)
def test_the_shipped_sample_workbook_states_its_own_tail(relative: str) -> None:
    """The demo data must not be data the product refuses.

    Both files used to hold 24 bp primers with a 0 bp common suffix, and loaded
    only because of the fixed-length fallback. They are regenerated by
    ``python-core/scripts/regen_mame_sample_barcodes.py`` from
    ``egfp_with_flanks.fa`` plus ``02_mame_barcode_seeds.xlsx``, and this test is
    what catches it if either one loses that shape again: the seeds it hands
    back are checked against the seed workbook they were designed from, not just
    against a length.
    """
    from kuma_core.mame.ingest.barcode_package import parse_barcode_seeds

    repo_root = Path(__file__).resolve().parents[2]
    workbook = repo_root / relative
    seeds_workbook = repo_root / "src-tauri/samples/mame/02_mame_barcode_seeds.xlsx"

    resolution = load_barcode_prefixes_with_provenance(workbook)
    expected = parse_barcode_seeds(seeds_workbook)

    assert len(resolution.forward.tail) >= 12
    assert len(resolution.reverse.tail) >= 12
    assert len(resolution.forward.barcodes) == 12
    assert len(resolution.reverse.barcodes) == 8

    recovered = [seed for _, seed in resolution.forward.barcodes]
    recovered += [seed for _, seed in resolution.reverse.barcodes]
    wanted = [expected[f"fwd_{i}"].upper() for i in range(1, 13)]
    wanted += [expected[f"rev_{i}"].upper() for i in range(1, 9)]
    assert recovered == wanted


def test_the_demo_reference_and_the_demo_barcodes_yield_an_amplicon(
    tmp_path: Path,
) -> None:
    """The shipped demo pair has to reach the SUCCESS path, not just a valid one.

    ``loadSampleData`` (``src/store/mame/slices/analysisSlice.ts``) hands the
    analyze step ``egfp_with_flanks.fa``, and it must be that file rather than
    ``reference.fasta``: the flanking primers in
    ``04_mame_custom_barcodes.xlsx`` were designed in the synthetic flanks by
    ``python-core/scripts/regen_mame_sample_barcodes.py``, so against the bare
    720 bp CDS the tails are absent and every demo run reported
    ``_SpanReason.NOT_FOUND``. That outcome is legitimate for a bare-CDS
    reference, which is exactly why nothing failed and nobody noticed; what was
    wrong is that the demo could never show extraction working. Both halves are
    pinned here, since the point is the contrast between them.
    """
    from kuma_core.mame.ingest.amplicon_reference import resolve_amplicon_reference

    samples = Path(__file__).resolve().parents[2] / "src-tauri" / "samples" / "mame"
    barcodes = samples / "04_mame_custom_barcodes.xlsx"

    resolution = resolve_amplicon_reference(
        samples / "egfp_with_flanks.fa", barcodes, tmp_path / "flanked"
    )

    assert resolution.extracted
    assert resolution.span is not None
    # The construct is 1620 bp with the CDS at 450..1170; the amplicon runs from
    # the forward primer site to the end of the reverse primer site.
    assert resolution.original_length == 1620
    assert (resolution.span.start, resolution.span.end) == (50, 1275)
    assert resolution.reference_fasta.read_text(encoding="utf-8").count("\n") > 1

    bare = resolve_amplicon_reference(
        samples / "reference.fasta", barcodes, tmp_path / "bare"
    )

    assert not bare.extracted
    assert bare.span is None


# ---------------------------------------------------------------------------
# One rule, two readers
# ---------------------------------------------------------------------------


def test_amplicon_extraction_and_demux_agree_on_the_tail(
    tmp_path: Path, gene_barcodes_xlsx: Path
) -> None:
    """The amplicon cut and the seed cut are made by the same helper.

    Both modules import ``barcode_tail.common_tail``; this pins the consequence
    rather than the import. The reference is built so the amplicon span is
    exactly forward tail + coding + revcomp(reverse tail), so the extracted
    length can only be right if both readers derived the same two tails.
    """
    from kuma_core.mame.ingest.amplicon_reference import resolve_amplicon_reference
    from kuma_core.mame.ingest.combinatorial_demux import _reverse_complement

    coding = "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGA"
    amplicon = _GENE_F_TAIL + coding + _reverse_complement(_GENE_R_TAIL)
    reference = tmp_path / "reference.fa"
    reference.write_text(f">gene\n{'G' * 40}{amplicon}{'C' * 30}\n", encoding="utf-8")

    resolution = resolve_amplicon_reference(
        reference, gene_barcodes_xlsx, tmp_path / "out"
    )

    assert resolution.extracted
    assert resolution.span is not None
    assert resolution.span.start == 40
    assert resolution.span.end == 40 + len(amplicon)


# ---------------------------------------------------------------------------
# End to end: a non-ispS plate has to come back off the reads
# ---------------------------------------------------------------------------

_DEMUX_REF_SEQ = "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGAGACCCGT"


def _build_gene_read(r_index: int, f_index: int) -> str:
    """One synthetic read of the real library shape, non-ispS flanks.

    5'-[F seed + F anneal]-[insert]-[RC(R anneal) + RC(R seed)]-3'
    """
    from kuma_core.mame.ingest.combinatorial_demux import _reverse_complement

    return (
        _GENE_F_SEEDS[f_index - 1]
        + _GENE_F_TAIL
        + _DEMUX_REF_SEQ
        + _reverse_complement(_GENE_R_TAIL)
        + _reverse_complement(_GENE_R_SEEDS[r_index - 1])
    )


def test_demux_places_every_well_of_a_non_isps_plate(
    tmp_path: Path, gene_barcodes_xlsx: Path
) -> None:
    """Twelve wells go in and twelve wells come out, with no ispS tail anywhere.

    Reads for rows 1 and 2 are the discriminating part: those two reverse seeds
    share their first 10 bases, so the pre-derivation rule cut both to the same
    string and the matcher dropped every read carrying either one as ambiguous.
    That left rows 1 and 2 empty and the run reporting a clean four-well plate,
    which is the shape of quiet failure this whole change is about.
    """
    import gzip

    from kuma_core.mame.ingest.combinatorial_demux import run_combinatorial_demux

    reference = tmp_path / "reference.fasta"
    reference.write_text(f">gene_amplicon\n{_DEMUX_REF_SEQ}\n", encoding="utf-8")

    fastq = tmp_path / "reads.fastq.gz"
    with gzip.open(fastq, "wt") as handle:
        for r_index in (1, 2, 3):
            for f_index in (1, 2, 3, 4):
                for replicate in range(2):
                    sequence = _build_gene_read(r_index, f_index)
                    handle.write(
                        f"@read_{r_index}_{f_index}_{replicate}\n{sequence}\n"
                        f"+\n{'I' * len(sequence)}\n"
                    )

    result = run_combinatorial_demux(
        raw_fastq_paths=[fastq],
        reference_fasta=reference,
        barcodes_xlsx=gene_barcodes_xlsx,
        output_dir=tmp_path / "out",
        mapq_threshold=0,
        coverage_fraction=0.5,
        trim_flank_bp=30,
        min_depth=1,
    )

    expected_wells = {
        f"{r_index}_{f_index}"
        for r_index in (1, 2, 3)
        for f_index in (1, 2, 3, 4)
    }
    assert set(result.per_well_reads) == expected_wells
    assert result.stats.assigned_reads == 24
