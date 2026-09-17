"""User codon-table directory, R1/R5 isolation, and the D1 single-registry fix.

The D1 regression test has to go through the handler modules, not through
``core.get_registry()`` directly. ``handlers/misc.py`` and ``handlers/design.py``
used to bind ``_codon_registry`` at module import, so a fix applied only in
``core.py`` would leave both handlers holding the old object and the assertion
would still pass if it asked ``core`` itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python-core"))

from kuma_core.kuro import codon_table as codon_table_mod  # noqa: E402

SHIPPED = {"bsubtilis", "ecoli", "hsapiens", "mextorquens", "scerevisiae"}


def _valid_user_table(key: str, source_stem: str = "ecoli", **overrides) -> dict:
    # ecoli by default because it carries no zero-fraction codon, so a table
    # built from it validates without even a warning.
    src = json.loads(
        (codon_table_mod._RESOURCES_DIR / f"{source_stem}.json").read_text(
            encoding="utf-8"
        )
    )
    data = {
        "schema_version": 1,
        "key": key,
        "name": f"Lab table {key}",
        "taxid": None,
        "genetic_code": 11,
        "aliases": [f"{key} strain"],
        "source": "test",
        "provenance": {"method": "fraction_only"},
        "codons": src["codons"],
    }
    data.update(overrides)
    return data


@pytest.fixture
def user_dir(tmp_path, monkeypatch) -> Path:
    """Point HOME at a fresh directory and hand back the codon-table folder."""
    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".kuma" / "kuro" / "codon_tables"
    directory.mkdir(parents=True)
    codon_table_mod.get_registry().refresh()
    yield directory
    codon_table_mod.get_registry().refresh()


class TestUserDirectoryResolution:
    def test_user_dir_follows_home_after_import(self, user_dir):
        # The directory is resolved per call. Freezing it at import would make
        # the sidecar RPC suite answer from the developer's real home.
        assert codon_table_mod.user_codon_dir() == user_dir
        assert codon_table_mod.get_registry().scan()["user_dir"] == str(user_dir)

    def test_valid_user_table_joins_the_list(self, user_dir):
        (user_dir / "lab_strain.json").write_text(
            json.dumps(_valid_user_table("lab_strain")), encoding="utf-8"
        )
        registry = codon_table_mod.get_registry()
        registry.refresh()
        assert set(registry.list_organisms()) == SHIPPED | {"lab_strain"}
        entry = next(
            e for e in registry.scan()["organisms"] if e["key"] == "lab_strain"
        )
        assert entry["source"] == "user"
        assert entry["taxid"] is None
        assert entry["warnings"] == []

    def test_user_alias_resolves(self, user_dir):
        (user_dir / "lab_strain.json").write_text(
            json.dumps(_valid_user_table("lab_strain")), encoding="utf-8"
        )
        codon_table_mod.get_registry().refresh()
        assert codon_table_mod.resolve_organism_key("Lab_strain STRAIN") == (
            "lab_strain"
        )

    def test_r1_broken_file_is_skipped_not_fatal(self, user_dir):
        (user_dir / "lab_strain.json").write_text(
            json.dumps(_valid_user_table("lab_strain")), encoding="utf-8"
        )
        (user_dir / "broken.json").write_text("{ not json", encoding="utf-8")
        registry = codon_table_mod.get_registry()
        registry.refresh()
        scan = registry.scan()
        assert set(registry.list_organisms()) == SHIPPED | {"lab_strain"}
        failed = {f["filename"]: f for f in scan["failed"]}
        assert set(failed) == {"broken.json"}
        assert failed["broken.json"]["code"] == "V3"

    def test_case_only_collision_keeps_the_lowercase_file(self, user_dir):
        # Linux lets both names coexist. The lowercase one is the one kuma can
        # actually key on, so it loads and the other is reported.
        (user_dir / "lab_strain.json").write_text(
            json.dumps(_valid_user_table("lab_strain")), encoding="utf-8"
        )
        (user_dir / "Lab_Strain.json").write_text(
            json.dumps(_valid_user_table("lab_strain")), encoding="utf-8"
        )
        registry = codon_table_mod.get_registry()
        registry.refresh()
        scan = registry.scan()
        assert "lab_strain" in registry.list_organisms()
        failed = {f["filename"]: f for f in scan["failed"]}
        assert set(failed) == {"Lab_Strain.json"}
        assert "lab_strain" in failed["Lab_Strain.json"]["reason"]

    def test_r5_bundled_stem_shadows_the_user_file(self, user_dir):
        # Different numbers under the built-in key, so the lookup assertion
        # below distinguishes the two files rather than comparing equals.
        (user_dir / "ecoli.json").write_text(
            json.dumps(_valid_user_table("ecoli", source_stem="mextorquens")),
            encoding="utf-8",
        )
        registry = codon_table_mod.get_registry()
        registry.refresh()
        scan = registry.scan()
        assert set(registry.list_organisms()) == SHIPPED
        failed = {f["filename"]: f for f in scan["failed"]}
        assert failed["ecoli.json"]["code"] == "R5"
        # The bundled numbers win the lookup as well, not just the listing.
        bundled = json.loads(
            (codon_table_mod._RESOURCES_DIR / "ecoli.json").read_text(
                encoding="utf-8"
            )
        )
        assert registry.get_codon_table("ecoli")["A"] == [
            tuple(pair) for pair in bundled["codons"]["A"]
        ]


class TestCachedTableIsNotShared:
    def test_mutating_the_returned_table_does_not_leak(self):
        registry = codon_table_mod.get_registry()
        first = registry.get_codon_table("ecoli")
        original = list(first["A"])
        first["A"].clear()
        first["INVALID"] = []
        assert registry.get_codon_table("ecoli")["A"] == original
        assert "INVALID" not in registry.get_codon_table("ecoli")

    def test_ecoli_constant_matches_a_fresh_lookup(self):
        assert codon_table_mod.ECOLI_CODON_USAGE == (
            codon_table_mod.get_registry().get_codon_table("ecoli")
        )


class TestSingleRegistryInstance:
    def test_both_handlers_answer_from_one_registry(self, user_dir):
        """D1: the dropdown and the design gate must not drift apart."""
        from sidecar_kuro.handlers import design as design_handlers
        from sidecar_kuro.handlers import misc as misc_handlers

        (user_dir / "lab_strain.json").write_text(
            json.dumps(_valid_user_table("lab_strain")), encoding="utf-8"
        )

        # misc.py owns the dropdown and refreshes the registry.
        dropdown = misc_handlers.handle_list_organisms({})
        dropdown_keys = {e["key"] for e in dropdown["organisms"]}

        # design.py owns the gate that rejects an unknown organism.
        gate_keys = set(design_handlers._core.get_registry().list_organisms())

        # sdm_engine and every codon lookup go through the domain singleton.
        domain_keys = set(codon_table_mod.get_registry().list_organisms())

        assert dropdown_keys == gate_keys == domain_keys
        assert "lab_strain" in dropdown_keys

    def test_handlers_do_not_hold_a_module_level_binding(self):
        from sidecar_kuro.handlers import design as design_handlers
        from sidecar_kuro.handlers import misc as misc_handlers

        for module in (design_handlers, misc_handlers):
            assert not hasattr(module, "_codon_registry"), module.__name__

    def test_core_registry_is_the_domain_singleton(self):
        import sidecar_kuro.core as core

        assert core.get_registry() is codon_table_mod.get_registry()
