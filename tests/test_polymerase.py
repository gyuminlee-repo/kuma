"""Tests for polymerase profile registry."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kuma_core.kuro.polymerase import PolymeraseProfile, PolymeraseRegistry


class TestPolymeraseRegistryGet:
    def test_get_q5(self):
        registry = PolymeraseRegistry()
        profile = registry.get("Q5")
        assert isinstance(profile, PolymeraseProfile)
        assert profile.name == "Q5"

    def test_get_benchling(self):
        registry = PolymeraseRegistry()
        profile = registry.get("Benchling")
        assert profile.name == "Benchling"

    def test_get_taq(self):
        registry = PolymeraseRegistry()
        profile = registry.get("Taq")
        assert profile.name == "Taq"

    def test_get_nonexistent_raises_keyerror(self):
        registry = PolymeraseRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.get("NonExistent")

    def test_get_empty_name_raises_keyerror(self):
        registry = PolymeraseRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.get("")

    def test_get_case_sensitive(self):
        registry = PolymeraseRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.get("q5")


class TestPolymeraseRegistryListNames:
    def test_list_names_returns_sorted(self):
        registry = PolymeraseRegistry()
        names = registry.list_names()
        assert names == sorted(names)

    def test_list_names_contains_known_profiles(self):
        registry = PolymeraseRegistry()
        names = registry.list_names()
        for expected in ["Q5", "Phusion", "Taq", "Benchling", "KOD", "DreamTaq"]:
            assert expected in names

    def test_list_names_count(self):
        registry = PolymeraseRegistry()
        names = registry.list_names()
        assert len(names) >= 6


class TestPolymeraseProfileFields:
    @pytest.fixture()
    def registry(self) -> PolymeraseRegistry:
        return PolymeraseRegistry()

    def test_benchling_asymmetric_tm(self, registry: PolymeraseRegistry):
        p = registry.get("Benchling")
        assert p.opt_tm_fwd == 62.0
        assert p.opt_tm_rev == 58.0
        assert p.opt_tm_overlap == 42.0

    def test_benchling_min_3prime_dist(self, registry: PolymeraseRegistry):
        p = registry.get("Benchling")
        assert p.min_3prime_dist == 4

    def test_q5_has_no_asymmetric_tm(self, registry: PolymeraseRegistry):
        p = registry.get("Q5")
        assert p.opt_tm_fwd is None
        assert p.opt_tm_rev is None
        assert p.opt_tm_overlap is None

    def test_q5_default_min_3prime_dist(self, registry: PolymeraseRegistry):
        p = registry.get("Q5")
        assert p.min_3prime_dist == 0

    def test_tm_method_values(self, registry: PolymeraseRegistry):
        valid_methods = {"breslauer", "santalucia"}
        for name in registry.list_names():
            p = registry.get(name)
            assert p.tm_method in valid_methods, f"{name}: invalid tm_method"

    def test_salt_correction_values(self, registry: PolymeraseRegistry):
        valid_corrections = {"schildkraut", "santalucia", "owczarzy"}
        for name in registry.list_names():
            p = registry.get(name)
            assert p.salt_correction in valid_corrections, (
                f"{name}: invalid salt_correction"
            )

    def test_gc_range_is_valid(self, registry: PolymeraseRegistry):
        for name in registry.list_names():
            p = registry.get(name)
            assert 0.0 <= p.min_gc < p.max_gc <= 100.0, (
                f"{name}: invalid GC range"
            )

    def test_tm_range_is_valid(self, registry: PolymeraseRegistry):
        for name in registry.list_names():
            p = registry.get(name)
            assert p.min_tm < p.opt_tm < p.max_tm, f"{name}: invalid Tm range"

    def test_size_range_is_valid(self, registry: PolymeraseRegistry):
        for name in registry.list_names():
            p = registry.get(name)
            assert p.min_size < p.opt_size < p.max_size, (
                f"{name}: invalid size range"
            )

    def test_all_profiles_are_dataclass_instances(
        self, registry: PolymeraseRegistry
    ):
        for name in registry.list_names():
            p = registry.get(name)
            assert isinstance(p, PolymeraseProfile)


class TestCustomPolymerasePersistence:
    def test_save_and_reload_custom_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / "custom_polymerases.json"
            registry = PolymeraseRegistry(custom_path=custom_path)
            profile = PolymeraseProfile(
                name="Custom HiFi",
                tm_method="santalucia",
                salt_correction="owczarzy",
                opt_tm=68.0,
                min_tm=63.0,
                max_tm=73.0,
                opt_size=21,
                min_size=18,
                max_size=28,
                min_gc=35.0,
                max_gc=65.0,
                salt_monovalent=50.0,
                salt_divalent=2.0,
                dntp_conc=0.8,
                dna_conc=250.0,
                max_tm_diff=4.0,
                opt_tm_fwd=65.0,
                opt_tm_rev=61.0,
                opt_tm_overlap=45.0,
                min_3prime_dist=3,
            )

            registry.save_custom(profile)

            restarted = PolymeraseRegistry(custom_path=custom_path)
            loaded = restarted.get("Custom HiFi")
            assert loaded.name == "Custom HiFi"
            assert loaded.opt_tm_overlap == 45.0
            assert loaded.min_3prime_dist == 3
