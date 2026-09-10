"""Materialize the on-disk test fixtures described in 030_테스트_fixture.md.

Running this module standalone also works: ``python tests/create_fixtures.py``.
"""

from __future__ import annotations

import random
from pathlib import Path

import openpyxl

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"

_REFERENCE = (
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)

# --- FASTA bodies (exact copies from 030 §3). ------------------------------
_NB01_1_1 = (
    "ATGGTGTTCAAGAACTTTTTCGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)
_NB01_1_2 = (
    "ATGGTGTTCAAGAACTTTTTCGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAG---TTCAACAAGAACTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)
_NB01_1_3 = (
    "ATGGTGTTCAAGAACTTTTTCGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGACC"
)
_NB01_1_4 = (
    "ATGTTGTTCAAGAACTTTTTCGCGTTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGTTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)

_NB02_1_1 = _NB01_1_1  # same sequence, but file forced small for LOWDEPTH.
_NB02_1_2 = (
    "ATGGTGTTCAAGAACTTTTTCGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAAGAAGTTCAACTGA"
)
_NB02_1_3 = _NB01_1_1
_NB02_1_4 = _NB01_1_1

_NB03_1_1 = _NB02_1_2  # WRONG_AA
_NB03_1_2 = _NB01_1_3  # FRAMESHIFT
_NB03_1_3 = _NB01_1_1  # PASS
_NB03_1_4 = _NB01_1_4  # MANY

_FASTA_MAP: dict[tuple[str, str], str] = {
    ("NB01", "1_1"): _NB01_1_1,
    ("NB01", "1_2"): _NB01_1_2,
    ("NB01", "1_3"): _NB01_1_3,
    ("NB01", "1_4"): _NB01_1_4,
    ("NB02", "1_1"): _NB02_1_1,
    ("NB02", "1_2"): _NB02_1_2,
    ("NB02", "1_3"): _NB02_1_3,
    ("NB02", "1_4"): _NB02_1_4,
    ("NB03", "1_1"): _NB03_1_1,
    ("NB03", "1_2"): _NB03_1_2,
    ("NB03", "1_3"): _NB03_1_3,
    ("NB03", "1_4"): _NB03_1_4,
}

# NB02/1_1 is the designated LOWDEPTH fixture. LOWDEPTH is now driven by the
# real read-depth gate (the consensus `depth=N` header) rather than the
# file-size proxy: this well carries `depth=5` (< the recommended
# min_read_count=30) so it stays LOWDEPTH regardless of file size. Every other
# well carries `depth=100` so the read-depth gate clears them.
_LOWDEPTH_KEY = ("NB02", "1_1")
_LOWDEPTH_DEPTH = 5
_PASSING_DEPTH = 100


def reference_sequence() -> str:
    return _REFERENCE


def _write_fasta(path: Path, header: str, body: str, pad_to_bytes: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Wrap body at 60 chars to match typical FASTA output.
    wrapped = "\n".join(body[i : i + 60] for i in range(0, len(body), 60))
    text = f">{header}\n{wrapped}\n"
    if pad_to_bytes is not None and len(text.encode("utf-8")) < pad_to_bytes:
        # Pad using additional comment lines (';' prefix) which FASTA parsers
        # universally ignore; our parser ignores any line that does not start
        # with '>' and treats it as sequence, so we instead pad with blank
        # records carrying the same data under separate headers is invalid. We
        # pad by appending whitespace-only lines that the parser strips.
        padding_line = ("N" * 78 + "\n").encode("utf-8")  # noqa: F841 - retained for clarity
        # Use a stream of blank lines (our parser strips and skips empty lines).
        filler = ("\n" * 64).encode("utf-8")
        encoded = text.encode("utf-8")
        while len(encoded) < pad_to_bytes:
            encoded += filler
        path.write_bytes(encoded)
        return
    path.write_text(text, encoding="utf-8")


def _create_kuro_xlsx(dest: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Fwd List"
    ws.append(
        [
            "Well",
            "Primer Name",
            "Sequence",
            "Length",
            "Tm",
            "Tm_Overlap",
            "WT_Codon",
            "MT_Codon",
            "Mutation",
        ]
    )
    # Wells are column-major, the way a real KURO export writes them: occupant 2
    # is B1, not A2 (A2 is well 9). The fixture said A2, which made this sheet
    # describe a different plate from its own `expected_mutations` sheet. Nothing
    # noticed while `plate_order_check` collapsed both sides into dense lists and
    # compared them by position; once it compares by well, the fixture is a
    # self-contradicting workbook and every validation using it reports a plate
    # mismatch it was never meant to carry.
    ws.append(["A1", "V5F_F", "ATGGTGTTCAAGNNNNNNNNN", 20, 62.0, 42.0, "GTG", "TTT", "V5F"])
    ws.append(["B1", "K53N_F", "AAGCTGAAAGCGNNNNNNNNN", 20, 61.5, 41.5, "AAG", "AAC", "K53N"])

    ws2 = wb.create_sheet("expected_mutations")
    ws2.append(
        [
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
    )
    ws2.append(["V5F", 5, "V", "F", "GTG", "TTT", "", "V5F", "substitution", "DESIGNED"])
    ws2.append(["K53N", 53, "K", "N", "AAG", "AAC", "", "K53N", "substitution", "DESIGNED"])

    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)


def _create_reference(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = _REFERENCE
    wrapped = "\n".join(body[i : i + 60] for i in range(0, len(body), 60))
    dest.write_text(f">ref_cds length=210 organism=synthetic\n{wrapped}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Homopolymer regression fixture
# ---------------------------------------------------------------------------
# A second, independent synthetic reference whose only purpose is to be a ruler.
# The 177 bp `_REFERENCE` above carries no run longer than 3, so nothing in the
# existing bench can say what MAME does when the reference contains the long
# homopolymers that ONT chemistry miscalls. This one carries six of them, at
# three lengths, plus two length-matched control blocks whose longest run is 1.
#
# NOTHING HERE ASSERTS AN IMPROVEMENT. The literature does not support the claim
# that per-base quality weighting reduces homopolymer error: what it supports is
# a WINDOW-mean Q around a candidate position (Ye et al. 2025, GigaScience 14
# giaf018), and MAME weights a single base. The direction of the net effect is
# unmeasured. This fixture exists so the effect can be MEASURED rather than
# assumed, before and after the FASTQ-quality wiring change.
#
# Layout (228 bp, 76 codons):
#   ATG | control block A (72 bp, max run 1) | homopolymer block (78 bp)
#       | control block B (72 bp, max run 1) | pad | TAA
# The homopolymer block holds A6, T6, G7, C7, A8, T8, each flanked by a 3 bp
# spacer that cannot extend the run. Two runs per length is the minimum that
# separates a length effect from a single unlucky locus.
_HOMOPOLYMER_REFERENCE = (
    "ATGATCGATCGACGTACGCATCGTACGCATGCATCGACGTACGCATCGTACGATCGATCGT"
    "ACGCATGCATCGTACGTAAAAAACGTCAGTTTTTTCAGCATGGGGGGGCATATGCCCCCCC"
    "ATGCGTAAAAAAAACGTCAGTTTTTTTTCAGCATCGTACGATCGACGTACGCATCGATGCA"
    "TCGTACGACGTATCGATCGCATCGTACGATCGTACGCATCGATAA"
)

#: Master seed for the homopolymer read simulator. Every well derives its own
#: stream from this value and its own index, so the whole fixture is one number
#: away from being regenerated identically on any machine.
HOMOPOLYMER_SEED = 20260910

#: Per-read homopolymer deletion probability, one tier per group of wells.
#: Majority vote only turns a per-read deletion into a no-call once the deletion
#: is the majority at that column, so a single rate would land the whole fixture
#: on one side of that transition and show nothing. These four straddle it.
HOMOPOLYMER_DEL_PROB_TIERS: tuple[float, ...] = (0.10, 0.30, 0.50, 0.70)

#: Wells per tier, and reads per well. 40 clears `min_read_count=30` so the
#: LOWDEPTH gate stays live without swallowing every well.
HOMOPOLYMER_WELLS_PER_TIER = 6
HOMOPOLYMER_READS_PER_WELL = 40

#: Runs at or above this length are treated as homopolymers by the simulator and
#: by the region classifier the test uses. 6 is the task-specified floor.
HOMOPOLYMER_MIN_RUN = 6

# --- error model constants (ASSUMPTIONS, not measurements) ------------------
# These numbers are a stated model, not a calibration against any run. They were
# chosen so both the homopolymer signal and the control noise floor are non-zero
# and separable at this depth. Reading any of them as an ONT error rate would be
# a mistake.
_SUB_RATE = 0.02           # per-base substitution
_NONHP_INDEL_RATE = 0.001  # per-base indel outside a homopolymer
_HP_INS_RATIO = 0.5        # insertion probability = deletion probability x this
_Q_CORRECT = (25, 35)      # Phred range assigned to a base the simulator kept
_Q_ERROR = (5, 12)         # Phred range assigned to a base the simulator broke
_COMPLEMENT = str.maketrans("ACGT", "TGCA")


def homopolymer_reference_sequence() -> str:
    """The homopolymer regression reference (228 bp CDS)."""
    return _HOMOPOLYMER_REFERENCE


def homopolymer_runs(
    seq: str, min_len: int = HOMOPOLYMER_MIN_RUN
) -> list[tuple[int, int, str]]:
    """Return ``(start, length, base)`` for every run of at least *min_len*.

    Derived by scanning the sequence rather than hardcoded, so a fixture edit
    cannot leave the coordinates behind. A checker carrying its own copy of a
    constant the target declares is a checker that inspects zero items and
    reports zero defects; this one reads the target.
    """
    out: list[tuple[int, int, str]] = []
    i = 0
    n = len(seq)
    while i < n:
        j = i
        while j + 1 < n and seq[j + 1] == seq[i]:
            j += 1
        if j - i + 1 >= min_len:
            out.append((i, j - i + 1, seq[i]))
        i = j + 1
    return out


def _phred(rng: random.Random, lo_hi: tuple[int, int]) -> str:
    return chr(33 + rng.randint(lo_hi[0], lo_hi[1]))


def _reverse_complement_with_qual(seq: str, qual: str) -> tuple[str, str]:
    return seq.translate(_COMPLEMENT)[::-1], qual[::-1]


def simulate_homopolymer_reads(
    reference: str,
    n_reads: int,
    hp_del_prob: float,
    seed: int,
) -> list[tuple[str, str, str]]:
    """Simulate ONT-like reads over *reference*, returning ``(id, seq, qual)``.

    The model, stated in full because every number in it is an assumption:

    * Each run of at least ``HOMOPOLYMER_MIN_RUN`` identical bases loses one base
      with probability ``hp_del_prob``, and otherwise gains one with probability
      ``hp_del_prob * _HP_INS_RATIO``. Length dependence is therefore NOT built
      in: every run of length 6, 7 and 8 gets the same per-read probability. Any
      length effect the test observes comes from the pileup and the aligner, not
      from the simulator preferring longer runs.
    * Every emitted base is substituted with probability ``_SUB_RATE`` and, when
      outside a homopolymer, deleted or duplicated with probability
      ``_NONHP_INDEL_RATE``.
    * Quality is informative about the simulator's OWN substitution and insertion
      decisions: a base it broke draws from ``_Q_ERROR``, a base it kept from
      ``_Q_CORRECT``. The ranges straddle the default ``min_base_quality=10``,
      so a quality-aware consensus can remove some but not all of those errors.
      A real basecaller is far less self-aware than this, so an arm consuming
      quality is measured here at an OPTIMISTIC bound. A DELETED base carries no
      quality at all, so the homopolymer mechanism itself is invisible to any
      per-base quality filter by construction. That is the object of the
      measurement, not a flaw in it.
    * Half the reads are emitted reverse-complemented, quality reversed with them.

    Reads span the whole reference: no primer flank, no adapter, no chimera.
    """
    rng = random.Random(seed)
    hp_positions: set[int] = set()
    for start, length, _base in homopolymer_runs(reference):
        hp_positions.update(range(start, start + length))

    reads: list[tuple[str, str, str]] = []
    for read_i in range(n_reads):
        bases: list[str] = []
        quals: list[str] = []
        i = 0
        n = len(reference)
        while i < n:
            if i in hp_positions:
                # Consume the whole run at once so the length change is one event
                # per run per read, the way a basecaller miscounts a run.
                j = i
                while j + 1 < n and reference[j + 1] == reference[i]:
                    j += 1
                run_len = j - i + 1
                emit = run_len
                roll = rng.random()
                if roll < hp_del_prob:
                    emit = run_len - 1
                elif roll < hp_del_prob + hp_del_prob * _HP_INS_RATIO:
                    emit = run_len + 1
                for k in range(emit):
                    base = reference[i]
                    broke = k >= run_len  # the duplicated base is the fabricated one
                    if rng.random() < _SUB_RATE:
                        base = rng.choice([b for b in "ACGT" if b != base])
                        broke = True
                    bases.append(base)
                    quals.append(_phred(rng, _Q_ERROR if broke else _Q_CORRECT))
                i = j + 1
                continue
            base = reference[i]
            broke = False
            if rng.random() < _SUB_RATE:
                base = rng.choice([b for b in "ACGT" if b != base])
                broke = True
            r = rng.random()
            if r < _NONHP_INDEL_RATE:
                i += 1
                continue
            bases.append(base)
            quals.append(_phred(rng, _Q_ERROR if broke else _Q_CORRECT))
            if r < 2 * _NONHP_INDEL_RATE:
                bases.append(base)
                quals.append(_phred(rng, _Q_ERROR))
            i += 1

        seq = "".join(bases)
        qual = "".join(quals)
        if read_i % 2 == 1:
            seq, qual = _reverse_complement_with_qual(seq, qual)
        reads.append((f"hp_read_{read_i}", seq, qual))
    return reads


def homopolymer_well_reads() -> dict[str, list[tuple[str, str, str]]]:
    """Every well of the homopolymer fixture, keyed ``tier{t}_w{i}``.

    Deterministic: the only inputs are ``HOMOPOLYMER_SEED`` and the well index.
    """
    ref = homopolymer_reference_sequence()
    wells: dict[str, list[tuple[str, str, str]]] = {}
    for tier_i, prob in enumerate(HOMOPOLYMER_DEL_PROB_TIERS):
        for well_i in range(HOMOPOLYMER_WELLS_PER_TIER):
            seed = HOMOPOLYMER_SEED + tier_i * 1000 + well_i
            wells[f"tier{tier_i}_w{well_i}"] = simulate_homopolymer_reads(
                reference=ref,
                n_reads=HOMOPOLYMER_READS_PER_WELL,
                hp_del_prob=prob,
                seed=seed,
            )
    return wells


def _create_homopolymer_reference(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = _HOMOPOLYMER_REFERENCE
    wrapped = "\n".join(body[i : i + 60] for i in range(0, len(body), 60))
    dest.write_text(
        f">hp_ref_cds length={len(body)} organism=synthetic\n{wrapped}\n",
        encoding="utf-8",
    )


# Target pad size for non-LOWDEPTH fixtures: ~52 KB to stay safely above 50.
_PAD_BYTES_ABOVE = 52 * 1024


def ensure_fixtures() -> None:
    ref_path = FIXTURE_ROOT / "reference.fasta"
    if not ref_path.exists():
        _create_reference(ref_path)

    # xlsx must not be rewritten on every run: openpyxl re-serialization
    # produces byte-level churn (zip archive timestamps) even though the
    # semantic content is unchanged. The fixture is immutable — only
    # create it if it is missing.
    kuro_path = FIXTURE_ROOT / "KURO_test.xlsx"
    if not kuro_path.exists():
        _create_kuro_xlsx(kuro_path)

    hp_ref_path = FIXTURE_ROOT / "homopolymer_reference.fasta"
    if not hp_ref_path.exists():
        _create_homopolymer_reference(hp_ref_path)

    for (nb, custom), body in _FASTA_MAP.items():
        out = FIXTURE_ROOT / "mock_consensus_output" / nb / f"{custom}.fasta"
        if out.exists():
            continue
        is_lowdepth = (nb, custom) == _LOWDEPTH_KEY
        # Real read depth lives in the consensus `depth=N` header. The LOWDEPTH
        # fixture carries depth below min_read_count; all others clear it. The
        # custom_barcode is header.split()[0], so the trailing ` depth=N` is
        # parsed as metadata without disturbing the barcode token.
        depth = _LOWDEPTH_DEPTH if is_lowdepth else _PASSING_DEPTH
        pad = None if is_lowdepth else _PAD_BYTES_ABOVE
        _write_fasta(
            out, header=f"{custom} depth={depth}", body=body, pad_to_bytes=pad
        )


if __name__ == "__main__":
    ensure_fixtures()
    print(f"Fixtures created under: {FIXTURE_ROOT}")
