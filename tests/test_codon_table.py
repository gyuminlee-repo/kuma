"""Tests for codon usage table and codon selection utilities."""

from __future__ import annotations

import pytest

from kuma_core.kuro.codon_table import (
    CODON_TO_AA,
    ECOLI_CODON_USAGE,
    CodonTableRegistry,
    best_codon,
    closest_codon,
    codon_to_aa,
    get_codon_table,
    codon_usage_fraction,
    mt_codons_for_design,
    resolve_organism_key,
)


STANDARD_20_AA = "ACDEFGHIKLMNPQRSTVWY"

# Canonical keys of the tables shipped in resources/codon_tables/.
SHIPPED_ORGANISMS = {"ecoli", "bsubtilis", "scerevisiae", "hsapiens", "mextorquens"}

# Amino acid groups whose rounded fractions sum further than 0.02 from 1.00.
# Empty: every shipped group is now within tolerance. The hsapiens Ser entry
# that used to sit here was a transcription defect, not a rounding artifact,
# and was repaired against Kazusa 9606 rather than exempted.
#
# The mechanism stays because a future table can legitimately need it: six
# synonymous codons each rounded to 2 decimals can sum as far as 0.03 from
# 1.00 with every individual cell faithful to its source.
_SUM_TOLERANCE_EXEMPTIONS: set[tuple[str, str]] = set()


class TestBestCodon:
    def test_all_20_amino_acids_return_valid_codon(self):
        for aa in STANDARD_20_AA:
            codon = best_codon(aa)
            assert len(codon) == 3
            assert all(base in "ACGT" for base in codon)

    def test_best_codon_encodes_correct_aa(self):
        for aa in STANDARD_20_AA:
            codon = best_codon(aa)
            assert codon_to_aa(codon) == aa

    def test_best_codon_is_highest_frequency(self):
        for aa in STANDARD_20_AA:
            codons = ECOLI_CODON_USAGE[aa]
            max_freq = max(freq for _, freq in codons)
            result = best_codon(aa)
            freq_of_result = dict(codons)[result]
            assert freq_of_result == max_freq

    def test_stop_codon(self):
        codon = best_codon("*")
        assert codon == "TAA"  # most frequent stop in E. coli

    def test_lowercase_input(self):
        assert best_codon("a") == best_codon("A")

    def test_invalid_amino_acid_raises(self):
        with pytest.raises(ValueError, match="Invalid amino acid"):
            best_codon("X")

    def test_invalid_amino_acid_digit_raises(self):
        with pytest.raises(ValueError, match="Invalid amino acid"):
            best_codon("1")

    def test_organism_kwarg_accepted(self):
        # organism kwarg is now valid — should return a valid codon
        codon = best_codon("A", organism="yeast")
        assert len(codon) == 3
        assert codon_to_aa(codon) == "A"


class TestCodonToAA:
    def test_all_codons_mapped(self):
        assert len(CODON_TO_AA) == 64

    def test_start_codon(self):
        assert CODON_TO_AA["ATG"] == "M"

    def test_stop_codons(self):
        for stop in ["TAA", "TAG", "TGA"]:
            assert CODON_TO_AA[stop] == "*"

    def test_codon_to_aa_function(self):
        assert codon_to_aa("ATG") == "M"
        assert codon_to_aa("GCG") == "A"

    def test_lowercase_codon_accepted(self):
        assert codon_to_aa("atg") == "M"

    def test_invalid_codon_raises(self):
        with pytest.raises(ValueError, match="Invalid codon"):
            codon_to_aa("XYZ")

    def test_too_short_codon_raises(self):
        with pytest.raises(ValueError, match="Invalid codon"):
            codon_to_aa("AT")


class TestClosestCodon:
    def test_same_codon_returns_itself(self):
        # GCG -> A; closest A codon to GCG is GCG itself
        assert closest_codon("GCG", "A") == "GCG"

    def test_one_base_change(self):
        # AAA encodes K; closest L codon should minimize hamming distance
        result = closest_codon("AAA", "L")
        assert codon_to_aa(result) == "L"

    def test_prefers_higher_frequency_at_same_distance(self):
        # For two codons equidistant from wt_codon, the higher-frequency one wins
        result = closest_codon("AAA", "A")
        assert codon_to_aa(result) == "A"
        # Verify it picks the best among equidistant options
        assert result in [c for c, _ in ECOLI_CODON_USAGE["A"]]

    def test_invalid_target_aa_raises(self):
        with pytest.raises(ValueError, match="Invalid amino acid"):
            closest_codon("ATG", "X")

    def test_lowercase_inputs_accepted(self):
        upper = closest_codon("GCG", "A")
        lower = closest_codon("gcg", "a")
        assert upper == lower


