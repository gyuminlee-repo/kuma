# ruff: noqa: S101
"""Tests for GPU/CPU detection additions to system_info.

Covers:
- detect_gpu() return shape and type contract
- cpu_cores() return type contract
- recommend_esm2_model() contains all expected keys (existing + new)
- detect_gpu() does not raise even when torch is absent (current .venv state)
"""
from __future__ import annotations

import kuma_core.shared.system_info as system_info

_VALID_GPU_KINDS = {"cuda", "mps", "cuda?", "mps?", None}

_EXPECTED_RECOMMEND_KEYS = {
	# Existing keys (must not be removed)
	"os",
	"arch",
	"ram_gb",
	"disk_free_gb",
	"recommended_model_id",
	"recommended_label",
	"models",
	"warnings",
	# New keys added by T2
	"cpu_cores",
	"gpu_available",
	"gpu_kind",
}


def _clear_cache() -> None:
	"""Clear the module-level ESM2 cache so each test sees a fresh build."""
	system_info._esm2_cache.clear()


class TestDetectGpu:
	def test_returns_dict_with_required_keys(self) -> None:
		result = system_info.detect_gpu()
		assert "gpu_available" in result
		assert "gpu_kind" in result

	def test_gpu_available_is_bool(self) -> None:
		result = system_info.detect_gpu()
		assert isinstance(result["gpu_available"], bool)

	def test_gpu_kind_is_valid(self) -> None:
		result = system_info.detect_gpu()
		assert result["gpu_kind"] in _VALID_GPU_KINDS

	def test_gpu_kind_is_str_or_none(self) -> None:
		result = system_info.detect_gpu()
		val = result["gpu_kind"]
		assert val is None or isinstance(val, str)

	def test_does_not_raise_without_torch(self) -> None:
		"""detect_gpu must not raise even when torch is absent in the environment."""
		# The test environment (.venv) has no torch installed.
		# ImportError is handled inside detect_gpu; this must complete cleanly.
		result = system_info.detect_gpu()
		assert "gpu_available" in result


class TestCpuCores:
	def test_returns_int_or_none(self) -> None:
		result = system_info.cpu_cores()
		assert result is None or isinstance(result, int)

	def test_positive_if_not_none(self) -> None:
		result = system_info.cpu_cores()
		if result is not None:
			assert result > 0


class TestRecommendEsm2ModelHardwareKeys:
	def setup_method(self) -> None:
		_clear_cache()

	def test_all_expected_keys_present(self) -> None:
		result = system_info.recommend_esm2_model()
		missing = _EXPECTED_RECOMMEND_KEYS - result.keys()
		assert not missing

	def test_existing_keys_not_removed(self) -> None:
		result = system_info.recommend_esm2_model()
		existing = {
			"os", "arch", "ram_gb", "disk_free_gb",
			"recommended_model_id", "recommended_label",
			"models", "warnings",
		}
		assert not existing - result.keys()

	def test_cpu_cores_type(self) -> None:
		result = system_info.recommend_esm2_model()
		val = result["cpu_cores"]
		assert val is None or isinstance(val, int)

	def test_gpu_available_type(self) -> None:
		result = system_info.recommend_esm2_model()
		assert isinstance(result["gpu_available"], bool)

	def test_gpu_kind_type_and_value(self) -> None:
		result = system_info.recommend_esm2_model()
		assert result["gpu_kind"] in _VALID_GPU_KINDS

	def test_models_list_intact(self) -> None:
		result = system_info.recommend_esm2_model()
		assert isinstance(result["models"], list)
		assert len(result["models"]) == 6

	def test_cache_consistent_with_fresh_call(self) -> None:
		"""Second call must return identical object (cache hit)."""
		first = system_info.recommend_esm2_model()
		second = system_info.recommend_esm2_model()
		assert first is second
