"""MAME barcode primers get the same structural QC as KURO SDM primers.

Until v0.16 a barcode flanking primer was accepted on its Tm window and its 3'
GC clamp alone, while the equivalent KURO primer also had to clear hairpin,
homodimer and off-target checks. These tests pin the three added checks, the
fallback behaviour when nothing clears them, and the fact that the advisory
pass over the full ``seed + flanking`` oligo does not move a selection.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from kuma_core.mame.ingest import barcode_package as bp
from kuma_core.mame.ingest.barcode_package import (
    design_flanking_primers,
    generate_mame_package,
)
from kuma_core.mame.ingest.polymerase import get_profile

_PROFILE = get_profile("Q5")
_COMPLEMENT = str.maketrans("ACGT", "TGCA")

# Hairpin 73.4 C / homodimer 35.9 C on the design scale: fails hairpin alone.
_HAIRPIN_18 = "GGGCCCTTTTTTGGGCCC"
# Hairpin 35.7 C / homodimer 44.4 C: fails homodimer alone. Ends in A, so the
# tests that use it switch the GC clamp off to keep the two checks separate.
_HOMODIMER_18 = "TCCGCGCGGATTCACTAA"

_GENE_START = 300
_GENE_LEN = 300


def _clean_template(seed: int, length: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(length))


def _plant(template: str, at: int, motif: str) -> str:
    return template[:at] + motif + template[at + len(motif):]


def _design(template: str, **kwargs) -> tuple[str, str, list[str]]:
    params: dict[str, Any] = dict(
        gene_start=_GENE_START,
        gene_end=_GENE_START + _GENE_LEN,
        profile=_PROFILE,
        overhang_max=60,
        binding_min_len=18,
        binding_max_len=18,
        tm_min=-1000.0,
        tm_max=1000.0,
        require_gc_clamp=False,
    )
    params.update(kwargs)
    return design_flanking_primers(template, **params)


# ---------------------------------------------------------------------------
# The three added checks reject a candidate
# ---------------------------------------------------------------------------

def test_hairpin_candidate_is_not_selected() -> None:
    """The outermost site folds on itself, so the search moves inward."""
    template = _plant(_clean_template(1001, 900), _GENE_START - 60, _HAIRPIN_18)
    assert "hairpin" in " ".join(bp._structure_failures(_HAIRPIN_18))

    fwd, _rev, _warns = _design(template)

    assert fwd.upper() != _HAIRPIN_18
    assert not bp._structure_failures(fwd.upper())


def test_homodimer_candidate_is_not_selected() -> None:
    """Same, for a site that dimerises with a copy of itself."""
    template = _plant(_clean_template(1002, 900), _GENE_START - 60, _HOMODIMER_18)
    failures = " ".join(bp._structure_failures(_HOMODIMER_18))
    assert "homodimer" in failures and "hairpin" not in failures

    fwd, _rev, _warns = _design(template)

    assert fwd.upper() != _HOMODIMER_18


def test_offtarget_candidate_is_not_selected() -> None:
    """A site whose sequence also occurs elsewhere on the template is refused.

    The second copy is a second binding site for the same primer, which is the
    spurious-amplicon risk ``check_offtarget`` exists to catch.
    """
    base = _clean_template(1003, 900)
    cap_site = base[_GENE_START - 60: _GENE_START - 42]
    template = _plant(base, 800, cap_site)
    assert template.count(cap_site) == 2
    assert bp._binding_qc_failures(
        cap_site, template, _GENE_START - 60, 18, len(template)
    )

    fwd, _rev, _warns = _design(template)

    assert fwd.upper() != cap_site
    assert template.count(fwd.upper()) == 1


def test_offtarget_clean_template_yields_no_hits_on_either_strand() -> None:
    """Control for the test above: a repeat-free template rejects nothing.

    A wrong intended-span exclusion would make every candidate hit itself, and
    that failure mode is silent (everything falls to the fallback path).
    """
    template = _clean_template(1004, 900)
    seq_len = len(template)

    assert seq_len == 900

    fwd_pos = _GENE_START - 60
    fwd_site = template[fwd_pos: fwd_pos + 18]
    assert not bp._perfect_repeat_failure(
        fwd_site, template, fwd_pos, fwd_pos + 18
    )
    assert not bp._offtarget_failures(fwd_site, template, fwd_pos, fwd_pos + 18)

    rev_end = _GENE_START + _GENE_LEN + 60
    rev_start = rev_end - 18
    rev_primer = template[rev_start:rev_end].translate(_COMPLEMENT)[::-1]
    assert not bp._perfect_repeat_failure(
        rev_primer, template, rev_start, rev_end
    )
    assert not bp._offtarget_failures(rev_primer, template, rev_start, rev_end)


# ---------------------------------------------------------------------------
# Nothing clears QC
# ---------------------------------------------------------------------------

def test_total_qc_failure_falls_back_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every candidate fails, so the old fallback still runs and warns loudly.

    No new ValueError is introduced, and the warning states that the primer
    that was selected did not pass QC rather than presenting it as clean.
    """
    monkeypatch.setattr(bp, "_QC_STRUCTURE_TM_MAX", -1.0)
    template = _clean_template(1005, 900)

    fwd, rev, warns = _design(template)

    assert fwd and rev
    joined = " ".join(warns)
    assert "did not pass QC" in joined
    assert "hairpin" in joined
    assert "failed QC" in joined


