"""Codon-table validator: known-answer control plus one fixture per rule.

Two claims are tested and they are different claims.

(a) The tables kuma ships clear the validator with zero errors and zero
    warnings. That is the known-answer control; without it a validator that
    rejects everything would look like a strict one.

(b) For every rejection rule V9-V30 there is a fixture that fires exactly that
    rule and nothing else. Each test also asserts ``checks_performed > 0``, so a
    validator that examined nothing and reported "no defects" fails here.

Every negative fixture is the same complete, warning-free base table with one
thing perturbed.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from kuma_core.kuro import codon_table as codon_table_mod
from kuma_core.kuro.codon_import import (
    LOW_CDS_WARN_THRESHOLD,
    MESSAGE_CODES,
    ValidationContext,
    canonical_digest,
    validate_codon_table_data,
    validate_codon_table_file,
)

BUNDLED_DIR = codon_table_mod._RESOURCES_DIR
SHIPPED = {"bsubtilis", "ecoli", "hsapiens", "mextorquens", "scerevisiae"}


# ── base fixture ───────────────────────────────────────────────────────────

def _base_table() -> dict:
    """A complete user table: aliases, provenance and self-consistent counts.

    Built from the shipped M. extorquens frequencies rather than transcribed,
    then given integer counts and frequencies recomputed from them, so V27 has
    nothing to complain about and N4 is a no-op numerically.
    """
    src = json.loads(
        (BUNDLED_DIR / "mextorquens.json").read_text(encoding="utf-8")
    )
    counts: dict[str, list] = {}
    codons: dict[str, list] = {}
    for aa, pairs in src["codons"].items():
        raw = [(c, max(1, round(f * 100_000))) for c, f in pairs]
        total = sum(v for _, v in raw)
        counts[aa] = [[c, v] for c, v in raw]
        codons[aa] = [[c, round(v / total, 6)] for c, v in raw]
    return {
        "schema_version": 1,
        "key": "lab_strain",
        "name": "Lab strain AM1-derived",
        "taxid": 272630,
        "genetic_code": 11,
        "aliases": ["lab strain", "lab strain am1"],
        "source": "Derived from the bundled M. extorquens table for testing.",
        "provenance": {
            "method": "cds_count",
            "cds_counted": 6256,
            "codon_count": 1_930_715,
            "generated_by": "tests/test_codon_import.py",
        },
        "counts": counts,
        "codons": codons,
    }


def _report(mutate=None, *, stem="lab_strain", context=None):
    data = _base_table()
    if mutate is not None:
        mutate(data)
    return validate_codon_table_data(
        data, stem=stem, context=context or ValidationContext()
    )


def _assert_only(report, code: str) -> None:
    fired = report.error_codes + report.warning_codes
    assert fired == [code] or set(fired) == {code}, fired
    assert report.checks_performed > 0, "validator examined nothing"


# ── (a) known-answer control ───────────────────────────────────────────────

class TestShippedTablesPassClean:
    @pytest.mark.parametrize("stem", sorted(SHIPPED))
    def test_bundled_table_has_no_findings(self, stem):
        report = validate_codon_table_file(
            BUNDLED_DIR / f"{stem}.json", ValidationContext(is_builtin=True)
        )
        assert report.error_codes == [], report.errors
        assert report.warning_codes == [], report.warnings
        assert report.codons_examined == 64
        assert report.checks_performed > 300
        assert report.table_sha256 is not None

    def test_the_shipped_set_is_five(self):
        stems = {p.stem for p in BUNDLED_DIR.glob("*.json")}
        assert stems == SHIPPED

    def test_base_fixture_is_clean(self):
        # The negative fixtures are only meaningful if the thing they perturb
        # is itself clean.
        report = _report()
        assert report.error_codes == []
        assert report.warning_codes == []
        assert report.codons_examined == 64

    def test_seed_template_installs_clean(self, tmp_path):
        seed = (
            codon_table_mod._RESOURCES_DIR.parent
            / "codon_table_seeds"
            / "TEMPLATE.json.txt"
        )
        target = tmp_path / "example_strain.json"
        target.write_text(seed.read_text(encoding="utf-8"), encoding="utf-8")
        report = validate_codon_table_file(target, ValidationContext())
        assert report.error_codes == [], report.errors
        assert report.warning_codes == [], report.warnings


# ── (b) one fixture per file-level rule V1-V8 ──────────────────────────────

class TestFileLevelRules:
    def test_v1_wrong_extension(self, tmp_path):
        path = tmp_path / "lab_strain.txt"
        path.write_text("{}", encoding="utf-8")
        report = validate_codon_table_file(path, ValidationContext())
        _assert_only(report, "V1")

    def test_v2_too_large(self, tmp_path):
        path = tmp_path / "lab_strain.json"
        path.write_text(" " * 1_000_001, encoding="utf-8")
        report = validate_codon_table_file(path, ValidationContext())
        _assert_only(report, "V2")

    def test_v3_not_json(self, tmp_path):
        path = tmp_path / "lab_strain.json"
        path.write_text('{"codons": ,}', encoding="utf-8")
        report = validate_codon_table_file(path, ValidationContext())
        _assert_only(report, "V3")

    def test_v4_not_an_object(self, tmp_path):
        path = tmp_path / "lab_strain.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        report = validate_codon_table_file(path, ValidationContext())
        _assert_only(report, "V4")

    def test_v5_schema_from_the_future(self):
        _assert_only(_report(lambda d: d.update(schema_version=99)), "V5")

    def test_v6_unreadable(self, tmp_path):
        path = tmp_path / "lab_strain.json"
        report = validate_codon_table_file(path, ValidationContext())
        _assert_only(report, "V6")

    def test_v7_unusable_key(self):
        _assert_only(_report(lambda d: d.update(key="Lab-Strain")), "V7")

    def test_v8_key_disagrees_with_filename(self):
        _assert_only(_report(lambda d: d.update(key="other_strain")), "V8")


# ── (b) identity, genetic code, codon set, frequencies ─────────────────────

class TestIdentityRules:
    def test_v9_builtin_key_cannot_be_replaced(self):
        report = _report(
            lambda d: d.update(key="ecoli"),
            stem="ecoli",
            context=ValidationContext(
                builtin_keys={"ecoli": "Escherichia coli K-12"}
            ),
        )
        _assert_only(report, "V9")

    def test_v10_existing_user_key(self):
        report = _report(
            context=ValidationContext(
                existing_user_tables={
                    "lab_strain": {"name": "Older copy", "date": "2026-01-01",
                                   "sha8": "deadbeef"}
                }
            )
        )
        _assert_only(report, "V10")

    def test_v10_silent_when_overwriting(self):
        report = _report(
            context=ValidationContext(
                existing_user_tables={"lab_strain": {"name": "Older copy"}},
                overwrite=True,
            )
        )
        assert report.error_codes == []

    def test_v11_case_only_stem_collision(self):
        report = _report(
            context=ValidationContext(sibling_stems=("lab_strain", "Lab_Strain"))
        )
        _assert_only(report, "V11")

    def test_v12_no_display_name(self):
        _assert_only(_report(lambda d: d.update(name="   ")), "V12")

    def test_v13_bad_taxid(self):
        _assert_only(_report(lambda d: d.update(taxid="272630")), "V13")

    def test_v13_null_taxid_is_allowed(self):
        report = _report(lambda d: d.update(taxid=None))
        assert report.error_codes == []


class TestGeneticCodeRules:
    def test_v14_missing_genetic_code_warns_for_user_tables(self):
        _assert_only(_report(lambda d: d.pop("genetic_code")), "V14")

    def test_v15_non_standard_code_is_refused(self):
        # Mycoplasma (code 4) is out of scope on purpose: it changes how kuma
        # reads wild-type codons, so accepting it quietly would be wrong.
        _assert_only(_report(lambda d: d.update(genetic_code=4)), "V15")

    def test_v16_swapped_amino_acid_columns(self):
        def mutate(d):
            # Swap the codon strings between two amino acids, keeping the
            # fractions and the 64-codon set intact so only V16 can fire.
            d.pop("counts")
            f = d["codons"]["F"]
            y = d["codons"]["Y"]
            d["codons"]["F"] = [[y[i][0], f[i][1]] for i in range(len(f))]
            d["codons"]["Y"] = [[f[i][0], y[i][1]] for i in range(len(y))]
        _assert_only(_report(mutate), "V16")


class TestCodonSetRules:
    def test_v17_missing_amino_acid(self):
        def mutate(d):
            d.pop("counts")
            d["codons"].pop("W")
        _assert_only(_report(mutate), "V17")

    def test_v18_duplicated_codon(self):
        def mutate(d):
            d.pop("counts")
            # TTA -> CTG inside Leu: still Leu, so V16 stays silent, but CTG is
            # now listed twice and TTA is gone.
            d["codons"]["L"] = [
                ["CTG" if c == "TTA" else c, f] for c, f in d["codons"]["L"]
            ]
        _assert_only(_report(mutate), "V18")

    def test_v19_ambiguity_letters(self):
        def mutate(d):
            d.pop("counts")
            d["codons"]["W"] = [["NNN", 1.0]]
        _assert_only(_report(mutate), "V19")

    def test_v20_wrong_length(self):
        def mutate(d):
            d.pop("counts")
            d["codons"]["W"] = [["TG", 1.0]]
        _assert_only(_report(mutate), "V20")

    def test_n1_and_n2_normalise_without_error(self):
        def mutate(d):
            d.pop("counts")
            d["codons"]["W"] = [["ugg", 1.0]]
        report = _report(mutate)
        assert report.error_codes == []
        assert {f.code for f in report.normalizations} == {"N1", "N2"}
        assert report.table["W"] == [("TGG", 1.0)]


class TestFrequencyRules:
    def test_v21_out_of_range(self):
        def mutate(d):
            d.pop("counts")
            d["codons"]["W"] = [["TGG", 1.5]]
        _assert_only(_report(mutate), "V21")

    def test_v22_sum_far_from_one(self):
        def mutate(d):
            d.pop("counts")
            d["codons"]["D"] = [[c, f / 2] for c, f in d["codons"]["D"]]
        _assert_only(_report(mutate), "V22")

    def test_v23_sum_inside_tolerance_but_rounded(self):
        def mutate(d):
            d.pop("counts")
            pairs = d["codons"]["D"]
            total = sum(f for _, f in pairs)
            d["codons"]["D"] = [[c, f * 0.955 / total] for c, f in pairs]
        _assert_only(_report(mutate), "V23")

    def test_v24_no_usable_codon(self):
        def mutate(d):
            d.pop("counts")
            d["codons"]["D"] = [[c, 0.0] for c, _ in d["codons"]["D"]]
        _assert_only(_report(mutate), "V24")


class TestCountRules:
    def test_v25_negative_count(self):
        def mutate(d):
            d["counts"]["W"] = [["TGG", -1]]
        _assert_only(_report(mutate), "V25")

    def test_v26_count_codon_set_disagrees(self):
        def mutate(d):
            d["counts"]["W"] = [["TGA", d["counts"]["W"][0][1]]]
        _assert_only(_report(mutate), "V26")

    def test_v27_hand_edited_fraction(self):
        def mutate(d):
            # Swap two counts inside one amino acid: the count total and every
            # stored fraction stay put, only the implied ranking moves.
            pairs = d["counts"]["D"]
            pairs[0][1], pairs[1][1] = pairs[1][1], pairs[0][1]
        _assert_only(_report(mutate), "V27")

    def test_n4_recomputes_from_counts(self):
        report = _report()
        assert "N4" in {f.code for f in report.normalizations}


class TestAliasRules:
    def test_v28_empty_alias(self):
        _assert_only(_report(lambda d: d["aliases"].append("  ")), "V28")

    def test_v29_alias_is_another_tables_key(self):
        report = _report(
            lambda d: d["aliases"].append("ecoli"),
            context=ValidationContext(
                builtin_keys={"ecoli": "Escherichia coli K-12"}
            ),
        )
        _assert_only(report, "V29")

    def test_v30_alias_already_points_elsewhere(self):
        report = _report(
            lambda d: d["aliases"].append("human"),
            context=ValidationContext(builtin_aliases={"human": "hsapiens"}),
        )
        _assert_only(report, "V30")


class TestWarningRules:
    def test_v31_small_sample(self):
        def mutate(d):
            d["provenance"]["cds_counted"] = LOW_CDS_WARN_THRESHOLD - 1
        _assert_only(_report(mutate), "V31")

    def test_v32_no_provenance(self):
        _assert_only(_report(lambda d: d.pop("provenance")), "V32")

    def test_v33_no_aliases(self):
        _assert_only(_report(lambda d: d.update(aliases=[])), "V33")

    def test_v34_zero_fraction_codon(self):
        def mutate(d):
            d.pop("counts")
            pairs = d["codons"]["L"]
            # Move TTA's share onto CTC so the group still sums to 1.
            idx = [i for i, (c, _) in enumerate(pairs) if c == "TTA"][0]
            other = [i for i, (c, _) in enumerate(pairs) if c == "CTC"][0]
            pairs[other][1] += pairs[idx][1]
            pairs[idx][1] = 0.0
        _assert_only(_report(mutate), "V34")

    def test_v35_unknown_top_level_field(self):
        _assert_only(_report(lambda d: d.update(colour="blue")), "V35")

    def test_v34_is_exempt_for_bundled_tables(self):
        # Measured 2026-09-17: mextorquens.json lists TTA at 0.0. The design
        # note exempted only V32/V33 because it was written when four tables
        # shipped and none carried a zero.
        raw = json.loads(
            (BUNDLED_DIR / "mextorquens.json").read_text(encoding="utf-8")
        )
        zeros = [
            c for pairs in raw["codons"].values() for c, f in pairs if f == 0.0
        ]
        assert zeros == ["TTA"]
        report = validate_codon_table_file(
            BUNDLED_DIR / "mextorquens.json", ValidationContext(is_builtin=True)
        )
        assert "V34" not in report.warning_codes


class TestDigest:
    def test_digest_ignores_provenance(self):
        a = _report()
        b = _report(lambda d: d["provenance"].update(generated_at="2030-01-01"))
        assert a.table_sha256 == b.table_sha256

    def test_digest_follows_the_numbers(self):
        a = _report()
        table = copy.deepcopy(a.table)
        table["D"] = [(c, f + 0.001) for c, f in table["D"]]
        assert canonical_digest(table, 11) != a.table_sha256

    def test_every_code_is_reachable_by_name(self):
        assert len(MESSAGE_CODES) == 39
        assert MESSAGE_CODES[-4:] == ("N1", "N2", "N3", "N4")
