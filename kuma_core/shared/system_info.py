"""Cross-platform system probing and ESM2 RAM recommendations."""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

_ESM2_BASE_URL = "https://dl.fbaipublicfiles.com/fair-esm/models"


@dataclass(frozen=True)
class Esm2ModelSpec:
	model_id: str
	label: str
	size_label: str
	min_ram_gb: int
	recommended_ram_gb: int
	download_url: str
	# Approximate file size in bytes (fair-esm official).
	# Assumption: these are near-exact values from fair-esm release pages.
	# The actual download should verify via Content-Length header.
	expected_bytes: int


def _esm2_url(model_id: str) -> str:
	return f"{_ESM2_BASE_URL}/{model_id}.pt"


ESM2_MODELS = [
	Esm2ModelSpec(
		"esm2_t6_8M_UR50D", "ESM2 8M", "8M", 8, 8,
		_esm2_url("esm2_t6_8M_UR50D"), 31_400_000,
	),
	Esm2ModelSpec(
		"esm2_t12_35M_UR50D", "ESM2 35M", "35M", 8, 16,
		_esm2_url("esm2_t12_35M_UR50D"), 138_400_000,
	),
	Esm2ModelSpec(
		"esm2_t30_150M_UR50D", "ESM2 150M", "150M", 16, 32,
		_esm2_url("esm2_t30_150M_UR50D"), 619_900_000,
	),
	Esm2ModelSpec(
		"esm2_t33_650M_UR50D", "ESM2 650M", "650M", 32, 48,
		_esm2_url("esm2_t33_650M_UR50D"), 2_614_000_000,
	),
	Esm2ModelSpec(
		"esm2_t36_3B_UR50D", "ESM2 3B", "3B", 64, 96,
		_esm2_url("esm2_t36_3B_UR50D"), 11_350_000_000,
	),
	Esm2ModelSpec(
		"esm2_t48_15B_UR50D", "ESM2 15B", "15B", 128, 192,
		_esm2_url("esm2_t48_15B_UR50D"), 57_700_000_000,
	),
]

# Module-level cache: RAM and disk are stable for the lifetime of the sidecar
# process. Caching avoids repeated syscalls on every RPC call (important when
# the user refreshes the recommendation card multiple times).
# Uses a list as a mutable container to avoid the `global` keyword.
_esm2_cache: list[dict] = []


def _round_gb(byte_count: int | float | None) -> float | None:
	if byte_count is None:
		return None
	return round(float(byte_count) / (1024**3), 1)


def _darwin_total_memory_bytes() -> int | None:
	# Use sysctlbyname() via ctypes instead of shelling out to sysctl(8).
	# This avoids subprocess entirely and satisfies S603/S607.
	try:
		libc = ctypes.CDLL("libc.dylib", use_errno=True)
		size = ctypes.c_size_t(ctypes.sizeof(ctypes.c_uint64()))
		value = ctypes.c_uint64(0)
		ret = libc.sysctlbyname(
			b"hw.memsize",
			ctypes.byref(value),
			ctypes.byref(size),
			None,
			0,
		)
		if ret == 0:
			return int(value.value)
	except (OSError, AttributeError):
		pass
	return None


def _windows_total_memory_bytes() -> int | None:
	class MemoryStatusEx(ctypes.Structure):
		_fields_ = [
			("dwLength", ctypes.c_ulong),
			("dwMemoryLoad", ctypes.c_ulong),
			("ullTotalPhys", ctypes.c_ulonglong),
			("ullAvailPhys", ctypes.c_ulonglong),
			("ullTotalPageFile", ctypes.c_ulonglong),
			("ullAvailPageFile", ctypes.c_ulonglong),
			("ullTotalVirtual", ctypes.c_ulonglong),
			("ullAvailVirtual", ctypes.c_ulonglong),
			("ullAvailExtendedVirtual", ctypes.c_ulonglong),
		]

	status = MemoryStatusEx()
	status.dwLength = ctypes.sizeof(MemoryStatusEx)
	if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
		return int(status.ullTotalPhys)
	return None


def _posix_total_memory_bytes() -> int | None:
	try:
		pages = os.sysconf("SC_PHYS_PAGES")
		page_size = os.sysconf("SC_PAGE_SIZE")
		return int(pages * page_size)
	except (AttributeError, OSError, ValueError):
		return None