def test_geometry_invariants_survive_the_new_filters() -> None:
    """QC narrows the choice; it does not let a primer into the gene."""
    template = _clean_template(1006, 900)
    gene_end = _GENE_START + _GENE_LEN

    fwd, rev, _warns = _design(template, binding_max_len=35, overhang_min=20)

    fwd_site = fwd.upper()
    rev_site = rev.upper().translate(_COMPLEMENT)[::-1]
    fwd_start = template.index(fwd_site)
    rev_start = template.index(rev_site)

    assert fwd_start + len(fwd_site) <= _GENE_START
    assert rev_start >= gene_end
    assert 20 <= _GENE_START - fwd_start <= 60
    assert 20 <= (rev_start + len(rev_site)) - gene_end <= 60


# ---------------------------------------------------------------------------
# Full-oligo advisory pass
# ---------------------------------------------------------------------------

_FWD_SEEDS = {
    1: "TATCTGACCTT", 2: "GCATACGTAAC", 3: "AACTTGCATAG", 4: "TGACCTAAGGT",
    5: "CCGTATATAAC", 6: "GTAACCTGCAT", 7: "AAGCTTACCAT", 8: "TTCCGGATCAT",
    9: "CCATTAGCATG", 10: "GGTTAACCATG", 11: "AATCCGTTAGC", 12: "GAACATACGGT",
}
_REV_SEEDS = {
    1: "CCCTATGACAG", 2: "GCTATAGCCTT", 3: "TTGCAATCGAT", 4: "CCAGTATCGGT",
    5: "GGTACCTAATG", 6: "AAGCTATCGCT", 7: "TTCCAGCTTAG", 8: "AGAGTGCGGCT",
}


def _write_seeds(path: Path, fwd: dict[int, str], rev: dict[int, str]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["name", "sequence"])
    for i in range(1, 13):
        ws.append([f"fwd_{i}", fwd[i]])
    for i in range(1, 9):
        ws.append([f"rev_{i}", rev[i]])
    wb.save(str(path))


def _run_package(
    tmp_path: Path,
    fwd_seeds: dict[int, str],
    rev_seeds: dict[int, str] | None = None,
) -> tuple[list[str], str]:
    """Generate a package and return (warnings, the forward flanking part)."""
    root = tmp_path
    root.mkdir(parents=True, exist_ok=True)
    fasta = root / "cds.fa"
    fasta.write_text(">cds\n" + _clean_template(1007, 900) + "\n", encoding="utf-8")
    seeds = root / "seeds.xlsx"
    _write_seeds(seeds, fwd_seeds, _REV_SEEDS if rev_seeds is None else rev_seeds)

    result = generate_mame_package(
        fasta_path=fasta,
        gene_start=_GENE_START,
        gene_end=_GENE_START + _GENE_LEN,
        barcode_seeds_path=seeds,
        output_dir=root / "design",
        project_root=root,
        gene_name="egfp",
    )
    wb = openpyxl.load_workbook(result.barcodes_xlsx)
    sheet = wb.active
    assert sheet is not None
    row = sheet["B2"].value
    assert isinstance(row, str)
    flanking = row[len(fwd_seeds[1]):]
    return result.warnings, flanking


def test_full_oligo_warning_does_not_change_the_selected_flanking(
    tmp_path: Path,
) -> None:
    """A seed that folds is reported and nothing else.

    The seed is an input the operator already ordered, so there is no
    alternative to select; rejecting the binding site for it would apply a
    criterion nothing defines.
    """
    clean_warns, clean_flank = _run_package(tmp_path / "clean", dict(_FWD_SEEDS))

    folded = dict(_FWD_SEEDS)
    folded[1] = "GGGCCCTTTTTTGGGCCCAAA"
    folded_warns, folded_flank = _run_package(tmp_path / "folded", folded)

    assert folded_flank == clean_flank

    def _advisory(warnings: list[str]) -> str:
        hits = [w for w in warnings if "advisory structure limit" in w]
        assert len(hits) == 1
        return hits[0]

    clean_line = _advisory(clean_warns)
    folded_line = _advisory(folded_warns)
    assert clean_line != folded_line

    # The advisory quotes the folded oligo that was actually written, and the
    # value is read back from the module rather than restated as a literal.
    tms = bp._structure_tms(folded[1] + folded_flank)
    assert tms is not None
    hairpin_tm, _homodimer_tm = tms
    assert f"egfp_f_1: hairpin Tm={hairpin_tm:.1f} C" in folded_line


def test_full_oligo_longer_than_primer3_limit_is_reported_not_crashed() -> None:
    """65 nt is reachable (30 bp seed + 35 bp flank) and primer3 refuses >60."""
    long_oligo = "A" * 61
    assert bp._structure_tms(long_oligo) is None
    warnings = bp._full_oligo_qc_warnings([("egfp_f_1", long_oligo)])
    assert warnings and "were not" in warnings[0] and "egfp_f_1" in warnings[0]