class TestMtCodonsForDesign:
    """The pool the design engine receives.

    It used to be [closest, optimal] and is now every synonymous codon the host
    uses at least CODON_USAGE_FLOOR of the time, WT excluded. Floor, ordering
    and the inert ``strategy`` argument are pinned in tests/test_codon_pool.py;
    these keep the plain contract the rest of this file relies on.
    """

    def test_every_offered_codon_encodes_the_target(self):
        codons = mt_codons_for_design("AAA", "A", strategy="closest")
        assert len(codons) >= 1
        for c in codons:
            assert codon_to_aa(c) == "A"

    def test_the_whole_synonymous_set_is_offered(self):
        # E. coli uses all four Ala codons above the floor and none of them is
        # the WT codon here, so the pool is the full set rather than two of it.
        codons = mt_codons_for_design("AAA", "A", strategy="closest")
        assert sorted(codons) == ["GCA", "GCC", "GCG", "GCT"]
        assert len(set(codons)) == len(codons)

    def test_a_silent_request_drops_the_wt_codon(self):
        # GCG->A is silent: re-emitting GCG is not a mutation, so it is dropped
        # and the other three Ala codons remain.
        codons = mt_codons_for_design("GCG", "A", strategy="closest")
        assert "GCG" not in codons
        assert sorted(codons) == ["GCA", "GCC", "GCT"]

    def test_methionine_always_returns_one(self):
        # M has only one codon (ATG)
        codons = mt_codons_for_design("TTT", "M")
        assert codons == ["ATG"]

    def test_tryptophan_always_returns_one(self):
        # W has only one codon (TGG)
        codons = mt_codons_for_design("TTT", "W")
        assert codons == ["TGG"]

    def test_organism_parameter_changes_result(self):
        # E. coli best A codon is GCG; yeast best A codon is GCT
        ecoli_codons = mt_codons_for_design("AAA", "A", organism="ecoli")
        yeast_codons = mt_codons_for_design("AAA", "A", organism="scerevisiae")
        # The optimal codons should differ
        ecoli_optimal = best_codon("A", "ecoli")
        yeast_optimal = best_codon("A", "scerevisiae")
        assert ecoli_optimal != yeast_optimal
        # Both should encode A
        assert codon_to_aa(ecoli_codons[0]) == "A"
        assert codon_to_aa(yeast_codons[0]) == "A"


class TestResolveOrganismKey:
    @pytest.mark.parametrize(
        ("annotation", "expected"),
        [
            ("ecoli", "ecoli"),
            (" E. coli ", "ecoli"),
            ("Escherichia coli", "ecoli"),
            ("Bacillus subtilis", "bsubtilis"),
            ("Saccharomyces cerevisiae", "scerevisiae"),
            ("Homo sapiens", "hsapiens"),
        ],
    )
    def test_supported_annotation_resolves_to_canonical_key(
        self, annotation: str, expected: str
    ):
        assert resolve_organism_key(annotation) == expected

    @pytest.mark.parametrize(
        "annotation",
        [None, "", "   ", "synthetic construct", "unknown organism"],
    )
    def test_unsupported_or_blank_annotation_returns_none(
        self, annotation: str | None
    ):
        assert resolve_organism_key(annotation) is None


