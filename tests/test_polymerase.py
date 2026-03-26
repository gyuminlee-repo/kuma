"""Tests for polymerase profile registry."""

from __future__ import annotations

import pytest

from kuro.polymerase import PolymeraseProfile, PolymeraseRegistry


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
