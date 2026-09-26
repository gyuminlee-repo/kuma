"""The import and export RPCs, and the two rules that only exist here.

V9 AND V10 HAD NO SITE BEFORE THIS PHASE.
The drop-in path of Phase 1 has no import step, so a user file named
``ecoli.json`` lost the stem race to the bundled table and was reported as R5
rather than as V9 -- the rule never ran. V10 was unreachable for a different
reason: V8 required the key to equal the file stem, so "this key is already
taken" could not be reached by any file that also satisfied V8. The import RPC
takes the key as a parameter, which is what V9's own sentence instructs the
user to do ("import under a different key, for example ecoli_lab"), and that
is what puts both rules in reach. These tests are where they are pinned.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python-core"))

from kuma_core.kuro import codon_formats as cf  # noqa: E402
from kuma_core.kuro import codon_table as codon_table_mod  # noqa: E402

from sidecar_kuro.handlers.codon import (  # noqa: E402
    handle_export_codon_table,
    handle_import_codon_table,
)


@pytest.fixture
def user_dir(tmp_path, monkeypatch) -> Iterator[Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".kuma" / "kuro" / "codon_tables"
    directory.mkdir(parents=True)
    codon_table_mod.get_registry().refresh()
    yield directory
    codon_table_mod.get_registry().refresh()


def _ecoli_document() -> dict:
    return json.loads(
        (codon_table_mod._RESOURCES_DIR / "ecoli.json").read_text(encoding="utf-8")
    )


def _params(**over) -> dict:
    base = {
        "format": "json",
        "key": "lab_strain",
        "text": json.dumps(_ecoli_document()),
        "name": "Lab strain",
        "aliases": ["lab strain"],
    }
    base.update(over)
    return base


class TestTheRulesThisPhaseUnlocks:
    def test_v9_refuses_to_replace_a_built_in_key(self, user_dir):
        result = handle_import_codon_table(_params(key="ecoli"))
        assert result["ok"] is False
        assert result["installed"] is False
        assert [f["code"] for f in result["errors"]] == ["V9"]
        # The sentence has to name the table it is protecting and offer the
        # way out, or the user has a refusal with no next action.
        params = result["errors"][0]["params"]
        assert params["key"] == "ecoli"
        assert params["name"] == "Escherichia coli K-12"
        assert not list(user_dir.glob("*.json")), "a rejection wrote to disk"
        print(f"V9: checks_performed={result['checks_performed']}")

    def test_v10_refuses_a_key_already_installed(self, user_dir):
        first = handle_import_codon_table(_params())
        assert first["ok"] and first["installed"]

        second = handle_import_codon_table(_params())
        assert second["ok"] is False
        assert [f["code"] for f in second["errors"]] == ["V10"]
        found = second["errors"][0]["params"]
        assert found["name"] == "Lab strain"
        assert found["sha8"] == first["table_sha256"][:8]
        assert found["date"], "V10 promises a date and must supply one"

    def test_v10_is_waived_by_overwrite_and_the_file_is_replaced(self, user_dir):
        handle_import_codon_table(_params())
        again = handle_import_codon_table(
            _params(name="Lab strain, recount", overwrite=True)
        )
        assert again["ok"] and again["installed"]
        stored = json.loads((user_dir / "lab_strain.json").read_text())
        assert stored["name"] == "Lab strain, recount"

    def test_control_the_same_table_under_a_free_key_installs(self, user_dir):
        """V9's own suggested remedy has to actually work."""
        result = handle_import_codon_table(_params(key="ecoli_lab"))
        assert result["ok"] and result["installed"]
        assert (user_dir / "ecoli_lab.json").exists()


class TestNormalizationsAreReported:
    def test_n1_and_n2_reach_the_caller(self, user_dir):
        """RNA and lowercase codons are converted, and the import says so."""
        document = _ecoli_document()
        document["codons"] = {
            aa: [[c.replace("T", "U").lower(), f] for c, f in pairs]
            for aa, pairs in document["codons"].items()
        }
        result = handle_import_codon_table(
            _params(text=json.dumps(document), dry_run=True)
        )
        assert result["ok"], result["errors"]
        codes = {f["code"] for f in result["normalizations"]}
        assert {"N1", "N2"} <= codes
        n1 = next(f for f in result["normalizations"] if f["code"] == "N1")
        assert n1["params"]["n"] > 0
        print(f"normalizations reported: {sorted(codes)}")

    def test_n4_fires_when_counts_carry_the_truth(self, user_dir):
        """A cusp file with a Number column is recomputed from its counts."""
        entry = next(
            e for e in codon_table_mod.get_registry().scan()["organisms"]
            if e["key"] == "ecoli"
        )
        document = dict(entry["document"])
        total = 100000
        document["counts"] = {
            aa: [[c, max(1, round(f * total))] for c, f in pairs]
            for aa, pairs in document["codons"].items()
        }
        text = cf.format_table(document, "cusp")
        result = handle_import_codon_table(
            _params(format="cusp", text=text, key="counted", dry_run=True)
        )
        assert result["ok"], result["errors"]
        assert "N4" in {f["code"] for f in result["normalizations"]}


