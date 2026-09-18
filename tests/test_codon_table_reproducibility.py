"""Phase 2: what a run manifest has to say about the codon table it used.

The hole this closes is stated in section 8.1 of the design note: a manifest
recorded ``organism`` as a bare word, so two machines holding different files
under one key produced different primers from two manifests that read
identically. The table now travels as a canonical digest, and a user-installed
one also as a hashed input file.

The known-answer pair at the bottom is the point of the file. One case differs
only in the numbers and has to separate; the control differs only in
paperwork and has to stay together. A digest that changed on both would look
just as "working" as one that changed on neither.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python-core"))

from kuma_core.kuro import codon_table as codon_table_mod  # noqa: E402
from kuma_core.kuro.codon_import import (  # noqa: E402
    ValidationContext,
    validate_codon_table_file,
)

SHIPPED = {"bsubtilis", "ecoli", "hsapiens", "mextorquens", "scerevisiae"}


def _ecoli_codons() -> dict:
    return json.loads(
        (codon_table_mod._RESOURCES_DIR / "ecoli.json").read_text(encoding="utf-8")
    )["codons"]


def _user_table(key: str, **overrides) -> dict:
    data = {
        "schema_version": 1,
        "key": key,
        "name": f"Lab table {key}",
        "taxid": None,
        "genetic_code": 11,
        "aliases": [f"{key} strain"],
        "source": "test",
        "provenance": {"method": "fraction_only", "generated_at": "2026-01-01"},
        "codons": _ecoli_codons(),
    }
    data.update(overrides)
    return data


@pytest.fixture
def user_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".kuma" / "kuro" / "codon_tables"
    directory.mkdir(parents=True)
    codon_table_mod.get_registry().refresh()
    yield directory
    codon_table_mod.get_registry().refresh()


def _write(directory: Path, key: str, **overrides) -> Path:
    path = directory / f"{key}.json"
    path.write_text(json.dumps(_user_table(key, **overrides)), encoding="utf-8")
    codon_table_mod.get_registry().refresh()
    return path


class TestDescribe:
    def test_builtin_names_its_own_file_and_digest(self, user_dir):
        described = codon_table_mod.get_registry().describe("ecoli")
        assert described["key"] == "ecoli"
        assert described["source"] == "builtin"
        assert described["path"].endswith("ecoli.json")
        assert len(described["table_sha256"]) == 64

    def test_alias_resolves_to_the_canonical_key(self, user_dir):
        assert codon_table_mod.get_registry().describe("E. coli")["key"] == "ecoli"

    def test_user_table_reports_the_user_path(self, user_dir):
        path = _write(user_dir, "mylab")
        described = codon_table_mod.get_registry().describe("mylab")
        assert described["source"] == "user"
        assert Path(described["path"]) == path

    def test_unknown_organism_raises(self, user_dir):
        with pytest.raises(ValueError):
            codon_table_mod.get_registry().describe("nosuchtable")


class TestPortableDocument:
    """A workspace carries this block, and installing writes it back."""

    @pytest.mark.parametrize("key", sorted(SHIPPED))
    def test_round_trip_keeps_the_canonical_digest(self, key, user_dir, tmp_path):
        entry = next(
            o for o in codon_table_mod.get_registry().scan()["organisms"]
            if o["key"] == key
        )
        target = tmp_path / f"{key}.json"
        target.write_text(json.dumps(entry["document"]), encoding="utf-8")
        report = validate_codon_table_file(
            target, ValidationContext(is_builtin=False)
        )
        assert report.ok, report.error_codes
        assert report.table_sha256 == entry["table_sha256"]

    def test_document_carries_the_codons_and_the_key(self, user_dir):
        _write(user_dir, "mylab")
        entry = next(
            o for o in codon_table_mod.get_registry().scan()["organisms"]
            if o["key"] == "mylab"
        )
        document = entry["document"]
        assert document["key"] == "mylab"
        assert document["genetic_code"] == 11
        assert set(document["codons"]) == set(_ecoli_codons())
        assert document["aliases"] == ["mylab strain"]


class TestFailuresAndNormalizations:
    def test_failed_entry_carries_params_for_every_error(self, user_dir):
        (user_dir / "broken.json").write_text("{not json", encoding="utf-8")
        codon_table_mod.get_registry().refresh()
        failed = codon_table_mod.get_registry().scan()["failed"]
        entry = next(f for f in failed if f["filename"] == "broken.json")
        assert entry["code"] == "V3"
        assert [f["code"] for f in entry["findings"]] == ["V3"]
        assert set(entry["findings"][0]["params"]) == {"line", "col", "detail"}

    def test_shadowed_user_file_carries_r5_params(self, user_dir):
        _write(user_dir, "ecoli")
        failed = codon_table_mod.get_registry().scan()["failed"]
        entry = next(f for f in failed if f["filename"] == "ecoli.json")
        assert entry["findings"] == [
            {"code": "R5", "params": {"filename": "ecoli.json", "stem": "ecoli"}}
        ]

    def test_normalizations_reach_the_listing(self, user_dir):
        """N1 was produced and then dropped; its ten locales were unreachable."""
        codons = _ecoli_codons()
        codons["K"] = [["AAA", 0.76], ["AAG", 0.24]]
        codons["F"] = [["UUU", 0.57], ["UUC", 0.43]]
        _write(user_dir, "rnalab", codons=codons)
        entry = next(
            o for o in codon_table_mod.get_registry().scan()["organisms"]
            if o["key"] == "rnalab"
        )
        assert "N1" in [n["code"] for n in entry["normalizations"]]
        assert entry["document"]["codons"]["F"][0][0] == "TTT"


class TestManifestKnownAnswer:
    """Section 8.1's hole: same key, different numbers, identical manifests."""

    def _provenance(self, organism: str) -> dict:
        from sidecar_kuro.handlers.design import _codon_table_provenance

        return _codon_table_provenance(organism)

    def test_same_key_different_codons_separate(self, user_dir):
        _write(user_dir, "mylab")
        first = self._provenance("mylab")

        swapped = _ecoli_codons()
        swapped["K"] = [["AAA", 0.24], ["AAG", 0.76]]
        _write(user_dir, "mylab", codons=swapped)
        second = self._provenance("mylab")

        assert first["key"] == second["key"] == "mylab"
        assert first["table_sha256"] != second["table_sha256"]

    def test_control_same_codons_different_paperwork_stay_together(self, user_dir):
        _write(user_dir, "mylab")
        first = self._provenance("mylab")
        _write(
            user_dir,
            "mylab",
            provenance={"method": "fraction_only", "generated_at": "2030-12-31"},
        )
        second = self._provenance("mylab")
        assert first["table_sha256"] == second["table_sha256"]

    def test_user_table_becomes_a_hashed_manifest_input(self, user_dir, monkeypatch):
        import sidecar_kuro.core as core
        from sidecar_kuro.handlers import export as export_mod

        path = _write(user_dir, "mylab")
        provenance = {"codon_table": self._provenance("mylab")}
        monkeypatch.setattr(
            core, "_provenance_snapshot", lambda: (provenance, [])
        )
        inputs, extra = export_mod._design_provenance_for_manifest("state")
        assert inputs["design_codon_table"] == path
        assert extra["design"]["codon_table"]["table_sha256"]

    def test_builtin_table_is_named_only_in_extra(self, user_dir, monkeypatch):
        import sidecar_kuro.core as core
        from sidecar_kuro.handlers import export as export_mod

        provenance = {"codon_table": self._provenance("ecoli")}
        monkeypatch.setattr(
            core, "_provenance_snapshot", lambda: (provenance, [])
        )
        inputs, extra = export_mod._design_provenance_for_manifest("state")
        assert "design_codon_table" not in inputs
        assert extra["design"]["codon_table"]["key"] == "ecoli"
        assert extra["design"]["codon_table"]["source"] == "builtin"
