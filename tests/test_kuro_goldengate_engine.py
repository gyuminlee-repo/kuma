"""Self-consistency tests for the generic KURO Golden Gate engine (L1).

The engine is organism-parameterized (codon usage = Kazusa) and reports Tm via
SantaLucia 1998 (the SnapGene method). Regression is guarded by *engine
self-consistency invariants* against a committed golden snapshot
(``mutation_results_v5_golden.csv``, 96 rows = 8 positions x 12 target AAs), NOT by
external fixed codon values. Because the codon table is now Kazusa E. coli, the
selected codon for several amino acids (notably Ser) differs from the legacy v4
hand table; that is expected and v5 is regenerated from the live engine.

The CDS that drives the batch is reconstructed from each golden row's WT context
window (21 codons, mutated centre restored to the WT codon) placed at its absolute
codon index. Inter-window gaps are filled with neutral codons that never enter any
mutation's +/-10-codon neighborhood, so per-mutation results (codon screen, overhang
geometry, context window, and the batch Tm ceiling) are identical to the true CDS.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from kuma_core.kuro import goldengate as gg
from kuma_core.kuro.codon_table import CODON_TO_AA
from kuma_core.kuro.overlap import reverse_complement
from kuma_core.kuro.sdm_engine import calc_sdm_tm

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kuro_goldengate"
_GOLDEN = _FIXTURES / "mutation_results_v5_golden.csv"

_CODON_AT = 30  # non-truncated 21-codon window => mutated codon starts at nt 30
_FILLER = "AAA"  # neutral gap codon; never within any mutation's +/-10-codon window
_ORGANISM = "ecoli"


def _golden_rows() -> list[dict]:
    with _GOLDEN.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(line for line in fh if not line.startswith("#"))
        rows = list(reader)
    assert rows and all(r["context_window_truncated"] == "FALSE" for r in rows)
    return rows


def _reconstruct_cds(rows: list[dict]) -> tuple[str, str]:
    """Rebuild a single CDS whose +/-10-codon neighborhood around every golden
    position reproduces the reference WT sequence (gaps neutrally filled)."""
    pos_window: dict[int, str] = {}
    for r in rows:
        p = int(r["position_1based"])
        ctx = r["context_window_up_to_21_codons"]
        wt = ctx[:_CODON_AT] + r["original_codon"] + ctx[_CODON_AT + 3:]
        assert len(wt) == 63
        prev = pos_window.setdefault(p, wt)
        assert prev == wt, p
    ncod = max(pos_window) + 10
    codons = [_FILLER] * ncod
    for p, wt in pos_window.items():
        for i in range(21):  # window covers codon indices (p-11)..(p+9)
            codons[p - 11 + i] = wt[i * 3:i * 3 + 3]
    dna = "".join(codons)
    return dna, gg.translate_dna(dna)


@pytest.fixture(scope="module")
def golden() -> list[dict]:
    return _golden_rows()


@pytest.fixture(scope="module")
def bsai():
    enz = gg.get_enzyme("BsaI")
    return enz, gg.load_overhang_scores(enz)


@pytest.fixture(scope="module")
def batch(golden):
    """The live engine batch driven by the reconstructed CDS, plus its Tm ceiling."""
    dna, protein = _reconstruct_cds(golden)
    muts = [r["mutation"] for r in golden]
    results = gg.design_goldengate(dna, protein, muts, enzyme="BsaI", organism=_ORGANISM)
    enz = gg.get_enzyme("BsaI")
    scores = gg.load_overhang_scores(enz)
    # Reconstruct the pre-trim Tm ceiling exactly as apply_global_tm_trim does.
    pre = [
        gg.design_single_goldengate(
            dna, protein, m, enz, scores,
            gg.DEFAULT_FORBIDDEN_SITES, gg.DEFAULT_FORBIDDEN_OVERHANGS,
            organism=_ORGANISM, prefix=enz.prefix,
        )
        for m in muts
    ]
    tms = [v for r in pre if r.status == "success" for v in (r.left_tm, r.right_tm) if v is not None]
    ceiling = round(min(tms) + gg.GLOBAL_TM_WINDOW, 2)
    by_mut = {r.mutation: r for r in results}
    return {"dna": dna, "protein": protein, "results": results, "by_mut": by_mut, "ceiling": ceiling}


class TestSelfConsistency:
    """The engine output must satisfy its own design invariants for all 96 rows.

    These replace the legacy fixed-golden codon comparison (codon=Kazusa now differs
    per amino acid); regression is guarded by engine<->snapshot self-consistency.
    """

    def test_all_rows_succeed(self, batch) -> None:
        results = batch["results"]
        assert len(results) == 96
        assert all(r.status == "success" for r in results)

    def test_codon_encodes_target_aa(self, batch) -> None:
        # (a) the selected codon translates to the requested target AA.
        for r in batch["results"]:
            assert CODON_TO_AA[r.mt_codon] == r.target_aa, r.mutation

    def test_codon_is_first_forbidden_passing_priority(self, batch) -> None:
        # (b) mt_codon == first _codon_priority codon that clears the forbidden screen.
        dna = batch["dna"]
        ncod = len(dna) // 3
        for r in batch["results"]:
            ci = r.aa_position - 1
            cs = ci * 3
            chosen = None
            for cand, _usage in gg._codon_priority(r.target_aa, _ORGANISM):
                mutated = dna[:cs] + cand + dna[cs + 3:]
                window = mutated[max(0, ci - 2) * 3:min(ncod, ci + 3) * 3]
                bad, _ = gg.contains_forbidden_site(window, gg.DEFAULT_FORBIDDEN_SITES)
                if not bad:
                    chosen = cand
                    break
            assert chosen == r.mt_codon, (r.mutation, chosen, r.mt_codon)

    def test_overhang_recomputes(self, batch, bsai) -> None:
        # (c) overhang == select_overhang recomputation; non-empty; not forbidden.
        enz, scores = bsai
        dna = batch["dna"]
        for r in batch["results"]:
            cs = (r.aa_position - 1) * 3
            mutated = dna[:cs] + r.mt_codon + dna[cs + 3:]
            ov = gg.select_overhang(mutated, cs, scores, gg.DEFAULT_FORBIDDEN_OVERHANGS, enz.overhang_len)
            assert ov["ok"], r.mutation
            assert ov["overhang"] == r.overhang, (r.mutation, ov["overhang"], r.overhang)
            assert ov["overhang_position"] == r.overhang_position, r.mutation
            assert ov["overhang_score"] == r.overhang_score, r.mutation
            assert r.overhang and r.overhang not in gg.DEFAULT_FORBIDDEN_OVERHANGS, r.mutation

    def test_overhang_tiebreak_prefers_minus_one(self, bsai) -> None:
        # (c) on a fidelity-score tie the -1 candidate must win.
        enz, _ = bsai
        # Both candidates forced to the same score via a stub table.
        seq = "ACGTACGTACGT"
        scores = {seq[3:7]: 500, seq[4:8]: 500}  # -1 cand at start 3, +0 at start 4
        ov = gg.select_overhang(seq, 4, scores, [], enz.overhang_len)
        assert ov["overhang_position"] == "-1"

    def test_primers_reconstruct_from_overhang_and_annealing(self, batch, bsai) -> None:
        # (d) reverse == prefix+rc(overhang)+left_annealing; forward == prefix+overhang+right_annealing.
        enz, _ = bsai
        prefix = enz.prefix
        for r in batch["results"]:
            assert r.reverse_seq == prefix + reverse_complement(r.overhang) + r.left_annealing, r.mutation
            assert r.forward_seq == prefix + r.overhang + r.right_annealing, r.mutation

    def test_tm_matches_santalucia_of_annealing(self, batch) -> None:
        # (e) stored Tm == round(calc_sdm_tm(annealing), 2).
        for r in batch["results"]:
            assert r.left_tm == round(calc_sdm_tm(r.left_annealing), 2), r.mutation
            assert r.right_tm == round(calc_sdm_tm(r.right_annealing), 2), r.mutation

    def test_tm_ceiling_and_min_length(self, batch) -> None:
        # (f) every Tm <= ceiling (or trimmed to the floor); annealing >= MIN length.
        ceiling = batch["ceiling"]
        for r in batch["results"]:
            for tm, ann in ((r.left_tm, r.left_annealing), (r.right_tm, r.right_annealing)):
                assert len(ann) >= gg.MIN_ANNEALING_LENGTH, r.mutation
                assert tm <= ceiling + 1e-9 or len(ann) == gg.MIN_ANNEALING_LENGTH, (r.mutation, tm, ceiling)


class TestGoldenRegression:
    """The live engine batch must reproduce the committed v5 snapshot exactly."""

    def test_batch_matches_v5_golden(self, batch, golden) -> None:
        by_mut = batch["by_mut"]
        checked = 0
        for row in golden:
            r = by_mut[row["mutation"]]
            assert r.mt_codon == row["selected_codon"], (row["mutation"], "codon")
            assert r.overhang == row["overhang"], (row["mutation"], "overhang")
            assert r.overhang_position == row["overhang_position"], (row["mutation"], "ov_pos")
            assert r.overhang_score == int(row["overhang_score"]), (row["mutation"], "ov_score")
            assert r.reverse_seq == row["left_primer_5to3"], (row["mutation"], "left_primer")
            assert r.forward_seq == row["right_primer_5to3"], (row["mutation"], "right_primer")
            assert r.left_annealing == row["left_annealing_sequence"], (row["mutation"], "lann")
            assert r.right_annealing == row["right_annealing_sequence"], (row["mutation"], "rann")
            assert r.left_tm == float(row["left_tm"]), (row["mutation"], "ltm")
            assert r.right_tm == float(row["right_tm"]), (row["mutation"], "rtm")
            assert r.context_window == row["context_window_up_to_21_codons"], (row["mutation"], "ctx")
            checked += 1
        assert checked == 96

    def test_golden_provenance_header(self) -> None:
        first = _GOLDEN.read_text(encoding="utf-8-sig").splitlines()[0]
        assert first.startswith("#")
        low = first.lower()
        assert "kazusa" in low and "santalucia" in low and "tiebreak" in low

    def test_ser_rebaselined_to_kazusa(self, batch) -> None:
        # Ser is the AA whose top forbidden-passing codon moved off the legacy table.
        for r in batch["results"]:
            if r.target_aa == "S":
                assert r.mt_codon == gg._codon_priority("S", _ORGANISM)[0][0] == "AGC", r.mutation


class TestTmMethodAndExport:
    """Tm method is SantaLucia end to end; the TSV header advertises it."""

    def test_design_reports_santalucia(self) -> None:
        out = gg.design_goldengate("ATGAAACGTTAA", "MKR*", ["R3K"], enzyme="BsaI")
        assert len(out) == 1 and out[0].mutation == "R3K"
        assert out[0].status == "success"
        assert out[0].tm_method == "santalucia"
        assert out[0].design_method == "goldengate"
        assert gg.TM_METHOD == "santalucia"

    def test_export_header_advertises_santalucia(self, tmp_path) -> None:
        results, _failed = gg.design_goldengate_batch("ATGAAACGTTAA", "MKR*", ["R3K"], enzyme="BsaI")
        out = tmp_path / "gg.tsv"
        gg.export_goldengate_tsv(results, out, enzyme="BsaI")
        text = out.read_text(encoding="utf-8")
        assert "# design_method=goldengate" in text
        assert "# enzyme=BsaI" in text
        assert "# tm_method=santalucia" in text
        lines = text.splitlines()
        header = next(line for line in lines if line.startswith("Mutation\t"))
        for col in ("Overhang", "Overhang_Score", "Forward_Primer", "Reverse_Primer", "Status"):
            assert col in header, col
        assert any(line.startswith("R3K\t") for line in lines)


class TestCodonTableIntegrity:
    """Codon selection is now driven by the organism codon table, not a hand table."""

    def test_priority_codons_encode_their_aa(self) -> None:
        # Every codon offered for an AA must translate back to that AA (no typo path).
        for aa in "ACDEFGHIKLMNPQRSTVWY*":
            for codon, _usage in gg._codon_priority(aa, _ORGANISM):
                assert CODON_TO_AA[codon] == aa, (aa, codon, CODON_TO_AA.get(codon))

    def test_priority_is_freq_desc_then_codon_asc(self) -> None:
        # tiebreak = (-freq, codon): strictly non-increasing freq, codon-ascending on ties.
        for aa in "ACDEFGHIKLMNPQRSTVWY*":
            ranked = gg._codon_priority(aa, _ORGANISM)
            keys = [(-f, c) for c, f in ranked]
            assert keys == sorted(keys), aa

    def test_all_amino_acids_have_codons(self) -> None:
        for aa in "ACDEFGHIKLMNPQRSTVWY*":
            assert gg._codon_priority(aa, _ORGANISM), aa

    def test_design_goldengate_rejects_mismatched_protein(self) -> None:
        with pytest.raises(ValueError):
            gg.design_goldengate("ATGAAACGTTAA", "MMM*", ["R3K"], enzyme="BsaI")
        with pytest.raises(ValueError):
            gg.design_goldengate("ATGAAACG", "MK", ["K2A"], enzyme="BsaI")  # len not %3


class TestEngineUnits:
    """Targeted engine behaviour: degrade, variable overhang_len, forbidden screen."""

    def test_functional_unscored_degrade_no_silent_empty(self) -> None:
        # No fidelity table => still pick a functional overhang (unscored), never empty.
        seq = "AAACCCGGGTTTACGTACGTACGT"  # arbitrary, codon at 12
        res = gg.select_overhang(seq, 12, {}, gg.DEFAULT_FORBIDDEN_OVERHANGS, 4)
        assert res["ok"] and res["overhang"] and res["overhang_score"] is None

    def test_zero_candidates_reports_not_ok(self) -> None:
        # Both -1 and +0 candidates are forbidden overhangs => no valid overhang.
        res = gg.select_overhang("ACGTAC", 1, {}, ["ACGT", "CGTA"], 4)
        assert res["ok"] is False and res["overhang"] == ""

    def test_overhang_len_is_parameterized(self) -> None:
        # SapI (3 nt) must not be hardcoded to 4.
        sapi = gg.get_enzyme("SapI")
        assert sapi.overhang_len == 3
        res = gg.select_overhang("ACGTACGTACGT", 4, {}, [], sapi.overhang_len)
        assert res["ok"] and len(res["overhang"]) == 3

    def test_forbidden_site_screen_rejects_motif_and_rc(self) -> None:
        bad, hits = gg.contains_forbidden_site("AAAGGTCTCAAA", gg.DEFAULT_FORBIDDEN_SITES)
        assert bad and any("GGTCTC" in h for h in hits)
        bad_rc, _ = gg.contains_forbidden_site("AAAGAGACCAAA", gg.DEFAULT_FORBIDDEN_SITES)
        assert bad_rc  # GAGACC = rc(GGTCTC)

    def test_design_goldengate_smoke(self) -> None:
        # End-to-end on a tiny CDS: M K R * with R3K mutation.
        out = gg.design_goldengate("ATGAAACGTTAA", "MKR*", ["R3K"], enzyme="BsaI")
        assert len(out) == 1 and out[0].mutation == "R3K"
        assert out[0].status in {"success", "no_valid_overhang", "no_valid_codon"}
        assert out[0].tm_method == "santalucia" and out[0].design_method == "goldengate"


class TestCdsAndBatch:
    """extract_cds + fault-tolerant batch orchestration (handler-facing L3 core)."""

    def test_extract_cds_from_template(self) -> None:
        template = "GGGG" + "ATGAAACGTTAA" + "CCCC"  # flank + CDS + flank
        assert gg.extract_cds(template, 4) == "ATGAAACGTTAA"

    def test_extract_cds_requires_atg(self) -> None:
        with pytest.raises(ValueError):
            gg.extract_cds("GGGGCCCC", 0)

    def test_extract_cds_runs_to_end_without_stop(self) -> None:
        assert gg.extract_cds("ATGAAACGT", 0) == "ATGAAACGT"

    def test_batch_collects_successes_and_failures(self) -> None:
        cds = "ATGAAACGTTAA"  # M K R *
        results, failed = gg.design_goldengate_batch(
            cds, "MKR*", ["R3K", "Z9Q", "M1Q", "K2"], enzyme="BsaI",
        )
        assert all(r.status == "success" for r in results)
        assert "R3K" in {r.mutation for r in results}
        assert "Z9Q" in failed  # position out of range
        assert "K2" in failed   # malformed notation
        assert len(results) + len(failed) == 4

    def test_batch_rejects_dna_protein_mismatch(self) -> None:
        with pytest.raises(ValueError):
            gg.design_goldengate_batch("ATGAAACGTTAA", "WRONG", ["R3K"], enzyme="BsaI")

    def test_batch_extract_cds_integration(self) -> None:
        template = "TT" + "ATGAAACGTTAA" + "GG"
        cds = gg.extract_cds(template, 2)
        results, failed = gg.design_goldengate_batch(cds, "MKR*", ["R3K"], enzyme="BsaI")
        assert len(results) == 1 and not failed
        assert results[0].forward_seq.startswith("CTAGGGTCTCA")  # BsaI prefix inserted