# ---------------------------------------------------------------------------
# Fwd x rev heterodimer advisory pass
# ---------------------------------------------------------------------------

def _heterodimer_lines(warnings: list[str]) -> list[str]:
    return [w for w in warnings if "advisory heterodimer limit" in w]


def test_complementary_seed_pair_is_flagged_as_heterodimer(tmp_path: Path) -> None:
    """A rev seed that pairs with a fwd seed is reported; the clean set is not.

    fwd_1 and rev_1 share a well in combinatorial barcoding, so a duplex
    between their full oligos is the failure the pass exists to catch. The
    clean seed set is the negative control: without it a pass that flags
    every pair would satisfy the positive half.
    """
    clean_warns, clean_flank = _run_package(tmp_path / "clean", dict(_FWD_SEEDS))
    assert _heterodimer_lines(clean_warns) == []

    fwd = dict(_FWD_SEEDS)
    rev = dict(_REV_SEEDS)
    fwd[1] = "GGCGCTTCAGGCGACCTG"
    rev[1] = fwd[1].translate(_COMPLEMENT)[::-1]
    warns, flank = _run_package(tmp_path / "paired", fwd, rev)

    # Advisory only: the forward flanking primer is chosen before the seeds
    # are read and does not move.
    assert flank == clean_flank

    lines = _heterodimer_lines(warns)
    assert len(lines) == 1
    assert "egfp_f_1 x egfp_r_1: heterodimer Tm=" in lines[0]
    tm = float(lines[0].split("egfp_f_1 x egfp_r_1: heterodimer Tm=")[1].split(" ")[0])
    assert tm > bp._QC_HETERODIMER_TM_MAX


def test_heterodimer_pass_covers_exactly_the_96_fwd_rev_pairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every fwd_i x rev_j pair goes through the shared thermo adapter once.

    Spied on ``kuma_core.shared.thermo``, the adapter KURO's
    ``_check_secondary_structure`` calls, so a local reimplementation of the
    dimer maths would leave the counters at zero and fail here.
    """
    from kuma_core.shared import thermo

    calls: dict[str, list[tuple[Any, ...]]] = {
        "calc_hairpin": [], "calc_homodimer": [], "calc_heterodimer": [],
    }
    for name in calls:
        real = getattr(thermo, name)

        def spy(*args: Any, _real: Any = real, _name: str = name, **kwargs: Any) -> Any:
            calls[_name].append(tuple(args))
            return _real(*args, **kwargs)

        monkeypatch.setattr(thermo, name, spy)

    _run_package(tmp_path, dict(_FWD_SEEDS))

    # check_offtarget also calls calc_heterodimer (primer against a template
    # site), so keep only the calls whose partners are two full barcode oligos.
    fwd_len = len(_FWD_SEEDS[1])
    rev_len = len(_REV_SEEDS[1])
    fwd_set = set(_FWD_SEEDS.values())
    rev_set = set(_REV_SEEDS.values())
    oligo_pairs = [
        (a[:fwd_len], b[:rev_len])
        for a, b in calls["calc_heterodimer"]
        if a[:fwd_len] in fwd_set and b[:rev_len] in rev_set
    ]
    assert len(oligo_pairs) == 12 * 8
    assert set(oligo_pairs) == {(f, r) for f in fwd_set for r in rev_set}
    # Flanking candidates plus the 20 full oligos.
    assert len(calls["calc_hairpin"]) >= 20
    assert len(calls["calc_homodimer"]) >= 20


def test_flanking_search_calls_kuro_check_offtarget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The off-target verdict comes from KURO's function, not a MAME copy."""
    from kuma_core.kuro import sdm_engine

    seen: list[str] = []
    real = sdm_engine.check_offtarget

    def spy(primer_seq: str, *args: Any, **kwargs: Any) -> Any:
        seen.append(primer_seq.upper())
        return real(primer_seq, *args, **kwargs)

    monkeypatch.setattr(sdm_engine, "check_offtarget", spy)
    fwd, rev, _warns = _design(_clean_template(1008, 900))

    assert fwd.upper() in seen
    assert rev.upper() in seen


def test_heterodimer_length_guard_needs_both_partners_over_the_limit() -> None:
    """primer3 refuses a pair only when both exceed 60 nt; one long is fine."""
    long_a = "ACGT" * 16  # 64 nt
    long_b = "TGCA" * 16
    short = "ACGTACGTACGTACGTAC"
    assert bp._heterodimer_tm(long_a, short) is not None
    assert bp._heterodimer_tm(long_a, long_b) is None

    rows = [(f"egfp_f_{i}", long_a) for i in range(1, 13)]
    rows += [("egfp_r_1", long_b)] + [(f"egfp_r_{i}", short) for i in range(2, 9)]
    warnings = bp._heterodimer_qc_warnings(rows)
    unchecked = [w for w in warnings if "were not checked for heterodimer" in w]
    assert len(unchecked) == 1 and unchecked[0].startswith("12 of 96 ")