class TestCodonTableRegistry:
    def test_list_organisms_returns_shipped_set(self):
        registry = CodonTableRegistry()
        organisms = registry.list_organisms()
        assert len(organisms) == 5
        assert set(organisms) == SHIPPED_ORGANISMS

    def test_list_organisms_includes_mextorquens(self):
        # D3: the table has to be discoverable, not merely present on disk
        registry = CodonTableRegistry()
        assert "mextorquens" in registry.list_organisms()

    def test_list_organisms_detailed_has_keys(self):
        registry = CodonTableRegistry()
        details = registry.list_organisms_detailed()
        assert len(details) == 5
        for item in details:
            assert "key" in item
            assert "name" in item
            assert "taxid" in item

    def test_taxid_less_table_still_lists(self, tmp_path, monkeypatch):
        """A table JSON without a "taxid" key must list, not poison the list.

        list_organisms_detailed reports data.get("taxid"), so an in-house
        strain that never got an NCBI taxid reports None. The frontend
        validates this payload element by element through isArrayOf, so an
        entry that fails the guard rejects the whole array and empties the
        organism dropdown. Keep the None-bearing entry present and keep its
        neighbours intact.
        """
        import json
        import shutil

        import kuma_core.kuro.codon_table as codon_table_mod

        src = codon_table_mod._RESOURCES_DIR / "ecoli.json"
        shutil.copy(src, tmp_path / "ecoli.json")

        data = json.loads(src.read_text(encoding="utf-8"))
        data["name"] = "In-house strain"
        data.pop("taxid", None)
        (tmp_path / "inhouse.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        monkeypatch.setattr(codon_table_mod, "_RESOURCES_DIR", tmp_path)
        registry = CodonTableRegistry()

        details = registry.list_organisms_detailed()
        by_key = {item["key"]: item for item in details}

        assert set(by_key) == {"ecoli", "inhouse"}
        assert by_key["inhouse"]["taxid"] is None
        assert by_key["inhouse"]["name"] == "In-house strain"
        # The taxid-less neighbour must not cost the well-formed entry.
        assert by_key["ecoli"]["taxid"] == 83333

    def test_get_codon_table_ecoli(self):
        table = get_codon_table("ecoli")
        assert "A" in table
        assert "M" in table
        assert "*" in table
        # All 20 AA + stop
        assert len(table) == 21

    def test_get_codon_table_all_organisms(self):
        registry = CodonTableRegistry()
        for org in registry.list_organisms():
            table = registry.get_codon_table(org)
            assert len(table) == 21
            # Each AA should have at least one codon
            for aa, codons in table.items():
                assert len(codons) >= 1
                # Frequencies should sum close to 1.0
                total = sum(freq for _, freq in codons)
                assert 0.95 <= total <= 1.05, f"{org}/{aa}: freq sum={total}"

    def test_alias_resolution(self):
        registry = CodonTableRegistry()
        t1 = registry.get_codon_table("ecoli")
        t2 = registry.get_codon_table("E. coli")
        t3 = registry.get_codon_table("Escherichia coli")
        assert t1 is t2  # same cached object
        assert t1 is t3

    def test_unknown_organism_raises(self):
        registry = CodonTableRegistry()
        with pytest.raises(ValueError, match="Unknown organism"):
            registry.get_codon_table("nonexistent_organism")

    def test_ecoli_backward_compatible(self):
        # ECOLI_CODON_USAGE constant should match get_codon_table("ecoli")
        table = get_codon_table("ecoli")
        assert table == ECOLI_CODON_USAGE

    def test_best_codon_per_organism(self):
        # E. coli: best A = GCG (GC-rich preference)
        assert best_codon("A", "ecoli") == "GCG"
        # Yeast: best A = GCT (AT-rich preference)
        assert best_codon("A", "scerevisiae") == "GCT"
        # Human: best A = GCC
        assert best_codon("A", "hsapiens") == "GCC"

    def test_closest_codon_per_organism(self):
        # Same target but different organisms may pick different codons
        ecoli_closest = closest_codon("AAA", "A", organism="ecoli")
        yeast_closest = closest_codon("AAA", "A", organism="scerevisiae")
        assert codon_to_aa(ecoli_closest) == "A"
        assert codon_to_aa(yeast_closest) == "A"



class TestEcoliHistidineOrdering:
    """Regression test for D1: the E. coli His pair was inverted.

    Kazusa E. coli W3110 raw counts are CAT 17,791 and CAC 13,399, so CAT is
    0.5704 and is the more used codon. The table shipped CAC 0.57 / CAT 0.43.
    """

    def test_cat_listed_before_cac(self):
        codons = [codon for codon, _ in ECOLI_CODON_USAGE["H"]]
        assert codons.index("CAT") < codons.index("CAC")

    def test_cat_carries_the_higher_fraction(self):
        freqs = dict(ECOLI_CODON_USAGE["H"])
        assert freqs["CAT"] == 0.57
        assert freqs["CAC"] == 0.43

    def test_best_codon_is_cat(self):
        assert best_codon("H", "ecoli") == "CAT"

    def test_optimal_design_codon_is_cat(self):
        # A His codon resynthesised under the "optimal" strategy now emits CAT
        assert mt_codons_for_design("CAC", "H", strategy="optimal")[0] == "CAT"


class TestShippedTableStructure:
    """Structural guard over every table in resources/codon_tables/.

    D2 shipped a B. subtilis table of unknown provenance. These checks do not
    judge the numbers, they pin the shape every consumer relies on: a complete
    genetic code, one amino acid per codon, and fractions that behave like
    fractions.
    """

    @pytest.mark.parametrize("organism", sorted(SHIPPED_ORGANISMS))
    def test_has_21_amino_acid_keys(self, organism: str):
        table = get_codon_table(organism)
        assert len(table) == 21
        assert set(table) == set(STANDARD_20_AA) | {"*"}

    @pytest.mark.parametrize("organism", sorted(SHIPPED_ORGANISMS))
    def test_has_64_distinct_codons(self, organism: str):
        table = get_codon_table(organism)
        codons = [codon for entries in table.values() for codon, _ in entries]
        assert len(codons) == 64
        assert len(set(codons)) == 64

    @pytest.mark.parametrize("organism", sorted(SHIPPED_ORGANISMS))
    def test_codons_agree_with_the_genetic_code(self, organism: str):
        # CODON_TO_AA is built from the E. coli table, so this also catches a
        # codon filed under the wrong amino acid in any other table.
        table = get_codon_table(organism)
        for aa, entries in table.items():
            for codon, _ in entries:
                assert CODON_TO_AA[codon] == aa, f"{organism}: {codon} under {aa}"

    @pytest.mark.parametrize("organism", sorted(SHIPPED_ORGANISMS))
    def test_fractions_are_within_zero_and_one(self, organism: str):
        table = get_codon_table(organism)
        for aa, entries in table.items():
            for codon, freq in entries:
                assert isinstance(freq, float)
                assert 0.0 <= freq <= 1.0, f"{organism}/{aa}/{codon}: {freq}"

    @pytest.mark.parametrize("organism", sorted(SHIPPED_ORGANISMS))
    def test_each_group_sums_to_one_within_two_hundredths(self, organism: str):
        table = get_codon_table(organism)
        for aa, entries in table.items():
            if (organism, aa) in _SUM_TOLERANCE_EXEMPTIONS:
                continue
            total = sum(freq for _, freq in entries)
            assert abs(total - 1.0) <= 0.02, f"{organism}/{aa}: freq sum={total}"


class TestMextorquensTable:
    """Regression test for D3: an AM1 user used to fall back to E. coli.

    The module docstring claimed M. extorquens support while no table and no
    alias existed, so resolve_organism_key returned None and the caller kept
    the E. coli default.
    """

    @pytest.mark.parametrize(
        "annotation",
        [
            "mextorquens",
            "M. extorquens",
            "m.extorquens",
            "Methylorubrum extorquens",
            "Methylorubrum extorquens AM1",
            "Methylobacterium extorquens",
            " Methylobacterium extorquens AM1 ",
        ],
    )
    def test_both_genus_spellings_resolve_to_one_key(self, annotation: str):
        assert resolve_organism_key(annotation) == "mextorquens"

    def test_both_genus_spellings_reach_the_same_table(self):
        registry = CodonTableRegistry()
        methylorubrum = registry.get_codon_table("Methylorubrum extorquens")
        methylobacterium = registry.get_codon_table("Methylobacterium extorquens AM1")
        assert methylorubrum is methylobacterium

    def test_table_is_not_the_ecoli_fallback(self):
        # AM1 is GC-rich and E. coli is not, so Lys and Glu separate them:
        # AM1 reads AAG 0.89 / GAG 0.79 where E. coli reads AAA 0.76 / GAA 0.68.
        assert best_codon("K", "mextorquens") == "AAG"
        assert best_codon("E", "mextorquens") == "GAG"
        assert best_codon("K", "ecoli") == "AAA"
        assert best_codon("E", "ecoli") == "GAA"
        assert get_codon_table("mextorquens") != ECOLI_CODON_USAGE


class TestRoundedTieOrdering:
    """Pin the two picks that rounding leaves to array order.

    best_codon takes max(), which returns the first maximum, so where two
    codons round to the same 2-decimal fraction the JSON order alone decides.
    Both picks below are the genuinely more frequent codon in the raw counts;
    a reformatter that re-sorted either group would silently change designed
    primers with nothing else failing.
    """

    def test_bsubtilis_leucine_prefers_ctg(self):
        # RefSeq ASM904v1: CTG 28,686 vs CTT 28,582, both 0.24 rounded
        assert best_codon("L", "bsubtilis") == "CTG"

    def test_mextorquens_leucine_prefers_ctc(self):
        # RefSeq ASM2268v1, all 5 replicons: CTC 87,117 vs CTG 86,425, both
        # 0.44 rounded. The chromosome alone reverses the order, so the
        # all-replicon count is the recorded choice.
        assert best_codon("L", "mextorquens") == "CTC"

    def test_hsapiens_arginine_prefers_aga(self):
        # Kazusa 9606: AGA 494,682 vs AGG 486,463, both 0.21 rounded.
        assert best_codon("R", "hsapiens") == "AGA"

    def test_hsapiens_arginine_lists_aga_before_agg(self):
        # The fractions are equal at 2 decimals, so only this array order
        # keeps max() on the codon the raw counts actually favour.
        codons = [codon for codon, _ in get_codon_table("hsapiens")["R"]]
        assert codons.index("AGA") < codons.index("AGG")


class TestHsapiensArginine:
    """Regression test for the hsapiens Arg group, which promoted CGG.

    Kazusa 9606 (93,487 CDS, 40,662,582 codons) counts AGA 494,682,
    AGG 486,463 and CGG 464,485, giving 0.21 / 0.21 / 0.20. The table shipped
    CGG 0.21 first with AGA and AGG at 0.20, so best_codon returned CGG and
    CGG also outranked AGG in every equidistant closest_codon race.
    """

    def test_best_codon_is_aga(self):
        assert best_codon("R", "hsapiens") == "AGA"

    def test_cgg_ranks_below_both_ag_codons(self):
        codons = [codon for codon, _ in get_codon_table("hsapiens")["R"]]
        assert codons.index("AGA") < codons.index("CGG")
        assert codons.index("AGG") < codons.index("CGG")

    def test_the_design_pool_leads_with_aga_where_distance_ties(self):
        # The pool orders by hamming distance first and only then by usage, so
        # the repair shows in the order wherever distance cannot decide. GGT is
        # two changes from AGA, AGG and CGG alike, which leaves the fractions to
        # break the tie; before the repair CGG's inflated 0.21 led here.
        picked = mt_codons_for_design("GGT", "R", organism="hsapiens")
        assert picked[0] == "AGA"
        assert picked.index("AGA") < picked.index("CGG")
        assert codon_usage_fraction("AGA", "hsapiens") > codon_usage_fraction(
            "CGG", "hsapiens"
        )

    @pytest.mark.parametrize(
        "wt_codon", ["TTG", "TCG", "TAG", "TGG", "GTG", "GCG", "GAG", "GGG"]
    )
    def test_equidistant_race_against_cgg_now_picks_agg(self, wt_codon: str):
        # These eight WT codons are the same hamming distance from CGG and
        # AGG. AGG carries the higher fraction once CGG is no longer inflated,
        # so it wins the tiebreak; before the repair all eight returned CGG.
        assert closest_codon(wt_codon, "R", organism="hsapiens") == "AGG"


class TestHsapiensSerine:
    """Regression test for the hsapiens Ser group, which summed to 0.97.

    Kazusa 9606 Ser is AGC 0.24, TCC 0.22, TCT 0.19, TCA 0.15, AGT 0.15 and
    TCG 0.05, summing to exactly 1.00. The table shipped TCT at 0.15 and TCG
    at 0.06, and the whole 0.03 shortfall lived in those two cells rather than
    in six simultaneous round-downs. The structural sum check used to skip
    this group by name.
    """

    def test_group_sums_to_one_within_the_standard_tolerance(self):
        entries = get_codon_table("hsapiens")["S"]
        total = sum(freq for _, freq in entries)
        assert abs(total - 1.0) <= 0.02, f"hsapiens/S: freq sum={total}"

    def test_group_carries_no_sum_tolerance_exemption(self):
        assert ("hsapiens", "S") not in _SUM_TOLERANCE_EXEMPTIONS

    def test_tct_and_tcg_carry_the_kazusa_fractions(self):
        freqs = dict(get_codon_table("hsapiens")["S"])
        assert freqs["TCT"] == 0.19
        assert freqs["TCG"] == 0.05

    def test_best_codon_is_unchanged(self):
        # TCT rising from 0.15 to 0.19 leaves AGC 0.24 on top, which is why
        # repairing Ser alone moved no design decision.
        assert best_codon("S", "hsapiens") == "AGC"