class TestPreviewAndInstallAgree:
    def test_dry_run_validates_without_writing(self, user_dir):
        preview = handle_import_codon_table(_params(dry_run=True))
        assert preview["ok"] is True
        assert preview["installed"] is False
        assert preview["path"] is None
        assert preview["document"] is not None
        assert not list(user_dir.glob("*.json"))

        real = handle_import_codon_table(_params())
        assert real["installed"] is True
        # The preview promised a digest and a document; the install has to
        # deliver the same ones, or the preview was a different computation.
        assert real["table_sha256"] == preview["table_sha256"]
        assert real["document"] == preview["document"]

    def test_the_stored_file_is_what_the_listing_reports(self, user_dir):
        result = handle_import_codon_table(_params())
        on_disk = json.loads((user_dir / "lab_strain.json").read_text())
        assert on_disk == result["document"]
        codon_table_mod.get_registry().refresh()
        listed = next(
            e for e in codon_table_mod.get_registry().scan()["organisms"]
            if e["key"] == "lab_strain"
        )
        assert listed["document"] == on_disk
        assert listed["table_sha256"] == result["table_sha256"]

    def test_genetic_code_is_written_into_the_stored_file(self, user_dir):
        """V14 promises the assumed code is recorded. It has to be there."""
        document = _ecoli_document()
        document.pop("genetic_code", None)
        handle_import_codon_table(_params(text=json.dumps(document)))
        stored = json.loads((user_dir / "lab_strain.json").read_text())
        assert stored["genetic_code"] == 11


class TestTwoInputPathsOneStoredTable:
    def test_json_and_csv_of_one_table_install_identically(self, user_dir):
        document = _ecoli_document()
        via_json = handle_import_codon_table(
            _params(key="path_a", text=json.dumps(document), dry_run=True)
        )
        entry = next(
            e for e in codon_table_mod.get_registry().scan()["organisms"]
            if e["key"] == "ecoli"
        )
        via_csv = handle_import_codon_table(
            _params(
                key="path_b",
                format="csv",
                text=cf.format_table(entry["document"], "csv"),
                taxid=document["taxid"],
                dry_run=True,
            )
        )
        assert via_json["ok"] and via_csv["ok"], (
            via_json["errors"], via_csv["errors"]
        )
        assert via_json["table_sha256"] == via_csv["table_sha256"]

    def test_a_converted_import_records_where_it_came_from(self, user_dir):
        entry = next(
            e for e in codon_table_mod.get_registry().scan()["organisms"]
            if e["key"] == "ecoli"
        )
        result = handle_import_codon_table(
            _params(
                key="from_csv",
                format="csv",
                text=cf.format_table(entry["document"], "csv"),
            )
        )
        assert result["ok"], result["errors"]
        stored = json.loads((user_dir / "from_csv.json").read_text())
        assert stored["provenance"]["method"] == "fraction_only"
        assert stored["provenance"]["source_format"] == "csv"
        # V32 warns that a run cannot say where its numbers came from. After
        # provenance is recorded it can, so the warning must be gone.
        assert "V32" not in {f["code"] for f in result["warnings"]}


class TestParseFailuresReachTheCaller:
    def test_a_broken_csv_is_reported_as_v36_not_raised(self, user_dir):
        result = handle_import_codon_table(
            _params(format="csv", text="amino_acid,codon\nA,GCC\n")
        )
        assert result["ok"] is False
        assert [f["code"] for f in result["errors"]] == ["V36"]
        assert result["errors"][0]["params"]["format"] == "csv"
        assert result["checks_performed"] == 0, (
            "a rejection before validation examined nothing and must say so"
        )

    def test_broken_json_keeps_its_line_and_column(self, user_dir):
        result = handle_import_codon_table(_params(text="{ not json"))
        assert [f["code"] for f in result["errors"]] == ["V3"]
        assert result["errors"][0]["params"]["line"] == 1

    def test_a_json_array_is_v4(self, user_dir):
        result = handle_import_codon_table(_params(text="[]"))
        assert [f["code"] for f in result["errors"]] == ["V4"]
        assert result["errors"][0]["params"]["type"] == "list"


