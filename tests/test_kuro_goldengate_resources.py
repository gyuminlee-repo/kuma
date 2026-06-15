"""L0 resource integrity + golden cross-check for KURO Golden Gate (Type IIS).

Validates the bundled Type IIS enzyme DB and the BsaI/BsmBI overhang-fidelity
score tables derived from NEB Potapov et al. 2018 (ACS Synth Biol 7(11):2665-2674)
Supplementary Table S1 (BsaI-HFv2, 37C) / Table S2 (BsmBI-v2, 42C), where
Score = on-target ligation frequency (overhang ligated to its reverse complement).

The golden cross-check asserts every overhang_score in the committed reference
results (`mutation_results_v4_golden.csv`, produced by the source mutation_tool)
equals the BsaI on-target score in our bundled table. Self-contained: depends only
on committed fixtures + bundled resources, never on the external xlsx.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from kuma_core.kuro import goldengate as gg

_KURO_RES = Path(__file__).resolve().parents[1] / "kuma_core" / "kuro" / "resources"
_ENZYME_DB = _KURO_RES / "enzymes" / "typeIIS.json"
_FIDELITY_DIR = _KURO_RES / "overhang_fidelity"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kuro_goldengate"
_GOLDEN = _FIXTURES / "mutation_results_v4_golden.csv"
_SCORE_FIXTURE = _FIXTURES / "BsaI_overhang_fidelity.csv"

_DNA = set("ACGT")


def _load_scores(path: Path) -> dict[str, int]:
    scores: dict[str, int] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == ["overhang", "Score"], (path, reader.fieldnames)
        for row in reader:
            scores[row["overhang"]] = int(row["Score"])
    return scores


class TestEnzymeDb:
    """typeIIS.json must define well-formed Type IIS enzyme records."""

    def test_schema_and_values(self) -> None:
        enzymes = json.loads(_ENZYME_DB.read_text(encoding="utf-8"))
        assert isinstance(enzymes, list) and enzymes
        names = {e["name"] for e in enzymes}
        # The four catalog enzymes the plan seeds (incl. SapI for variable overhang_len).
        assert {"BsaI", "BsmBI", "BbsI", "SapI"} <= names
        by_name = {e["name"]: e for e in enzymes}

        for e in enzymes:
            for key in ("name", "recognition", "cut_offset", "overhang_len", "prefix", "fidelity_table"):
                assert key in e, (e["name"], key)
            assert set(e["recognition"]) <= _DNA, e["name"]
            assert set(e["prefix"]) <= _DNA, e["name"]
            top, bottom = e["cut_offset"]
            assert isinstance(top, int) and isinstance(bottom, int)
            assert bottom - top == e["overhang_len"], (
                e["name"],
                e["cut_offset"],
                e["overhang_len"],
            )
            # The recognition site must appear in the prefix (the site is *inserted*).
            assert e["recognition"] in e["prefix"], e["name"]

        # BsaI prefix must match the source tool exactly (golden reproduction depends on it).
        assert by_name["BsaI"]["prefix"] == "CTAGGGTCTCA"
        assert by_name["BsaI"]["overhang_len"] == 4
        # SapI exercises the variable (3 nt) overhang path; must not be hardcoded to 4.
        assert by_name["SapI"]["overhang_len"] == 3


class TestFidelityTables:
    """BsaI/BsmBI score tables must be complete 256-overhang on-target tables."""

    @pytest.mark.parametrize("enzyme", ["BsaI", "BsmBI"])
    def test_complete_and_valid(self, enzyme: str) -> None:
        scores = _load_scores(_FIDELITY_DIR / f"{enzyme}.csv")
        assert len(scores) == 256, enzyme
        for oh, sc in scores.items():
            assert len(oh) == 4 and set(oh) <= _DNA, oh
            assert isinstance(sc, int) and sc >= 0, (oh, sc)

    def test_bsai_self_complementary_present(self) -> None:
        # Palindromic (self-complementary) overhangs ligate to themselves; their
        # on-target score is well-defined and present in the table.
        scores = _load_scores(_FIDELITY_DIR / "BsaI.csv")
        for pal in ("AATT", "ACGT", "AGCT", "GATC"):
            assert pal in scores

    @pytest.mark.parametrize("enzyme", ["BsaI", "BsmBI"])
    def test_on_target_is_rc_symmetric(self, enzyme: str) -> None:
        # on-target(X) = freq(X ligated to rc(X)); the X--rc(X) ligation event is
        # physically identical to rc(X)--X, so the table must satisfy
        # score[oh] == score[rc(oh)] for every overhang.
        scores = _load_scores(_FIDELITY_DIR / f"{enzyme}.csv")
        rc = str.maketrans("ACGT", "TGCA")
        for oh, sc in scores.items():
            partner = oh.translate(rc)[::-1]
            assert scores[partner] == sc, (enzyme, oh, partner, sc, scores[partner])


class TestGoldenCrossCheck:
    """Every reference overhang_score must equal our bundled BsaI on-target score."""

    def test_committed_fixture_matches_resource(self) -> None:
        # The independent score fixture must be data-equal to the shipped resource.
        assert _load_scores(_SCORE_FIXTURE) == _load_scores(_FIDELITY_DIR / "BsaI.csv")

    def test_all_golden_overhang_scores_reproduced(self) -> None:
        scores = _load_scores(_FIDELITY_DIR / "BsaI.csv")
        checked = 0
        with _GOLDEN.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                overhang = row["overhang"].strip().upper()
                raw = row["overhang_score"].strip()
                if not overhang or not raw:
                    continue
                assert scores.get(overhang) == int(raw), (
                    row["mutation"],
                    overhang,
                    raw,
                    scores.get(overhang),
                )
                checked += 1
        # All 96 success rows of the source golden run carry a scored overhang.
        assert checked == 96

    def test_golden_positions_present(self) -> None:
        positions = set()
        with _GOLDEN.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                positions.add(int(row["position_1based"]))
        assert positions == {30, 60, 90, 110, 130, 150, 180, 211}

# A tiny self-contained CDS used by the custom-enzyme + junction behavior tests.
# A tiny self-contained CDS used by the custom-enzyme + junction behavior tests.
# M K R * ; R3K is a valid, designable mutation (verified against the engine).
_DNA_CDS = "ATGAAACGTTAA"
_PROTEIN = "MKR*"


class TestCustomEnzymeEngine:
    """load_enzyme_db merge + save_custom_enzyme persistence + fault isolation."""

    def test_custom_merge_and_name_override(self, tmp_path) -> None:
        custom = tmp_path / "custom_enzymes.json"
        # A brand-new enzyme plus a BsaI override (same name => overrides built-in).
        custom.write_text(
            json.dumps([
                {
                    "name": "MyTypeIIS",
                    "recognition": "GGTCTC",
                    "cut_offset": [1, 5],
                    "overhang_len": 4,
                    "prefix": "CTAGGGTCTCA",
                    "fidelity_table": "BsaI.csv",
                },
                {
                    "name": "BsaI",
                    "recognition": "GGTCTC",
                    "cut_offset": [1, 5],
                    "overhang_len": 4,
                    "prefix": "AAAGGTCTCAA",  # different from the bundled prefix
                    "fidelity_table": "BsaI.csv",
                },
            ]),
            encoding="utf-8",
        )
        builtin = gg.load_enzyme_db()
        merged = gg.load_enzyme_db(custom_path=custom)
        # New enzyme merged in; built-ins survive.
        assert "MyTypeIIS" in merged
        assert {"BsaI", "BsmBI", "BbsI", "SapI", "PaqCI", "BspMI"} <= set(merged)
        # Same-name custom entry overrides the built-in definition.
        assert builtin["BsaI"].prefix == "CTAGGGTCTCA"
        assert merged["BsaI"].prefix == "AAAGGTCTCAA"

    def test_save_custom_enzyme_roundtrip_uppercases(self, tmp_path) -> None:
        path = tmp_path / "custom_enzymes.json"
        enz = gg.save_custom_enzyme(
            {
                "name": "RoundTrip",
                "recognition": "gctcttc",   # lowercase input
                "cut_offset": [1, 4],
                "overhang_len": 3,
                "prefix": "aaagctcttca",     # lowercase input
            },
            path,
        )
        # Returned object normalizes case.
        assert enz.recognition == "GCTCTTC"
        assert enz.prefix == "AAAGCTCTTCA"
        # Persisted and reloadable.
        db = gg.load_enzyme_db(custom_path=path)
        assert "RoundTrip" in db
        assert db["RoundTrip"].recognition == "GCTCTTC"
        assert db["RoundTrip"].prefix == "AAAGCTCTTCA"

    def test_save_custom_enzyme_updates_existing_by_name(self, tmp_path) -> None:
        path = tmp_path / "custom_enzymes.json"
        gg.save_custom_enzyme(
            {"name": "Dup", "recognition": "GGTCTC", "cut_offset": [1, 5],
             "overhang_len": 4, "prefix": "CTAGGGTCTCA"},
            path,
        )
        gg.save_custom_enzyme(
            {"name": "Dup", "recognition": "GAAGAC", "cut_offset": [2, 6],
             "overhang_len": 4, "prefix": "AAAGAAGACAA"},
            path,
        )
        stored = json.loads(path.read_text(encoding="utf-8"))
        dups = [e for e in stored if e["name"] == "Dup"]
        assert len(dups) == 1  # updated in place, not appended
        assert dups[0]["recognition"] == "GAAGAC"

    def test_save_custom_enzyme_rejects_non_dna_recognition(self, tmp_path) -> None:
        path = tmp_path / "custom_enzymes.json"
        with pytest.raises(ValueError):
            gg.save_custom_enzyme(
                {"name": "Bad", "recognition": "GGXTCC", "cut_offset": [1, 5],
                 "overhang_len": 4, "prefix": "CTAGGGTCTCA"},
                path,
            )
        assert not path.exists()  # nothing written on validation failure

    def test_corrupt_custom_file_degrades_to_builtin(self, tmp_path) -> None:
        path = tmp_path / "custom_enzymes.json"
        path.write_text("{ this is not valid json", encoding="utf-8")
        db = gg.load_enzyme_db(custom_path=path)  # must not raise
        # Exactly the bundled six survive.
        assert set(db) == {"BsaI", "BsmBI", "BbsI", "SapI", "PaqCI", "BspMI"}

    def test_mixed_valid_invalid_entries_skips_only_bad(self, tmp_path) -> None:
        path = tmp_path / "custom_enzymes.json"
        path.write_text(
            json.dumps([
                {"name": "GoodE", "recognition": "GGTCTC", "cut_offset": [1, 5],
                 "overhang_len": 4, "prefix": "CTAGGGTCTCA"},
                {"name": "BadE", "recognition": "XYZ", "cut_offset": [1, 5],
                 "overhang_len": 4, "prefix": "CTA"},  # non-DNA recognition
            ]),
            encoding="utf-8",
        )
        db = gg.load_enzyme_db(custom_path=path)
        assert "GoodE" in db
        assert "BadE" not in db
        # Built-ins still present (one bad entry never poisons the catalog).
        assert "BsaI" in db

    def test_design_with_custom_enzyme(self, tmp_path) -> None:
        path = tmp_path / "custom_enzymes.json"
        gg.save_custom_enzyme(
            {"name": "MyBsa", "recognition": "GGTCTC", "cut_offset": [1, 5],
             "overhang_len": 4, "prefix": "CTAGGGTCTCA", "fidelity_table": "BsaI.csv"},
            path,
        )
        db = gg.load_enzyme_db(custom_path=path)
        out = gg.design_goldengate(_DNA_CDS, _PROTEIN, ["R3K"], enzyme="MyBsa", enzyme_db=db)
        assert len(out) == 1
        r = out[0]
        assert r.status == "success"
        assert r.enzyme == "MyBsa"
        assert r.forward_seq.startswith("CTAGGGTCTCA")
        assert len(r.overhang) == 4


class TestJunctionGeometry:
    """prefix_override / forbidden_overhangs / prefix-geometry validation."""

    def test_prefix_override_applied_to_all_success_primers(self) -> None:
        override = "GGGGGGGGGGG"
        out = gg.design_goldengate(
            _DNA_CDS, _PROTEIN, ["R3K"], enzyme="BsaI", prefix_override=override,
        )
        success = [r for r in out if r.status == "success"]
        assert success  # at least one designable mutation
        for r in success:
            assert r.forward_seq.startswith(override)
            assert r.reverse_seq.startswith(override)

    def test_prefix_override_bad_geometry_surfaced_in_warnings(self) -> None:
        # Override without the BsaI recognition site => geometry warning on results.
        out = gg.design_goldengate(
            _DNA_CDS, _PROTEIN, ["R3K"], enzyme="BsaI", prefix_override="GGGGGGGGGGG",
        )
        r = out[0]
        assert any("recognition site" in w for w in r.warnings)

    def test_default_prefix_is_catalog_prefix(self) -> None:
        out = gg.design_goldengate(_DNA_CDS, _PROTEIN, ["R3K"], enzyme="BsaI")
        success = [r for r in out if r.status == "success"]
        assert success
        enz = gg.get_enzyme("BsaI")
        for r in success:
            assert r.forward_seq.startswith(enz.prefix)
        # No prefix_override => no geometry warning emitted.
        assert not any("recognition site" in w for r in out for w in r.warnings)

    def test_default_forbidden_overhangs_constant(self) -> None:
        assert gg.DEFAULT_FORBIDDEN_OVERHANGS == ["AATG", "AGGT"]

    def test_forbidden_overhang_is_excluded(self) -> None:
        base = gg.design_goldengate(_DNA_CDS, _PROTEIN, ["R3K"], enzyme="BsaI")
        chosen = base[0].overhang
        assert base[0].status == "success" and chosen
        # Forbid the overhang the default run picked; a different one must be used.
        out = gg.design_goldengate(
            _DNA_CDS, _PROTEIN, ["R3K"], enzyme="BsaI", forbidden_overhangs=[chosen],
        )
        r = out[0]
        if r.status == "success":
            assert r.overhang != chosen
        assert r.overhang != chosen  # forbidden overhang never selected

    def test_validate_prefix_geometry_catalog_clean(self) -> None:
        enz = gg.get_enzyme("BsaI")
        assert gg._validate_prefix_geometry(enz.prefix, enz) == []

    def test_validate_prefix_geometry_missing_recognition_warns(self) -> None:
        enz = gg.get_enzyme("BsaI")
        warnings = gg._validate_prefix_geometry("GGGGGGGGGGG", enz)
        assert warnings
        assert any("recognition site" in w for w in warnings)