def total_memory_gb() -> float | None:
	system = platform.system().lower()
	if system == "darwin":
		return _round_gb(_darwin_total_memory_bytes())
	if system == "windows":
		return _round_gb(_windows_total_memory_bytes())
	return _round_gb(_posix_total_memory_bytes())


def disk_free_gb(path: str | None = None) -> float | None:
	try:
		target = Path(path or Path.home())
		usage = shutil.disk_usage(target)
		return _round_gb(usage.free)
	except OSError:
		return None



def detect_gpu() -> dict:
	"""Best-effort GPU detection without requiring torch as a hard dependency.

	Returns {"gpu_available": bool, "gpu_kind": str | None}.
	kind is one of: "cuda", "mps", "cuda?", "mps?", None.
	"cuda?" / "mps?" indicate heuristic detection when torch is absent.
	"""
	# Attempt precise detection via torch first.
	try:
		import torch  # noqa: PLC0415

		if torch.cuda.is_available():
			return {"gpu_available": True, "gpu_kind": "cuda"}
		if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
			return {"gpu_available": True, "gpu_kind": "mps"}
		return {"gpu_available": False, "gpu_kind": None}
	except ImportError:
		pass

	# Fallback: heuristic probes when torch is not installed.
	if shutil.which("nvidia-smi") is not None:
		return {"gpu_available": True, "gpu_kind": "cuda?"}
	if platform.system() == "Darwin" and platform.machine() == "arm64":
		return {"gpu_available": True, "gpu_kind": "mps?"}
	return {"gpu_available": False, "gpu_kind": None}


def cpu_cores() -> int | None:
	"""Return the number of logical CPU cores, or None if undetermined."""
	return os.cpu_count()


def _model_status(spec: Esm2ModelSpec, ram_gb: float | None) -> str:
	if ram_gb is None:
		return "unknown"
	if ram_gb < spec.min_ram_gb:
		return "blocked"
	if ram_gb < spec.recommended_ram_gb:
		return "caution"
	return "safe"


def recommend_esm2_model() -> dict:
	if _esm2_cache:
		return _esm2_cache[0]

	ram_gb = total_memory_gb()
	disk_gb = disk_free_gb()
	system = platform.system() or "Unknown"
	machine = platform.machine() or "unknown"

	models = []
	for spec in ESM2_MODELS:
		status = _model_status(spec, ram_gb)
		reason = ""
		if status == "blocked":
			reason = f"Requires at least {spec.min_ram_gb} GB RAM."
		elif status == "caution":
			reason = f"Allowed, but {spec.recommended_ram_gb} GB RAM is recommended."
		elif status == "safe":
			reason = f"Within the recommended {spec.recommended_ram_gb} GB RAM budget."
		else:
			reason = "RAM could not be detected."
		models.append(
			{
				"model_id": spec.model_id,
				"label": spec.label,
				"size_label": spec.size_label,
				"min_ram_gb": spec.min_ram_gb,
				"recommended_ram_gb": spec.recommended_ram_gb,
				"download_url": spec.download_url,
				"expected_bytes": spec.expected_bytes,
				"status": status,
				"reason": reason,
			}
		)

	recommended = None
	if ram_gb is not None:
		safe = [m for m in models if m["status"] == "safe"]
		caution = [m for m in models if m["status"] == "caution"]
		if safe:
			recommended = safe[-1]
		elif caution:
			recommended = caution[-1]

	warnings = []
	if disk_gb is not None and disk_gb < 10:
		warnings.append("Less than 10 GB free disk space is available.")
	if ram_gb is not None and all(m["status"] == "blocked" for m in models):
		warnings.append("No ESM2 model is within the detected RAM budget.")

	gpu_info = detect_gpu()

	result = {
		"os": system,
		"arch": machine,
		"ram_gb": ram_gb,
		"disk_free_gb": disk_gb,
		"recommended_model_id": recommended["model_id"] if recommended else None,
		"recommended_label": recommended["label"] if recommended else None,
		"models": models,
		"warnings": warnings,
		"cpu_cores": cpu_cores(),
		"gpu_available": gpu_info["gpu_available"],
		"gpu_kind": gpu_info["gpu_kind"],
	}
	_esm2_cache.append(result)
	return result