class TestExport:
    @pytest.mark.parametrize("fmt", ["json", "csv", "cusp"])
    def test_export_writes_a_file_that_imports_back_to_the_same_digest(
        self, user_dir, tmp_path, fmt
    ):
        """The round trip through the RPCs, not only through the converters."""
        entry = next(
            e for e in codon_table_mod.get_registry().scan()["organisms"]
            if e["key"] == "ecoli"
        )
        target = tmp_path / f"out{cf.EXPORT_EXTENSIONS[fmt]}"
        written = handle_export_codon_table(
            {"key": "ecoli", "format": fmt, "filepath": str(target)}
        )
        assert Path(written["path"]).exists()
        assert written["bytes"] > 0

        back = handle_import_codon_table(
            _params(
                key="ecoli_lab",
                format=fmt,
                text=None,
                filepath=str(target),
                name=entry["name"],
                taxid=entry["taxid"],
                dry_run=True,
            )
        )
        assert back["ok"], back["errors"]
        assert back["table_sha256"] == entry["table_sha256"]

    def test_export_refuses_a_key_that_is_not_installed(self, user_dir, tmp_path):
        with pytest.raises(ValueError, match="No codon table named"):
            handle_export_codon_table(
                {"key": "nope", "format": "json",
                 "filepath": str(tmp_path / "x.json")}
            )

    def test_export_refuses_kazusa(self, user_dir, tmp_path):
        """Kazusa is an input format only; there is one stored canon.

        The refusal comes from the Literal on ExportCodonTableParams rather
        than from a branch in the handler, which is where it belongs: the
        format union is the contract, and a ValidationError is a ValueError,
        so the dispatcher turns it into an RPC error like any other.
        """
        with pytest.raises(ValueError, match="'json', 'csv' or 'cusp'"):
            handle_export_codon_table(
                {"key": "ecoli", "format": "kazusa",
                 "filepath": str(tmp_path / "x.txt")}
            )


class TestTheDigestSurvivesTheImport:
    """The reproducibility guarantee, applied to the path that installs.

    ``genetic_code`` is an input to ``canonical_digest``. If the dialog's
    value overrode what a colleague's file declares, their table would carry
    one digest on their machine and another here, which is the section 8.1
    hole this whole feature exists to close -- reopened by the import path.

    V16 cannot stand in for these tests. NCBI genetic codes 1 and 11 have
    identical forward tables and identical stop codons (measured with
    biopython: they differ only in their start codons), so a table declared as
    1 and read as 11 passes every codon-to-amino-acid check there is. The
    bundled tables are all code 11, so the round-trip controls cannot see it
    either. These are the only tests that can.
    """

    def test_a_declared_genetic_code_survives_and_keeps_its_digest(self, user_dir):
        from kuma_core.kuro.codon_import import canonical_digest

        document = _ecoli_document()
        document["genetic_code"] = 1
        result = handle_import_codon_table(_params(text=json.dumps(document)))
        assert result["ok"], result["errors"]

        stored = json.loads((user_dir / "lab_strain.json").read_text())
        assert stored["genetic_code"] == 1, "the file's declared code was overwritten"
        expected = canonical_digest(
            {aa: [tuple(p) for p in pairs]
             for aa, pairs in stored["codons"].items()},
            1,
        )
        assert result["table_sha256"] == expected

    def test_discrimination_the_two_codes_give_different_digests(self, user_dir):
        """The assertion above can fail: 1 and 11 must not agree by accident."""
        from kuma_core.kuro.codon_import import canonical_digest

        entry = next(
            e for e in codon_table_mod.get_registry().scan()["organisms"]
            if e["key"] == "ecoli"
        )
        codons = {
            aa: [tuple(p) for p in pairs]
            for aa, pairs in entry["document"]["codons"].items()
        }
        assert canonical_digest(codons, 1) != canonical_digest(codons, 11)

    def test_v14_warns_when_a_json_file_declares_no_genetic_code(self, user_dir):
        """V14 promises a warning and a written-in default. Both, or neither."""
        document = _ecoli_document()
        document.pop("genetic_code", None)
        result = handle_import_codon_table(
            _params(text=json.dumps(document), dry_run=True)
        )
        assert result["ok"], result["errors"]
        assert "V14" in {f["code"] for f in result["warnings"]}
        assert result["document"]["genetic_code"] == 11

    def test_a_converted_format_still_takes_the_dialog_value(self, user_dir):
        """CSV carries no genetic code, so the dialog is its only source."""
        entry = next(
            e for e in codon_table_mod.get_registry().scan()["organisms"]
            if e["key"] == "ecoli"
        )
        result = handle_import_codon_table(
            _params(
                key="from_csv",
                format="csv",
                text=cf.format_table(entry["document"], "csv"),
                genetic_code=1,
                dry_run=True,
            )
        )
        assert result["ok"], result["errors"]
        assert result["document"]["genetic_code"] == 1


class TestTheImportJudgesTheDiskNotACache:
    def test_v10_fires_for_a_file_dropped_in_after_the_last_listing(self, user_dir):
        """The Open folder path and the import path meet here.

        A user lists the organisms, opens the folder, drops a table in, then
        imports the same key. With the scan answered from cache, V10 would see
        a disk that predates their file and os.replace would overwrite it
        without a word -- which is the one thing V10 exists to prevent.
        """
        codon_table_mod.get_registry().scan()  # fill the cache
        document = _ecoli_document()
        document["key"] = "lab_strain"
        document["name"] = "Dropped in by hand"
        (user_dir / "lab_strain.json").write_text(
            json.dumps(document), encoding="utf-8"
        )

        result = handle_import_codon_table(_params(name="Imported"))
        assert result["ok"] is False
        assert [f["code"] for f in result["errors"]] == ["V10"]
        assert json.loads((user_dir / "lab_strain.json").read_text())["name"] == (
            "Dropped in by hand"
        ), "the hand-dropped table was overwritten"
